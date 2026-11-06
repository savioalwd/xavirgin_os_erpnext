import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import format_datetime, get_datetime, getdate, now_datetime, time_diff_in_hours, today
from xavirgin_os.ai import generate_employee_poa_summary
from xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session import (
    compute_badge_tier,
    resolve_employee_context,
)


def is_admin_user(user: str = None) -> bool:
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    roles = set(frappe.get_roles(user))
    return bool(roles.intersection({"System Manager", "Xavirgin HR Admin", "Xavirgin HR Manager"}))


def is_team_lead_user(user: str = None, emp_ctx: dict = None) -> bool:
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    if "Xavirgin Team Lead" in roles:
        return True
    emp_ctx = emp_ctx or resolve_employee_context(user_id=user)
    if emp_ctx and emp_ctx.get("custom_is_team_lead"):
        return True
    return False


def can_user_manage_employee_poa(target_employee: str, user: str = None) -> bool:
    """Determines whether `user` is authorized to create/edit a Daily POA for `target_employee`.
    - Administrators / HR Admins: All employees.
    - Team Leads: Own record + employees in their department or reporting to them (`reports_to` / `custom_team_lead`).
    - Interns / Regular Employees: Strictly their own Employee record only.
    """
    user = user or frappe.session.user
    if is_admin_user(user):
        return True

    session_ctx = resolve_employee_context(user_id=user)
    if not session_ctx or not session_ctx.get("name"):
        return False

    session_emp = session_ctx.get("name")
    if not target_employee or target_employee == session_emp:
        return True

    if is_team_lead_user(user, session_ctx):
        target_info = frappe.db.get_value(
            "Employee",
            target_employee,
            ["department", "reports_to", "custom_team_lead"],
            as_dict=True,
        )
        if not target_info:
            return False
        if target_info.get("reports_to") == session_emp or target_info.get("custom_team_lead") == session_emp:
            return True
        if session_ctx.get("department") and target_info.get("department") == session_ctx.get("department"):
            return True

    return False


class XavirginDailyPOA(Document):
    def before_validate(self):
        self.resolve_intelligent_employee_fields()
        self.sync_live_attendance_and_github()
        self.calculate_poa_metrics_and_xp()

    def validate(self):
        if not self.employee:
            frappe.throw(
                _("Your user account ({0}) is not linked to an active Employee record. Please contact HR.").format(
                    frappe.session.user
                )
            )
        self.validate_employee_identity_and_permissions()
        self.validate_unique_daily_poa()
        self.validate_task_explanations()

    def on_update(self):
        self.rollup_employee_gamification_totals()

    def after_delete(self):
        self.rollup_employee_gamification_totals()

    def resolve_intelligent_employee_fields(self):
        """Automatically resolves Employee ID from session if missing or unauthorized,
        and populates Name, Department, Designation, User ID, and Reporting Manager.
        """
        session_ctx = resolve_employee_context(user_id=frappe.session.user)

        # If employee is blank, or if a non-admin/non-lead tried to set someone else's employee ID
        if not self.employee:
            if session_ctx and session_ctx.get("name"):
                self.employee = session_ctx.get("name")
        elif not is_admin_user() and not is_team_lead_user(emp_ctx=session_ctx):
            # Force intern/regular employee to their own Employee identity on new records
            if self.is_new() and session_ctx and session_ctx.get("name"):
                self.employee = session_ctx.get("name")

        ctx = resolve_employee_context(employee=self.employee, user_id=frappe.session.user)
        if ctx and ctx.get("name"):
            self.employee = ctx.get("name")
            self.employee_name = ctx.get("employee_name")
            self.department = ctx.get("department")
            self.designation = ctx.get("designation")
            emp_extra = frappe.db.get_value(
                "Employee",
                self.employee,
                ["user_id", "reports_to", "custom_team_lead"],
                as_dict=True,
            ) or {}
            self.user_id = emp_extra.get("user_id") or ctx.get("user_id")
            self.reporting_manager = emp_extra.get("reports_to") or emp_extra.get("custom_team_lead")

        if not self.poa_date:
            self.poa_date = today()

    def validate_employee_identity_and_permissions(self):
        """Enforces server-side authorization rules for creating/updating a POA."""
        if not can_user_manage_employee_poa(self.employee, frappe.session.user):
            frappe.throw(
                _("Access Denied: You are only authorized to create or modify your own Daily POA."),
                frappe.PermissionError,
            )

    def validate_unique_daily_poa(self):
        """Guarantees strictly 1 plan per employee per calendar date."""
        existing = frappe.db.get_value(
            "Xavirgin Daily POA",
            {
                "employee": self.employee,
                "poa_date": getdate(self.poa_date),
                "name": ["!=", self.name or ""],
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("A Daily Work Plan ({0}) already exists for {1} on {2}. Please open and update that record.").format(
                    existing, self.employee_name or self.employee, self.poa_date
                )
            )

    def validate_task_explanations(self):
        """Ensures incomplete tasks have explanations when finishing the day."""
        is_completed_state = self.status in ("Completed for Today", "Submitted (EOD Report)")
        for idx, row in enumerate(self.tasks, start=1):
            if row.status in ("Blocked", "Stuck / Blocked") and not (row.blocker_reason or "").strip():
                frappe.throw(
                    _("Task #{0} ('{1}') is marked as Blocked. Please type a short reason explaining what is stuck.").format(
                        idx, row.task_title
                    )
                )
            if is_completed_state and row.status in ("Pending", "Planned", "In Progress") and not (row.blocker_reason or "").strip():
                frappe.throw(
                    _("Task #{0} ('{1}') was not finished. Please mark it as Completed, Carried Forward, or explain what was left in the reason column.").format(
                        idx, row.task_title
                    )
                )

    def sync_live_attendance_and_github(self):
        """Pulls same-day attendance sessions (including active running time) and GitHub logs idempotently."""
        if not self.employee or not self.poa_date:
            return
        p_date = getdate(self.poa_date)

        # 1. Attendance Sync (Multi-session aware + active session live timer)
        sessions = frappe.get_all(
            "Xavirgin Attendance Session",
            filters={"employee": self.employee, "attendance_date": p_date},
            fields=["name", "status", "worked_hours", "day_classification", "check_in", "check_out", "work_log"],
            order_by="check_in asc",
        )
        if sessions:
            self.attendance_verified = 1
            total_att_hours = 0.0
            active_working = False
            now_dt = now_datetime()

            for s in sessions:
                if s.status == "Working" and s.check_in:
                    active_working = True
                    live_hrs = max(0.0, time_diff_in_hours(now_dt, s.check_in))
                    total_att_hours += live_hrs
                else:
                    total_att_hours += float(s.worked_hours or 0)

            total_att_hours = round(total_att_hours, 2)
            self.attendance_hours_logged = total_att_hours
            self.attendance_status = (
                f"Checked In ({len(sessions)} Session{'s' if len(sessions) > 1 else ''} - {total_att_hours}h)"
                if active_working
                else f"{sessions[-1].day_classification} ({total_att_hours}h across {len(sessions)} session{'s' if len(sessions) > 1 else ''})"
            )

            # Auto-populate task deliverables from attendance work_log if POA tasks table is empty on creation
            if not self.tasks:
                for idx, s in enumerate(sessions, start=1):
                    clean_log = (s.work_log or "").strip()
                    if clean_log:
                        hrs = round(float(s.worked_hours or 1.0), 1) or 1.0
                        self.append("tasks", {
                            "task_title": clean_log[:140],
                            "task_type": "Code/LogicImplementation",
                            "priority": "Medium",
                            "status": "Completed" if s.status in ("Completed", "Corrected") else "In Progress",
                            "expected_hours": hrs,
                            "actual_hours": hrs if s.status in ("Completed", "Corrected") else 0.0,
                            "description": f"Synced from Attendance Session {s.name} (Session #{idx}):\n{clean_log}",
                        })
        else:
            self.attendance_verified = 0
            self.attendance_hours_logged = 0.0
            self.attendance_status = "Not Checked In"

        # 2. GitHub Sync
        gh_events = frappe.get_all(
            "Xavirgin GitHub Activity",
            filters={"employee": self.employee, "activity_date": p_date},
            fields=["name", "event_type", "repository", "summary", "reference_id"],
            order_by="event_timestamp asc",
        )
        self.github_events_count = len(gh_events)
        if gh_events:
            lines = [f"• [{g.event_type}] {g.summary} ({g.repository})" for g in gh_events]
            self.github_contributions_summary = "\n".join(lines)

    def calculate_poa_metrics_and_xp(self):
        """Calculates task tallies, blockers, and points."""
        settings = frappe.get_single("Xavirgin HR Settings")
        base_xp = int(settings.poa_base_xp or 15)
        bonus_xp = int(settings.poa_duration_bonus_xp or 10)
        unverified_xp = int(settings.poa_unverified_xp or 2)

        planned_hrs = 0.0
        actual_hrs = 0.0
        completed = 0
        pending = 0
        blocked = 0
        total_xp = 0
        blocker_lines = []

        for row in self.tasks:
            planned_hrs += float(row.expected_hours or 0)
            actual_hrs += float(row.actual_hours or 0)

            if row.status == "Completed":
                completed += 1
                if self.attendance_verified:
                    task_xp = base_xp + (bonus_xp if float(row.actual_hours or 0) >= 2.0 else 0)
                else:
                    task_xp = unverified_xp
                row.xp_awarded = task_xp
                total_xp += task_xp
            else:
                row.xp_awarded = 0
                if row.status in ("Blocked", "Stuck / Blocked"):
                    blocked += 1
                    blocker_lines.append(f"• {row.task_title}: {row.blocker_reason or 'No reason specified'}")
                elif row.status in ("Planned", "In Progress", "Pending", "InProgress"):
                    pending += 1

        self.total_planned_hours = round(planned_hrs, 2)
        self.total_actual_hours = round(actual_hrs, 2)
        self.completed_tasks_count = completed
        self.pending_tasks_count = pending
        self.blocked_tasks_count = blocked
        self.total_poa_xp = total_xp
        self.blockers_summary = "\n".join(blocker_lines) if blocker_lines else "No active blockers."

        if blocked > 0 and self.status not in ("Completed for Today", "Submitted (EOD Report)"):
            self.status = "Stuck / Blocked"

    def rollup_employee_gamification_totals(self):
        """Updates Employee master XP and completed task counters."""
        if not self.employee or not frappe.db.exists("Employee", self.employee):
            return

        att_xp = sum(
            int(r.xp_earned or 0)
            for r in frappe.get_all("Xavirgin Attendance Session", filters={"employee": self.employee}, fields=["xp_earned"])
        )
        poa_rows = frappe.get_all(
            "Xavirgin Daily POA",
            filters={"employee": self.employee},
            fields=["total_poa_xp", "completed_tasks_count"],
        )
        poa_xp = sum(int(r.total_poa_xp or 0) for r in poa_rows)
        poa_tasks = sum(int(r.completed_tasks_count or 0) for r in poa_rows)

        gh_xp = sum(
            int(r.xp_awarded or 0)
            for r in frappe.get_all("Xavirgin GitHub Activity", filters={"employee": self.employee}, fields=["xp_awarded"])
        )

        grand_total_xp = att_xp + poa_xp + gh_xp
        badge = compute_badge_tier(grand_total_xp)

        frappe.db.set_value(
            "Employee",
            self.employee,
            {
                "custom_xp_points": grand_total_xp,
                "custom_badge_level": badge,
                "custom_completed_tasks_count": poa_tasks,
            },
            update_modified=False,
        )

    @frappe.whitelist()
    def sync_deliverables_from_attendance(self):
        """Idempotently pulls work logs from the day's Attendance Sessions into Task Deliverables."""
        self.validate_employee_identity_and_permissions()
        self.sync_live_attendance_and_github()

        p_date = getdate(self.poa_date)
        sessions = frappe.get_all(
            "Xavirgin Attendance Session",
            filters={"employee": self.employee, "attendance_date": p_date},
            fields=["name", "status", "worked_hours", "work_log", "check_in", "check_out"],
            order_by="check_in asc",
        )

        existing_descriptions = {(t.description or "").strip() for t in self.tasks}
        existing_titles = {(t.task_title or "").strip().lower() for t in self.tasks}
        added = 0

        for idx, s in enumerate(sessions, start=1):
            clean_log = (s.work_log or "").strip()
            if not clean_log:
                continue
            title_candidate = clean_log[:140]
            marker = f"Attendance Session {s.name}"
            if title_candidate.lower() in existing_titles or any(marker in d for d in existing_descriptions):
                continue

            hrs = round(float(s.worked_hours or 1.0), 1) or 1.0
            self.append("tasks", {
                "task_title": title_candidate,
                "task_type": "Code/LogicImplementation",
                "priority": "Medium",
                "status": "Completed" if s.status in ("Completed", "Corrected") else "In Progress",
                "expected_hours": hrs,
                "actual_hours": hrs if s.status in ("Completed", "Corrected") else 0.0,
                "description": f"Synced from {marker} (Session #{idx}):\n{clean_log}",
            })
            existing_titles.add(title_candidate.lower())
            added += 1

        self.calculate_poa_metrics_and_xp()
        if not self.is_new():
            self.save()

        return {
            "added_tasks": added,
            "attendance_status": self.attendance_status,
            "attendance_hours_logged": self.attendance_hours_logged,
            "attendance_verified": self.attendance_verified,
            "sessions_count": len(sessions),
        }

    @frappe.whitelist()
    def carry_forward_unfinished_tasks(self):
        """Pulls unfinished tasks from previous plans idempotently."""
        self.validate_employee_identity_and_permissions()
        prev_poas = frappe.get_all(
            "Xavirgin Daily POA",
            filters={
                "employee": self.employee,
                "poa_date": ["<", getdate(self.poa_date)],
            },
            fields=["name", "poa_date"],
            order_by="poa_date desc",
            limit=1,
        )
        if not prev_poas:
            return 0

        prev_doc = frappe.get_doc("Xavirgin Daily POA", prev_poas[0].name)
        existing_titles = {(t.task_title or "").strip().lower() for t in self.tasks}
        added = 0

        for t in prev_doc.tasks:
            if t.status in ("Planned", "In Progress", "InProgress", "Pending", "Blocked", "Stuck / Blocked", "Carried Forward", "CarriedForward"):
                if (t.task_title or "").strip().lower() not in existing_titles:
                    self.append("tasks", {
                        "task_title": t.task_title,
                        "task_type": t.task_type,
                        "priority": t.priority,
                        "status": "In Progress",
                        "expected_hours": t.expected_hours,
                        "actual_hours": 0.0,
                        "description": t.description,
                        "blocker_reason": t.blocker_reason,
                        "carried_from_poa": prev_doc.name,
                    })
                    existing_titles.add((t.task_title or "").strip().lower())
                    added += 1

        if added > 0 and not self.is_new():
            self.save()
        return added

    @frappe.whitelist()
    def submit_eod_report(self):
        """Direct submission when all tasks are finalized."""
        self.validate_employee_identity_and_permissions()
        self.status = "Completed for Today"
        self.submitted_at = now_datetime()
        self.save()
        return self.name

    @frappe.whitelist()
    def submit_eod_report_guided(self, action_choice: str, reason: str = ""):
        """Handles unfinished tasks cleanly through guided dialog options."""
        self.validate_employee_identity_and_permissions()
        for row in self.tasks:
            if row.status in ("Planned", "In Progress", "InProgress", "Pending"):
                if "Mark all as Completed" in action_choice or "MarkallasCompleted" in action_choice:
                    row.status = "Completed"
                    if not row.actual_hours or float(row.actual_hours) == 0:
                        row.actual_hours = row.expected_hours
                elif "Blocker" in action_choice or "Reason" in action_choice:
                    row.blocker_reason = reason or "Work in progress; will continue next session."
                elif "Move" in action_choice or "tomorrow" in action_choice:
                    row.status = "Carried Forward"
                    row.blocker_reason = "Carried forward to next work plan."

        self.status = "Completed for Today"
        self.submitted_at = now_datetime()
        self.save()
        return self.name

    @frappe.whitelist()
    def generate_individual_ai_summary(self):
        """Generates AI performance summary."""
        self.validate_employee_identity_and_permissions()
        html_summary = generate_employee_poa_summary(self.name)
        self.db_set("ai_summary", html_summary, update_modified=False)
        return html_summary


# ==============================================================================
# Whitelisted APIs for Client Auto-Linking, Attendance Telemetry & Kanban Board
# ==============================================================================

@frappe.whitelist()
def get_session_poa_Bootstrap(employee: str = None, poa_date: str = None):
    """Single atomic call for the Daily POA form:
    1. Resolves the logged-in user's Employee context (or target employee if authorized).
    2. Checks if a Daily POA already exists for `(employee, poa_date)`.
    3. Fetches live Attendance Sessions (with check-in/out times & work logs).
    4. Fetches cross-module telemetry counts (Candidate, Interviews, Attendance, GitHub).
    5. Returns edit authorization flags (`can_edit`, `is_admin`, `is_team_lead`).
    """
    session_ctx = resolve_employee_context(user_id=frappe.session.user)
    admin_flag = is_admin_user()
    lead_flag = is_team_lead_user(emp_ctx=session_ctx)

    target_emp = employee
    if not target_emp or (not admin_flag and not lead_flag):
        if session_ctx and session_ctx.get("name"):
            target_emp = session_ctx.get("name")

    emp_ctx = resolve_employee_context(employee=target_emp, user_id=frappe.session.user)
    if not emp_ctx or not emp_ctx.get("name"):
        return {
            "has_employee": False,
            "is_admin": admin_flag,
            "is_team_lead": lead_flag,
            "can_edit": admin_flag,
        }

    emp_id = emp_ctx["name"]
    target_date = getdate(poa_date or today())
    can_edit = can_user_manage_employee_poa(emp_id, frappe.session.user)

    emp_extra = frappe.db.get_value(
        "Employee",
        emp_id,
        [
            "user_id",
            "reports_to",
            "custom_team_lead",
            "custom_source_candidate",
            "custom_source_job_opening",
            "custom_source_offer_letter",
            "custom_xp_points",
            "custom_badge_level",
            "custom_active_days_completed",
        ],
        as_dict=True,
    ) or {}

    existing_poa = frappe.db.get_value(
        "Xavirgin Daily POA",
        {"employee": emp_id, "poa_date": target_date},
        ["name", "status"],
        as_dict=True,
    )

    # Attendance Sessions for target_date
    sessions = frappe.get_all(
        "Xavirgin Attendance Session",
        filters={"employee": emp_id, "attendance_date": target_date},
        fields=[
            "name",
            "daily_session_number",
            "status",
            "day_classification",
            "check_in",
            "check_out",
            "worked_hours",
            "xp_earned",
            "work_log",
        ],
        order_by="check_in asc",
    )

    now_dt = now_datetime()
    total_att_hours = 0.0
    active_working = False
    formatted_sessions = []

    for idx, s in enumerate(sessions, start=1):
        hrs = float(s.worked_hours or 0)
        if s.status == "Working" and s.check_in:
            active_working = True
            hrs = round(max(0.0, time_diff_in_hours(now_dt, s.check_in)), 2)
        total_att_hours += hrs
        formatted_sessions.append({
            "name": s.name,
            "session_number": s.daily_session_number or idx,
            "status": s.status,
            "check_in": format_datetime(s.check_in, "hh:mm a") if s.check_in else "-",
            "check_out": format_datetime(s.check_out, "hh:mm a") if s.check_out else "Active Now",
            "worked_hours": round(hrs, 2),
            "work_log": s.work_log or "",
        })

    total_att_hours = round(total_att_hours, 2)
    if sessions:
        att_status = (
            f"Checked In ({len(sessions)} Session{'s' if len(sessions) > 1 else ''} - {total_att_hours}h)"
            if active_working
            else f"{sessions[-1].day_classification} ({total_att_hours}h across {len(sessions)} session{'s' if len(sessions) > 1 else ''})"
        )
        att_verified = 1
    else:
        att_status = "Not Checked In"
        att_verified = 0

    # Related HR & Engineering Telemetry Counts
    candidate_id = emp_extra.get("custom_source_candidate")
    if not candidate_id and frappe.db.exists("DocType", "Xavirgin Candidate"):
        candidate_id = frappe.db.get_value("Xavirgin Candidate", {"employee": emp_id}, "name")

    interviews_count = 0
    if candidate_id and frappe.db.exists("DocType", "Xavirgin Interview"):
        interviews_count = frappe.db.count("Xavirgin Interview", {"candidate": candidate_id})

    total_attendance_count = frappe.db.count("Xavirgin Attendance Session", {"employee": emp_id})
    github_today_count = frappe.db.count("Xavirgin GitHub Activity", {"employee": emp_id, "activity_date": target_date})
    github_total_count = frappe.db.count("Xavirgin GitHub Activity", {"employee": emp_id})

    return {
        "has_employee": True,
        "session_employee": session_ctx.get("name") if session_ctx else None,
        "employee": emp_id,
        "employee_name": emp_ctx.get("employee_name"),
        "user_id": emp_extra.get("user_id") or emp_ctx.get("user_id"),
        "department": emp_ctx.get("department"),
        "designation": emp_ctx.get("designation"),
        "reporting_manager": emp_extra.get("reports_to") or emp_extra.get("custom_team_lead"),
        "poa_date": str(target_date),
        "existing_poa": existing_poa,
        "can_edit": can_edit,
        "is_admin": admin_flag,
        "is_team_lead": lead_flag,
        "attendance": {
            "verified": att_verified,
            "status": att_status,
            "hours_logged": total_att_hours,
            "active_working": active_working,
            "sessions": formatted_sessions,
        },
        "telemetry": {
            "employee": emp_id,
            "candidate": candidate_id,
            "job_opening": emp_extra.get("custom_source_job_opening"),
            "offer_letter": emp_extra.get("custom_source_offer_letter"),
            "interviews_count": interviews_count,
            "today_attendance_count": len(sessions),
            "total_attendance_count": total_attendance_count,
            "github_today_count": github_today_count,
            "github_total_count": github_total_count,
            "xp_points": int(emp_extra.get("custom_xp_points") or 0),
            "badge_level": emp_extra.get("custom_badge_level") or "Bronze Tier",
            "active_days": int(emp_extra.get("custom_active_days_completed") or 0),
        },
    }


@frappe.whitelist()
def get_department_poa_dashboard(target_date: str = None, department: str = None):
    """Computes department-wise POA submission metrics, attendance status, and employee lists
    for the Kanban/Card Dashboard without double-counting.
    """
    q_date = getdate(target_date or today())
    session_ctx = resolve_employee_context(user_id=frappe.session.user)
    admin_flag = is_admin_user()
    lead_flag = is_team_lead_user(emp_ctx=session_ctx)

    emp_filters = {"status": "Active"}
    if department:
        emp_filters["department"] = department

    active_employees = frappe.get_all(
        "Employee",
        filters=emp_filters,
        fields=[
            "name",
            "employee_name",
            "department",
            "designation",
            "reports_to",
            "custom_team_lead",
            "custom_is_team_lead",
            "custom_xp_points",
            "custom_badge_level",
        ],
        order_by="department asc, employee_name asc",
    )

    poas_on_date = frappe.get_all(
        "Xavirgin Daily POA",
        filters={"poa_date": q_date},
        fields=[
            "name",
            "employee",
            "employee_name",
            "department",
            "status",
            "attendance_status",
            "attendance_verified",
            "attendance_hours_logged",
            "completed_tasks_count",
            "pending_tasks_count",
            "blocked_tasks_count",
            "total_actual_hours",
            "total_poa_xp",
            "submitted_at",
        ],
        order_by="modified desc",
    )
    # Deduplicate by employee (1 POA per employee per date)
    poa_by_emp = {}
    for p in poas_on_date:
        if p.employee and p.employee not in poa_by_emp:
            poa_by_emp[p.employee] = p

    # Attendance sessions on target_date
    att_sessions = frappe.get_all(
        "Xavirgin Attendance Session",
        filters={"attendance_date": q_date},
        fields=["employee", "status", "worked_hours", "check_in"],
    )
    now_dt = now_datetime()
    att_by_emp = {}
    for s in att_sessions:
        if not s.employee:
            continue
        entry = att_by_emp.setdefault(s.employee, {"sessions": 0, "hours": 0.0, "working": False})
        entry["sessions"] += 1
        if s.status == "Working" and s.check_in:
            entry["working"] = True
            entry["hours"] += max(0.0, time_diff_in_hours(now_dt, s.check_in))
        else:
            entry["hours"] += float(s.worked_hours or 0)

    dept_map = {}
    totals = {
        "total_employees": 0,
        "submitted_count": 0,
        "in_progress_count": 0,
        "blocked_count": 0,
        "missing_count": 0,
        "checked_in_count": 0,
    }

    seen_employees = set()
    for emp in active_employees:
        if emp.name in seen_employees:
            continue
        seen_employees.add(emp.name)

        dept_name = emp.department or "Unassigned Squad"
        dept_bucket = dept_map.setdefault(dept_name, {
            "department": dept_name,
            "total_employees": 0,
            "submitted_count": 0,
            "in_progress_count": 0,
            "blocked_count": 0,
            "missing_count": 0,
            "submission_pct": 0.0,
            "is_my_department": bool(session_ctx and session_ctx.get("department") == dept_name),
            "employees": [],
        })

        poa = poa_by_emp.get(emp.name)
        att = att_by_emp.get(emp.name, {"sessions": 0, "hours": 0.0, "working": False})
        att_hours = round(att["hours"], 2)

        if att["sessions"] > 0:
            totals["checked_in_count"] += 1

        if poa:
            raw_status = poa.status or "Morning Plan"
            if raw_status in ("Completed for Today", "Submitted (EOD Report)"):
                ui_category = "Submitted"
                dept_bucket["submitted_count"] += 1
                totals["submitted_count"] += 1
            elif raw_status in ("Stuck / Blocked", "Blocked"):
                ui_category = "Blocked"
                dept_bucket["blocked_count"] += 1
                dept_bucket["in_progress_count"] += 1
                totals["blocked_count"] += 1
                totals["in_progress_count"] += 1
            else:
                ui_category = "In Progress"
                dept_bucket["in_progress_count"] += 1
                totals["in_progress_count"] += 1
        else:
            raw_status = "Missing"
            ui_category = "Missing"
            dept_bucket["missing_count"] += 1
            totals["missing_count"] += 1

        dept_bucket["total_employees"] += 1
        totals["total_employees"] += 1

        can_manage_member = can_user_manage_employee_poa(emp.name, frappe.session.user)

        dept_bucket["employees"].append({
            "employee": emp.name,
            "employee_name": emp.employee_name,
            "designation": emp.designation or "Team Member",
            "is_team_lead": bool(emp.custom_is_team_lead),
            "poa_name": poa.name if poa else None,
            "poa_status": raw_status,
            "ui_category": ui_category,
            "completed_tasks": int(poa.completed_tasks_count or 0) if poa else 0,
            "pending_tasks": int(poa.pending_tasks_count or 0) if poa else 0,
            "blocked_tasks": int(poa.blocked_tasks_count or 0) if poa else 0,
            "poa_xp": int(poa.total_poa_xp or 0) if poa else 0,
            "attendance_sessions": att["sessions"],
            "attendance_hours": att_hours,
            "attendance_working": att["working"],
            "can_manage": can_manage_member,
        })

    departments_list = []
    for d_name, d_data in dept_map.items():
        active_or_submitted = d_data["submitted_count"] + d_data["in_progress_count"]
        d_data["submission_pct"] = (
            round((active_or_submitted / d_data["total_employees"]) * 100, 1)
            if d_data["total_employees"] > 0
            else 0.0
        )
        d_data["eod_completed_pct"] = (
            round((d_data["submitted_count"] / d_data["total_employees"]) * 100, 1)
            if d_data["total_employees"] > 0
            else 0.0
        )
        departments_list.append(d_data)

    # Sort user's own department first, then alphabetically
    departments_list.sort(key=lambda x: (0 if x["is_my_department"] else 1, x["department"]))

    total_emp = totals["total_employees"]
    totals["overall_submission_pct"] = (
        round(((totals["submitted_count"] + totals["in_progress_count"]) / total_emp) * 100, 1)
        if total_emp > 0
        else 0.0
    )

    my_today_poa = None
    if session_ctx and session_ctx.get("name"):
        my_today_poa = frappe.db.get_value(
            "Xavirgin Daily POA",
            {"employee": session_ctx["name"], "poa_date": q_date},
            "name",
        )

    return {
        "date": str(q_date),
        "session_employee": session_ctx.get("name") if session_ctx else None,
        "session_employee_name": session_ctx.get("employee_name") if session_ctx else None,
        "session_department": session_ctx.get("department") if session_ctx else None,
        "my_poa_for_date": my_today_poa,
        "is_admin": admin_flag,
        "is_team_lead": lead_flag,
        "totals": totals,
        "departments": departments_list,
    }


# ==============================================================================
# Module-Level Frappe Permission Hooks (Visibility vs. Edit Separation)
# ==============================================================================

def get_permission_query_conditions(user: str = None) -> str:
    """Allows all authenticated workspace members (Admins, Team Leads, Interns, Employees)
    to VIEW all Daily POA records across the organization.
    Write/Edit restrictions are enforced separately in `has_permission` and `validate`.
    """
    user = user or frappe.session.user
    if user == "Guest":
        return "1=0"
    return ""


def has_permission(doc, ptype="read", user=None, debug=False) -> bool:
    """Separates read visibility from write/edit permissions:
    - Read / Select / Print / Export: Allowed for all internal authenticated users.
    - Create / Write / Submit:
        * Admins: Allowed everywhere.
        * Team Leads: Own record + members in their department / squad.
        * Interns / Employees: Only their own Employee record.
    - Delete: Admins only.
    """
    user = user or frappe.session.user
    if user == "Guest":
        return False

    roles = set(frappe.get_roles(user))
    if roles.intersection({"System Manager", "Administrator", "Xavirgin HR Admin", "Xavirgin HR Manager"}):
        return True

    # 1. Allow reading for all internal staff
    if ptype in ("read", "select", "print", "report", "export"):
        return True

    if ptype == "delete":
        return False

    # 2. String check when Frappe calls has_permission for doc creation check
    if isinstance(doc, str) or not doc:
        return True

    # 3. Write / Save validation
    target_emp = getattr(doc, "employee", None)
    if not target_emp:
        return True

    return can_user_manage_employee_poa(target_emp, user)