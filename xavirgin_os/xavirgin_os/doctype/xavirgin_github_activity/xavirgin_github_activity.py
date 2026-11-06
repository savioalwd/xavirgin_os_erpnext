import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, format_datetime, formatdate, getdate, now_datetime, today
from xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session import (
    compute_badge_tier,
    resolve_employee_context,
)


def is_github_admin_or_lead(user: str = None) -> bool:
    u = user or frappe.session.user
    if u == "Administrator":
        return True
    roles = set(frappe.get_roles(u))
    return bool(roles.intersection({"System Manager", "Xavirgin HR Admin", "Xavirgin HR Manager", "Xavirgin Team Lead"}))


def extract_clean_handle(val: str) -> str:
    """Normalizes a GitHub username or full URL into a lowercase handle."""
    if not val:
        return ""
    cleaned = val.strip().rstrip("/")
    if "/" in cleaned:
        cleaned = cleaned.split("/")[-1]
    return cleaned.lstrip("@").strip()


def resolve_employee_by_github_handle(github_username: str = "", sender_email: str = "") -> dict:
    """Resolves an Employee record from a GitHub username or commit author email without false positives."""
    handle = extract_clean_handle(github_username)
    emp_fields = ["name", "employee_name", "department", "designation", "custom_github_username"]

    if handle:
        # 1. Exact or URL match on Employee.custom_github_username
        variants = [
            handle,
            handle.lower(),
            f"https://github.com/{handle}",
            f"https://github.com/{handle.lower()}",
        ]
        emp = frappe.db.get_value(
            "Employee",
            {"custom_github_username": ["in", variants], "status": "Active"},
            emp_fields,
            as_dict=True,
        ) or frappe.db.get_value(
            "Employee",
            {"custom_github_username": ["in", variants]},
            emp_fields,
            as_dict=True,
        )
        if emp:
            return emp

        # 2. Lineage match via Xavirgin Candidate (github_username or github_url)
        if frappe.db.exists("DocType", "Xavirgin Candidate"):
            cand_emp = frappe.db.get_value(
                "Xavirgin Candidate",
                {"github_username": ["in", [handle, handle.lower()]], "employee": ["is", "set"]},
                "employee",
            ) or frappe.db.get_value(
                "Xavirgin Candidate",
                {"github_url": ["like", f"%/{handle}%"], "employee": ["is", "set"]},
                "employee",
            )
            if cand_emp and frappe.db.exists("Employee", cand_emp):
                emp = frappe.db.get_value("Employee", cand_emp, emp_fields, as_dict=True)
                if emp:
                    if not emp.get("custom_github_username"):
                        frappe.db.set_value("Employee", emp.name, "custom_github_username", handle, update_modified=False)
                        emp["custom_github_username"] = handle
                    return emp

    # 3. Match by commit author email if provided
    clean_email = (sender_email or "").strip().lower()
    if clean_email and "@" in clean_email and not clean_email.endswith("@users.noreply.github.com"):
        for email_field in ("company_email", "personal_email", "user_id"):
            emp = frappe.db.get_value(
                "Employee",
                {email_field: clean_email, "status": "Active"},
                emp_fields,
                as_dict=True,
            ) or frappe.db.get_value(
                "Employee",
                {email_field: clean_email},
                emp_fields,
                as_dict=True,
            )
            if emp:
                if handle and not emp.get("custom_github_username"):
                    frappe.db.set_value("Employee", emp.name, "custom_github_username", handle, update_modified=False)
                    emp["custom_github_username"] = handle
                return emp

    return {}


def compute_default_xp_for_event(event_type: str, action: str = "") -> int:
    settings = frappe.get_single("Xavirgin HR Settings")
    ev = (event_type or "").lower()
    act = (action or "").lower()
    if ev == "push":
        return int(settings.commit_xp or 5)
    if ev == "pull_request":
        if act == "merged":
            return int(settings.pr_merged_xp or 50)
        if act == "opened":
            return int(settings.pr_opened_xp or 15)
        return 0
    if ev in ("pull_request_review", "issues") and act in ("opened", "closed", "submitted", "reviewed", ""):
        return int(settings.issue_created_xp or 10)
    return 0


def sync_poa_and_employee_github_totals(employee: str, activity_date=None):
    """Updates linked Daily POA github_events_count / github_contributions_summary and Employee XP."""
    if not employee or not frappe.db.exists("Employee", employee):
        return

    if activity_date:
        p_date = getdate(activity_date)
        poa_name = frappe.db.get_value("Xavirgin Daily POA", {"employee": employee, "poa_date": p_date}, "name")
        if poa_name:
            day_events = frappe.get_all(
                "Xavirgin GitHub Activity",
                filters={"employee": employee, "activity_date": p_date},
                fields=["name", "event_type", "repository", "summary", "reference_id"],
                order_by="event_timestamp asc",
            )
            lines = [f"• [{g.event_type}] {g.summary} ({g.repository})" for g in day_events]
            frappe.db.set_value(
                "Xavirgin Daily POA",
                poa_name,
                {
                    "github_events_count": len(day_events),
                    "github_contributions_summary": "\n".join(lines) if lines else f"No GitHub events on {p_date}.",
                },
                update_modified=False,
            )

    # Rollup Employee XP
    att_xp = sum(
        int(r.xp_earned or 0)
        for r in frappe.get_all("Xavirgin Attendance Session", filters={"employee": employee}, fields=["xp_earned"])
    )
    poa_xp = sum(
        int(r.total_poa_xp or 0)
        for r in frappe.get_all("Xavirgin Daily POA", filters={"employee": employee}, fields=["total_poa_xp"])
    )
    gh_xp = sum(
        int(r.xp_awarded or 0)
        for r in frappe.get_all("Xavirgin GitHub Activity", filters={"employee": employee}, fields=["xp_awarded"])
    )
    total_xp = att_xp + poa_xp + gh_xp
    badge = compute_badge_tier(total_xp)
    frappe.db.set_value(
        "Employee",
        employee,
        {"custom_xp_points": total_xp, "custom_badge_level": badge},
        update_modified=False,
    )


def build_github_target_url(repository: str, event_type: str, reference_id: str, raw_payload: str = None) -> str:
    """Constructs a direct GitHub URL to the commit, pull request, issue, or repository."""
    if raw_payload:
        try:
            data = json.loads(raw_payload)
            if event_type == "push" and data.get("head_commit", {}).get("url"):
                return data["head_commit"]["url"]
            if event_type == "pull_request" and data.get("pull_request", {}).get("html_url"):
                return data["pull_request"]["html_url"]
            if event_type == "issues" and data.get("issue", {}).get("html_url"):
                return data["issue"]["html_url"]
            if data.get("repository", {}).get("html_url"):
                base_repo_url = data["repository"]["html_url"]
            else:
                base_repo_url = f"https://github.com/{repository}" if repository and "/" in repository else ""
        except Exception:
            base_repo_url = f"https://github.com/{repository}" if repository and "/" in repository else ""
    else:
        base_repo_url = f"https://github.com/{repository}" if repository and "/" in repository else ""

    if not base_repo_url:
        return ""

    ref = (reference_id or "").strip()
    if ref.startswith("PR #"):
        num = ref.replace("PR #", "").split()[0].strip()
        if num.isdigit():
            return f"{base_repo_url}/pull/{num}"
    elif ref.startswith("Issue #"):
        num = ref.replace("Issue #", "").split()[0].strip()
        if num.isdigit():
            return f"{base_repo_url}/issues/{num}"
    elif ref and len(ref) >= 7 and all(c in "0123456789abcdefABCDEF" for c in ref):
        return f"{base_repo_url}/commit/{ref}"

    return base_repo_url


class XavirginGitHubActivity(Document):
    def before_validate(self):
        self.normalize_dates_and_employee_mapping()

    def normalize_dates_and_employee_mapping(self):
        """Ensures activity_date is aligned to local date and maps employee from github_username/author_email."""
        if not getattr(self, "event_timestamp", None):
            self.event_timestamp = now_datetime()

        self.activity_date = getdate(self.event_timestamp)

        if not self.employee and (getattr(self, "github_username", None) or getattr(self, "author_email", None)):
            emp = resolve_employee_by_github_handle(self.github_username, getattr(self, "author_email", ""))
            if emp and emp.get("name"):
                self.employee = emp.get("name")
                self.employee_name = emp.get("employee_name")
                self.department = emp.get("department")

        if self.employee and (not self.employee_name or not self.department):
            e_info = frappe.db.get_value("Employee", self.employee, ["employee_name", "department"], as_dict=True)
            if e_info:
                self.employee_name = e_info.employee_name
                self.department = e_info.department

        if self.employee and not self.xp_awarded:
            self.xp_awarded = compute_default_xp_for_event(self.event_type, self.action)

        if self.employee and self.activity_date and not self.daily_poa:
            poa_name = frappe.db.get_value(
                "Xavirgin Daily POA",
                {"employee": self.employee, "poa_date": self.activity_date},
                "name",
            )
            if poa_name:
                self.daily_poa = poa_name

    def on_update(self):
        if self.employee:
            sync_poa_and_employee_github_totals(self.employee, self.activity_date)


@frappe.whitelist()
def remap_unmapped_github_events() -> dict:
    """Re-scans unmapped GitHub webhook records and links them to matching Employees and Daily POAs."""
    if not is_github_admin_or_lead():
        frappe.throw(
            _("Access Denied: Only Administrators and Team Leads can remap webhook events."),
            frappe.PermissionError,
        )

    unmapped = frappe.get_all(
        "Xavirgin GitHub Activity",
        filters={"employee": ["in", ["", None]]},
        fields=["name", "github_username", "author_email", "event_type", "action", "activity_date", "event_timestamp", "xp_awarded"],
    )
    linked_count = 0
    affected_employees = set()

    for ev in unmapped:
        emp = resolve_employee_by_github_handle(ev.github_username, ev.author_email)
        if emp and emp.get("name"):
            act_date = getdate(ev.event_timestamp) if ev.get("event_timestamp") else getdate(ev.activity_date)
            poa_name = frappe.db.get_value(
                "Xavirgin Daily POA",
                {"employee": emp["name"], "poa_date": act_date},
                "name",
            )
            xp_val = int(ev.xp_awarded or 0) or compute_default_xp_for_event(ev.event_type, ev.action)
            updates = {
                "employee": emp["name"],
                "employee_name": emp.get("employee_name"),
                "department": emp.get("department"),
                "activity_date": act_date,
                "xp_awarded": xp_val,
            }
            if poa_name:
                updates["daily_poa"] = poa_name
            frappe.db.set_value("Xavirgin GitHub Activity", ev.name, updates, update_modified=False)
            affected_employees.add((emp["name"], act_date))
            linked_count += 1

    for emp_id, a_date in affected_employees:
        sync_poa_and_employee_github_totals(emp_id, a_date)

    if linked_count:
        frappe.db.commit()
    return {"remapped_count": linked_count, "remaining_unmapped": len(unmapped) - linked_count}


@frappe.whitelist()
def link_activity_to_employee(activity_name: str, employee: str) -> dict:
    """Manually assigns an unmapped webhook event to an Employee and updates their GitHub handle if empty."""
    if not is_github_admin_or_lead():
        frappe.throw(_("Access Denied: Only Administrators and Team Leads can link webhook events."), frappe.PermissionError)

    doc = frappe.get_doc("Xavirgin GitHub Activity", activity_name)
    emp = frappe.db.get_value(
        "Employee",
        employee,
        ["name", "employee_name", "department", "custom_github_username"],
        as_dict=True,
    )
    if not emp:
        frappe.throw(_("Employee {0} not found.").format(employee))

    doc.employee = emp.name
    doc.employee_name = emp.employee_name
    doc.department = emp.department
    if not doc.xp_awarded:
        doc.xp_awarded = compute_default_xp_for_event(doc.event_type, doc.action)
    doc.save(ignore_permissions=True)

    if doc.github_username and doc.github_username != "unknown" and not emp.custom_github_username:
        frappe.db.set_value("Employee", emp.name, "custom_github_username", doc.github_username, update_modified=False)

    return {"status": "linked", "employee": emp.name, "employee_name": emp.employee_name}


@frappe.whitelist()
def get_github_activity_dashboard(
    date_range: str = "7d",
    start_date: str = None,
    end_date: str = None,
    department: str = None,
    employee: str = None,
    repository: str = None,
    search_text: str = None,
) -> dict:
    """Powers the Dedicated GitHub Activity Monitoring Dashboard:
    - Top KPI Summary Cards (Total Events, Total Commits via commit_count, Active Contributors, Repositories, PRs, Issues, Unmapped)
    - Employee-Wise Activity View
    - Repository-Wise Activity View
    - Webhook Event Monitoring Stream
    """
    today_d = getdate(today())
    if date_range == "today":
        s_date, e_date = today_d, today_d
    elif date_range == "yesterday":
        s_date = add_days(today_d, -1)
        e_date = s_date
    elif date_range == "30d":
        s_date, e_date = add_days(today_d, -29), today_d
    elif date_range == "custom" and start_date and end_date:
        s_date, e_date = getdate(start_date), getdate(end_date)
    else:
        s_date, e_date = add_days(today_d, -6), today_d

    fields = [
        "name",
        "delivery_id",
        "employee",
        "employee_name",
        "department",
        "github_username",
        "author_email",
        "event_type",
        "action",
        "repository",
        "branch",
        "reference_id",
        "commit_count",
        "xp_awarded",
        "activity_date",
        "event_timestamp",
        "daily_poa",
        "summary",
    ]

    filters = {"activity_date": ["between", [s_date, e_date]]}
    if employee:
        filters["employee"] = employee
    if repository:
        filters["repository"] = repository

    events = frappe.get_all(
        "Xavirgin GitHub Activity",
        filters=filters,
        fields=fields,
        order_by="event_timestamp desc, creation desc",
        limit=500,
    )

    emp_filters = {"status": "Active"}
    if department:
        emp_filters["department"] = department
    employees = frappe.get_all(
        "Employee",
        filters=emp_filters,
        fields=["name", "employee_name", "department", "designation", "custom_github_username"],
        order_by="employee_name asc",
    )
    emp_map = {e.name: e for e in employees}

    search_q = (search_text or "").strip().lower()

    kpis = {
        "total_events": 0,
        "total_commits": 0,
        "active_contributors": 0,
        "total_repositories": 0,
        "pr_opened": 0,
        "pr_merged": 0,
        "pr_closed": 0,
        "issues_opened": 0,
        "issues_closed": 0,
        "unmapped_events": 0,
        "failed_events": 0,
    }

    contributors_set = set()
    repos_map = {}
    emp_activity_map = {}
    webhook_stream = []

    for e in employees:
        if e.custom_github_username:
            emp_activity_map[e.name] = {
                "employee": e.name,
                "employee_name": e.employee_name,
                "department": e.department or "General",
                "designation": e.designation or "Developer",
                "github_username": extract_clean_handle(e.custom_github_username),
                "repos": set(),
                "commits": 0,
                "prs": 0,
                "issues": 0,
                "total_events": 0,
                "xp_earned": 0,
                "latest_timestamp": "-",
                "recent_events": [],
            }

    for ev in events:
        if department:
            ev_dept = ev.get("department") or (emp_map[ev.employee].department if ev.get("employee") in emp_map else "")
            if ev_dept != department:
                continue

        if search_q:
            hay = (
                f"{ev.get('employee_name') or ''} {ev.get('github_username') or ''} "
                f"{ev.get('repository') or ''} {ev.get('summary') or ''} "
                f"{ev.get('reference_id') or ''} {ev.get('branch') or ''}"
            ).lower()
            if search_q not in hay:
                continue

        kpis["total_events"] += 1
        ev_type = (ev.get("event_type") or "push").strip()
        ev_type_lower = ev_type.lower()
        act_lower = (ev.get("action") or "").strip().lower()
        summary_lower = (ev.get("summary") or "").lower()
        repo_name = ev.get("repository") or "Unknown Repository"
        gh_user = extract_clean_handle(ev.get("github_username")) or "unknown"

        is_commit = ev_type_lower == "push" or "commit" in ev_type_lower
        is_pr = ev_type_lower in ("pull_request", "pull_request_review")
        is_issue = ev_type_lower in ("issues", "issue_comment")

        commits_in_event = max(1, int(ev.get("commit_count") or 1)) if is_commit else 0

        if is_commit:
            kpis["total_commits"] += commits_in_event
        elif is_pr:
            if "merge" in act_lower or "merged" in summary_lower:
                kpis["pr_merged"] += 1
            elif "close" in act_lower or "closed" in summary_lower:
                kpis["pr_closed"] += 1
            else:
                kpis["pr_opened"] += 1
        elif is_issue:
            if "close" in act_lower or "closed" in summary_lower:
                kpis["issues_closed"] += 1
            else:
                kpis["issues_opened"] += 1

        if not ev.get("employee"):
            kpis["unmapped_events"] += 1
            webhook_status = "Unmapped"
        else:
            webhook_status = "Processed"

        contributors_set.add(ev.get("employee") or gh_user)

        # Repository Aggregation
        r_bucket = repos_map.setdefault(repo_name, {
            "repository": repo_name,
            "owner": repo_name.split("/")[0] if "/" in repo_name else "xavirgin",
            "total_events": 0,
            "commits": 0,
            "prs": 0,
            "issues": 0,
            "contributors": set(),
            "last_activity": (
                format_datetime(ev.event_timestamp, "dd MMM hh:mm a")
                if ev.get("event_timestamp")
                else formatdate(ev.activity_date, "dd MMM yyyy")
            ),
            "recent_commits": [],
        })
        r_bucket["total_events"] += 1
        r_bucket["contributors"].add(ev.get("employee_name") or gh_user)
        if is_commit:
            r_bucket["commits"] += commits_in_event
            if len(r_bucket["recent_commits"]) < 4:
                r_bucket["recent_commits"].append({
                    "summary": ev.get("summary") or "",
                    "author": ev.get("employee_name") or gh_user,
                    "branch": ev.get("branch") or "",
                    "sha": (ev.get("reference_id") or "")[:7],
                    "time": format_datetime(ev.event_timestamp, "dd MMM hh:mm a") if ev.get("event_timestamp") else "-",
                })
        elif is_pr:
            r_bucket["prs"] += 1
        elif is_issue:
            r_bucket["issues"] += 1

        # Employee Aggregation
        emp_id = ev.get("employee")
        if emp_id:
            e_obj = emp_map.get(emp_id) or {}
            e_bucket = emp_activity_map.setdefault(emp_id, {
                "employee": emp_id,
                "employee_name": ev.get("employee_name") or e_obj.get("employee_name") or emp_id,
                "department": ev.get("department") or e_obj.get("department") or "Engineering",
                "designation": e_obj.get("designation") or "Developer",
                "github_username": gh_user,
                "repos": set(),
                "commits": 0,
                "prs": 0,
                "issues": 0,
                "total_events": 0,
                "xp_earned": 0,
                "latest_timestamp": (
                    format_datetime(ev.event_timestamp, "dd MMM hh:mm a")
                    if ev.get("event_timestamp")
                    else formatdate(ev.activity_date, "dd MMM yyyy")
                ),
                "recent_events": [],
            })
            if e_bucket["latest_timestamp"] == "-" and ev.get("event_timestamp"):
                e_bucket["latest_timestamp"] = format_datetime(ev.event_timestamp, "dd MMM hh:mm a")
            e_bucket["repos"].add(repo_name)
            e_bucket["total_events"] += 1
            e_bucket["xp_earned"] += int(ev.get("xp_awarded") or 0)
            if is_commit:
                e_bucket["commits"] += commits_in_event
            elif is_pr:
                e_bucket["prs"] += 1
            elif is_issue:
                e_bucket["issues"] += 1

            if len(e_bucket["recent_events"]) < 5:
                e_bucket["recent_events"].append({
                    "name": ev.name,
                    "event_type": ev_type,
                    "repository": repo_name,
                    "branch": ev.get("branch") or "",
                    "summary": ev.get("summary") or "",
                    "sha": (ev.get("reference_id") or "")[:10],
                    "url": build_github_target_url(repo_name, ev_type, ev.get("reference_id") or ""),
                    "time": format_datetime(ev.event_timestamp, "dd MMM hh:mm a") if ev.get("event_timestamp") else str(ev.activity_date),
                })

        ref_id = ev.get("reference_id") or ""
        event_url = build_github_target_url(repo_name, ev_type, ref_id)

        webhook_stream.append({
            "name": ev.name,
            "delivery_id": ev.get("delivery_id") or "",
            "event_type": ev_type,
            "action": ev.get("action") or "",
            "repository": repo_name,
            "branch": ev.get("branch") or "",
            "github_username": gh_user,
            "author_email": ev.get("author_email") or "",
            "employee": emp_id or "",
            "employee_name": ev.get("employee_name") or (emp_map[emp_id].employee_name if emp_id in emp_map else ""),
            "summary": ev.get("summary") or "",
            "reference_id": ref_id,
            "short_sha": ref_id[:10] if ref_id else "",
            "commit_count": commits_in_event,
            "timestamp": format_datetime(ev.event_timestamp, "dd MMM yyyy hh:mm a") if ev.get("event_timestamp") else str(ev.activity_date),
            "status": webhook_status,
            "xp_awarded": int(ev.get("xp_awarded") or 0),
            "daily_poa": ev.get("daily_poa") or "",
            "event_url": event_url,
        })

    kpis["active_contributors"] = len(contributors_set)
    kpis["total_repositories"] = len(repos_map)

    employee_cards = []
    for emp_k, ed in emp_activity_map.items():
        ed["repo_count"] = len(ed.pop("repos", set()))
        employee_cards.append(ed)
    employee_cards.sort(key=lambda x: (x["total_events"], x["commits"]), reverse=True)

    repository_cards = []
    for rk, rd in repos_map.items():
        rd["contributor_count"] = len(rd.pop("contributors", set()))
        repository_cards.append(rd)
    repository_cards.sort(key=lambda x: x["total_events"], reverse=True)

    all_depts = frappe.get_all("Department", pluck="name")
    all_repos = frappe.get_all("Xavirgin GitHub Activity", distinct=True, pluck="repository")

    return {
        "can_manage": is_github_admin_or_lead(),
        "period": {"start_date": str(s_date), "end_date": str(e_date), "range": date_range},
        "kpis": kpis,
        "employees": employee_cards,
        "repositories": repository_cards,
        "webhooks": webhook_stream[:150],
        "filter_options": {
            "departments": sorted([d for d in all_depts if d]),
            "repositories": sorted([r for r in all_repos if r]),
        },
    }


def get_permission_query_conditions(user: str = None) -> str:
    """Allows all authenticated internal members to view GitHub activity."""
    u = user or frappe.session.user
    if not u or u == "Guest":
        return "1=0"
    return ""


def has_permission(doc, ptype="read", user=None, debug=False) -> bool:
    u = user or frappe.session.user
    if not u or u == "Guest":
        return False
    if is_github_admin_or_lead(u):
        return True
    if ptype in ("read", "select", "print", "report"):
        return True
    return False