import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_datetime, getdate, now_datetime, time_diff_in_hours, today

try:
    from xavirgin_os.api import resolve_current_user_employee_context as _resolve_user_emp_context
except ImportError:
    _resolve_user_emp_context = None


def resolve_employee_context(employee: str = None, user_id: str = None) -> dict:
    """Robustly resolves Employee record from explicit employee ID or logged-in user session.
    Handles cases where Employee.user_id is NULL by matching company_email, personal_email,
    or Xavirgin Candidate lineage, and self-heals the user_id link.
    """
    emp_fields = [
        "name",
        "employee_name",
        "user_id",
        "department",
        "designation",
        "reports_to",
        "custom_team_lead",
        "custom_is_team_lead",
        "custom_source_candidate",
        "custom_source_job_opening",
        "custom_source_offer_letter",
        "status",
        "company",
        "holiday_list",
    ]

    # 1. Explicit Employee ID lookup
    if employee and frappe.db.exists("Employee", employee):
        emp_data = frappe.db.get_value("Employee", employee, emp_fields, as_dict=True)
        if emp_data:
            emp_data["has_employee"] = True
            return emp_data

    target_user = (user_id or frappe.session.user or "").strip()
    if not target_user or target_user == "Guest":
        return {}

    # 2. Direct match on Employee.user_id (Active preferred, fallback to any)
    for filters in [{"user_id": target_user, "status": "Active"}, {"user_id": target_user}]:
        emp_data = frappe.db.get_value("Employee", filters, emp_fields, as_dict=True)
        if emp_data:
            emp_data["has_employee"] = True
            return emp_data

    # 3. Fallback via centralized xavirgin_os.api if available
    if _resolve_user_emp_context:
        try:
            ctx = _resolve_user_emp_context(target_user=target_user)
            if ctx and ctx.get("name") and frappe.db.exists("Employee", ctx["name"]):
                emp_data = frappe.db.get_value("Employee", ctx["name"], emp_fields, as_dict=True)
                if emp_data:
                    emp_data["has_employee"] = True
                    return emp_data
        except Exception:
            pass

    # 4. Match by User email against company_email or personal_email (handles NULL user_id)
    user_email = (frappe.db.get_value("User", target_user, "email") or target_user).strip().lower()
    if user_email and "@" in user_email:
        for email_field in ("company_email", "personal_email"):
            emp_data = frappe.db.get_value(
                "Employee",
                {email_field: user_email, "status": "Active"},
                emp_fields,
                as_dict=True,
            ) or frappe.db.get_value(
                "Employee",
                {email_field: user_email},
                emp_fields,
                as_dict=True,
            )
            if emp_data:
                if not emp_data.get("user_id") and frappe.db.exists("User", target_user):
                    frappe.db.set_value("Employee", emp_data["name"], "user_id", target_user, update_modified=False)
                    emp_data["user_id"] = target_user
                emp_data["has_employee"] = True
                return emp_data

        # 5. Match via Xavirgin Candidate conversion lineage
        if frappe.db.exists("DocType", "Xavirgin Candidate"):
            cand_emp = frappe.db.get_value(
                "Xavirgin Candidate",
                {"email": user_email, "employee": ["is", "set"]},
                "employee",
            )
            if cand_emp and frappe.db.exists("Employee", cand_emp):
                emp_data = frappe.db.get_value("Employee", cand_emp, emp_fields, as_dict=True)
                if emp_data:
                    if not emp_data.get("user_id") and frappe.db.exists("User", target_user):
                        frappe.db.set_value("Employee", emp_data["name"], "user_id", target_user, update_modified=False)
                        emp_data["user_id"] = target_user
                    emp_data["has_employee"] = True
                    return emp_data

    # 6. Match by User Full Name against Employee Name if unique active record exists
    user_full_name = frappe.db.get_value("User", target_user, "full_name")
    if user_full_name and target_user != "Administrator":
        matches = frappe.get_all(
            "Employee",
            filters={"employee_name": user_full_name, "status": "Active"},
            fields=emp_fields,
        )
        if len(matches) == 1:
            emp_data = matches[0]
            if not emp_data.get("user_id") and frappe.db.exists("User", target_user):
                frappe.db.set_value("Employee", emp_data["name"], "user_id", target_user, update_modified=False)
                emp_data["user_id"] = target_user
            emp_data["has_employee"] = True
            return emp_data

    # 7. Fallback for Administrator
    if target_user == "Administrator":
        admin_emp = (
            frappe.db.get_value("Employee", {"employee_name": ["like", "%Savio Babu%"], "status": "Active"}, emp_fields, as_dict=True)
            or frappe.db.get_value("Employee", {"status": "Active"}, emp_fields, as_dict=True)
        )
        if admin_emp:
            admin_emp["has_employee"] = True
            return admin_emp

    return {}


def compute_badge_tier(xp: int) -> str:
    if xp >= 5000:
        return "Legend Tier"
    if xp >= 2500:
        return "Gold Tier"
    if xp >= 1500:
        return "Silver Tier"
    return "Bronze Tier"


def get_company_holidays(employee: str) -> set:
    holiday_list = frappe.db.get_value("Employee", employee, "holiday_list")
    if not holiday_list:
        company = frappe.db.get_value("Employee", employee, "company")
        if company:
            holiday_list = frappe.db.get_value("Company", company, "default_holiday_list")
    if not holiday_list or not frappe.db.exists("DocType", "Holiday"):
        return set()
    dates = frappe.get_all("Holiday", filters={"parent": holiday_list}, pluck="holiday_date")
    return {getdate(d) for d in dates if d}


def update_daily_aggregates_and_employee_stats(employee: str, attendance_date):
    """Recalculates:
    1. Total check-in count for that employee on attendance_date.
    2. Cumulative worked hours across all sessions on attendance_date.
    3. Cumulative day classification (Full Day >= 4h, Half Day 2-4h, Short < 2h).
    4. Denormalized Employee master telemetry & linked Daily POA attendance metrics.
    """
    if not employee or not attendance_date:
        return

    day_date = getdate(attendance_date)
    day_sessions = frappe.get_all(
        "Xavirgin Attendance Session",
        filters={"employee": employee, "attendance_date": day_date},
        fields=["name", "worked_hours", "status", "check_in", "check_out"],
        order_by="check_in asc",
    )

    checkin_count = len(day_sessions)
    cumulative_hours = round(
        sum(float(s.worked_hours or 0) for s in day_sessions if s.status in ("Completed", "Corrected")),
        2,
    )

    min_full_hours = float(
        frappe.db.get_single_value("Xavirgin HR Settings", "min_daily_hours_for_full_day") or 4.0
    )
    if cumulative_hours >= min_full_hours:
        day_class = "Full Day (>= 4h)"
    elif cumulative_hours >= 2.0:
        day_class = "Half Day (2h - 4h)"
    else:
        day_class = "Short Session (< 2h)"

    for idx, sess in enumerate(day_sessions, start=1):
        row_class = "In Progress" if sess.status == "Working" else day_class
        frappe.db.set_value(
            "Xavirgin Attendance Session",
            sess.name,
            {
                "daily_session_number": idx,
                "daily_checkin_count": checkin_count,
                "daily_cumulative_hours": cumulative_hours,
                "day_classification": row_class,
            },
            update_modified=False,
        )

    # Sync attendance status into existing Xavirgin Daily POA for this date (if present)
    poa_name = frappe.db.get_value(
        "Xavirgin Daily POA",
        {"employee": employee, "poa_date": day_date},
        "name",
    )
    if poa_name:
        if day_sessions:
            active_working = any(s.status == "Working" for s in day_sessions)
            att_status = (
                f"Checked In (Active - {cumulative_hours}h logged)"
                if active_working
                else f"{day_class} ({cumulative_hours}h)"
            )
            frappe.db.set_value(
                "Xavirgin Daily POA",
                poa_name,
                {
                    "attendance_verified": 1,
                    "attendance_hours_logged": cumulative_hours,
                    "attendance_status": att_status,
                },
                update_modified=False,
            )
        else:
            frappe.db.set_value(
                "Xavirgin Daily POA",
                poa_name,
                {
                    "attendance_verified": 0,
                    "attendance_hours_logged": 0.0,
                    "attendance_status": "Not Checked In",
                },
                update_modified=False,
            )

    # Rollup across all dates for the Employee master record
    all_completed = frappe.get_all(
        "Xavirgin Attendance Session",
        filters={"employee": employee, "status": ["in", ["Completed", "Corrected"]]},
        fields=["attendance_date", "worked_hours", "work_log"],
    )
    total_hours = round(sum(float(s.worked_hours or 0) for s in all_completed), 2)
    tasks_count = sum(1 for s in all_completed if (s.work_log or "").strip())

    hours_by_day = {}
    for s in all_completed:
        d_str = str(s.attendance_date)
        hours_by_day[d_str] = hours_by_day.get(d_str, 0.0) + float(s.worked_hours or 0)
    active_days = sum(1 for _, h in hours_by_day.items() if h >= min_full_hours)

    all_xp_rows = frappe.get_all(
        "Xavirgin Attendance Session",
        filters={"employee": employee},
        fields=["xp_earned"],
    )
    att_xp = sum(int(r.xp_earned or 0) for r in all_xp_rows)

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
        {
            "custom_total_worked_hours": total_hours,
            "custom_completed_tasks_count": tasks_count,
            "custom_active_days_completed": active_days,
            "custom_xp_points": total_xp,
            "custom_badge_level": badge,
        },
        update_modified=False,
    )


class XavirginAttendanceSession(Document):
    def before_validate(self):
        self.resolve_intelligent_employee_fields()

    def resolve_intelligent_employee_fields(self):
        """Pulls biographical and organizational context automatically."""
        if not self.employee or not self.employee_name or not self.department:
            ctx = resolve_employee_context(self.employee)
            if ctx and ctx.get("name"):
                if not self.employee:
                    self.employee = ctx.get("name")
                if not self.employee_name:
                    self.employee_name = ctx.get("employee_name")
                if not self.department:
                    self.department = ctx.get("department")
                if not self.designation:
                    self.designation = ctx.get("designation")
                if not self.team_lead:
                    self.team_lead = ctx.get("custom_team_lead")

    def validate(self):
        if not self.employee:
            frappe.throw(_("Employee ID could not be determined. Please link an active Employee record."))
        if self.check_in:
            self.attendance_date = getdate(self.check_in)
        if self.check_in and self.check_out:
            if get_datetime(self.check_out) < get_datetime(self.check_in):
                frappe.throw(_("Check-Out time cannot be earlier than Check-In time."))
            self.worked_hours = round(time_diff_in_hours(self.check_out, self.check_in), 2)

    def on_update(self):
        update_daily_aggregates_and_employee_stats(self.employee, self.attendance_date)

    def after_delete(self):
        update_daily_aggregates_and_employee_stats(self.employee, self.attendance_date)


@frappe.whitelist()
def get_today_session_status(target_employee: str = None):
    """Returns the current active session, check-in count, and cumulative hours for the logged-in user."""
    ctx = resolve_employee_context(target_employee)
    if not ctx or not ctx.get("name"):
        return {"has_employee": False}

    emp_id = ctx["name"]
    current_date = getdate(today())

    active_session_doc = frappe.db.get_value(
        "Xavirgin Attendance Session",
        {"employee": emp_id, "status": "Working"},
        ["name", "attendance_date"],
        as_dict=True,
    )

    active_session = active_session_doc.name if active_session_doc else None
    query_date = active_session_doc.attendance_date if active_session_doc else current_date

    today_sessions = frappe.get_all(
        "Xavirgin Attendance Session",
        filters={"employee": emp_id, "attendance_date": query_date},
        fields=["name", "status", "worked_hours", "check_in"],
        order_by="check_in asc",
    )
    completed_hours = round(sum(float(s.worked_hours or 0) for s in today_sessions if s.status != "Working"), 2)

    return {
        "has_employee": True,
        "employee": emp_id,
        "employee_name": ctx.get("employee_name"),
        "active_session": active_session,
        "today_checkin_count": len(today_sessions),
        "today_completed_hours": completed_hours,
    }


@frappe.whitelist()
def start_session(target_employee: str = None):
    """Supports multiple daily check-ins. Blocks check-in only if an unclosed session already exists."""
    ctx = resolve_employee_context(target_employee)
    if not ctx or not ctx.get("name"):
        frappe.throw(_("No active Employee record could be resolved for user {0}.").format(frappe.session.user))

    employee = ctx["name"]
    open_session = frappe.db.get_value(
        "Xavirgin Attendance Session",
        {"employee": employee, "status": "Working"},
        "name",
    )
    if open_session:
        frappe.throw(
            _("You are already checked in (Active Session: {0}). Please Check Out before starting a new session.").format(
                open_session
            )
        )

    now_dt = now_datetime()
    current_date = getdate(now_dt)
    settings = frappe.get_single("Xavirgin HR Settings")

    prior_checkins_today = frappe.db.count(
        "Xavirgin Attendance Session",
        {"employee": employee, "attendance_date": current_date},
    )
    session_number = prior_checkins_today + 1

    xp_gained = int(settings.checkin_xp or 10) if session_number == 1 else 0

    if session_number == 1:
        holidays = get_company_holidays(employee)
        prev_work_day = add_days(current_date, -1)
        while prev_work_day.weekday() == 6 or prev_work_day in holidays:
            prev_work_day = add_days(prev_work_day, -1)

        attended_prev = frappe.db.exists(
            "Xavirgin Attendance Session",
            {"employee": employee, "attendance_date": prev_work_day},
        )
        current_streak = int(frappe.db.get_value("Employee", employee, "custom_streak_count") or 0)
        new_streak = (current_streak + 1) if attended_prev else 1
        frappe.db.set_value("Employee", employee, "custom_streak_count", new_streak, update_modified=False)

    doc = frappe.get_doc({
        "doctype": "Xavirgin Attendance Session",
        "employee": employee,
        "employee_name": ctx.get("employee_name"),
        "department": ctx.get("department"),
        "designation": ctx.get("designation"),
        "team_lead": ctx.get("custom_team_lead"),
        "attendance_date": current_date,
        "daily_session_number": session_number,
        "daily_checkin_count": session_number,
        "check_in": now_dt,
        "status": "Working",
        "xp_earned": xp_gained,
    }).insert(ignore_permissions=True)

    frappe.db.commit()

    return {
        "session": doc.name,
        "session_number": session_number,
        "xp_gained": xp_gained,
        "message": _("Check-In #{0} started ({1}). {2}").format(
            session_number,
            doc.name,
            f"+{xp_gained} XP earned!" if xp_gained else "Session tracking enabled.",
        ),
    }


@frappe.whitelist()
def stop_session(work_log: str, target_employee: str = None, session_name: str = None):
    """Allows check-out only if an active 'Working' session exists. Validates work log length."""
    settings = frappe.get_single("Xavirgin HR Settings")
    min_chars = int(getattr(settings, "min_work_log_chars", None) or 20)

    clean_log = (work_log or "").strip()
    if len(clean_log) < min_chars:
        frappe.throw(
            _("Please enter a Work Summary of at least {0} characters before checking out (currently {1} characters).").format(
                min_chars, len(clean_log)
            )
        )

    doc = None
    if session_name and frappe.db.exists("Xavirgin Attendance Session", session_name):
        doc = frappe.get_doc("Xavirgin Attendance Session", session_name)
    else:
        ctx = resolve_employee_context(target_employee)
        if not ctx or not ctx.get("name"):
            frappe.throw(_("No active Employee record found."))
        employee = ctx["name"]
        active_name = frappe.db.get_value(
            "Xavirgin Attendance Session",
            {"employee": employee, "status": "Working"},
            "name",
        )
        if active_name:
            doc = frappe.get_doc("Xavirgin Attendance Session", active_name)

    if not doc or doc.status != "Working":
        frappe.throw(_("Cannot Check Out: No active working session found. Please Check In first."))

    employee = doc.employee
    now_dt = now_datetime()
    doc.check_out = now_dt
    doc.work_log = clean_log
    doc.status = "Completed"
    session_hours = round(time_diff_in_hours(doc.check_out, doc.check_in), 2)
    doc.worked_hours = session_hours

    other_sessions_today = frappe.get_all(
        "Xavirgin Attendance Session",
        filters={
            "employee": employee,
            "attendance_date": doc.attendance_date,
            "name": ["!=", doc.name],
            "status": ["in", ["Completed", "Corrected"]],
        },
        fields=["worked_hours", "xp_earned"],
    )
    prior_hours_today = sum(float(s.worked_hours or 0) for s in other_sessions_today)
    new_cumulative_hours = round(prior_hours_today + session_hours, 2)

    checkin_xp = int(settings.checkin_xp or 10)
    full_bonus = int(settings.checkout_full_xp or 20)
    partial_bonus = int(settings.checkout_partial_xp or 5)
    min_full_hours = float(settings.min_daily_hours_for_full_day or 4.0)

    if new_cumulative_hours >= min_full_hours:
        target_daily_bonus = full_bonus
    elif new_cumulative_hours >= 1.0:
        target_daily_bonus = partial_bonus
    else:
        target_daily_bonus = 0

    total_xp_today_so_far = sum(int(s.xp_earned or 0) for s in other_sessions_today) + int(doc.xp_earned or 0)
    checkout_bonus_already_given = max(0, total_xp_today_so_far - checkin_xp)
    bonus_xp = max(0, target_daily_bonus - checkout_bonus_already_given)

    doc.xp_earned = int(doc.xp_earned or 0) + bonus_xp
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    total_checkins_today = len(other_sessions_today) + 1
    return {
        "session": doc.name,
        "session_number": total_checkins_today,
        "session_hours": session_hours,
        "daily_cumulative_hours": new_cumulative_hours,
        "bonus_xp": bonus_xp,
        "message": _("Check-Out #{0} Complete: {1}h this session | {2}h cumulative today (+{3} Bonus XP).").format(
            total_checkins_today, session_hours, new_cumulative_hours, bonus_xp
        ),
    }

def get_permission_query_conditions(user: str = None) -> str:
    """Allows all authenticated internal staff to view attendance analytics while keeping guest users blocked."""
    user = user or frappe.session.user
    if user == "Guest":
        return "1=0"
    return ""


def has_permission(doc, ptype="read", user=None, debug=False) -> bool:
    """Read is public to team members; write/edit is restricted to Admins, Team Leads (for squad), and self."""
    user = user or frappe.session.user
    if user == "Guest":
        return False

    roles = set(frappe.get_roles(user))
    if roles.intersection({"System Manager", "Administrator", "Xavirgin HR Admin", "Xavirgin HR Manager"}):
        return True

    if ptype in ("read", "select", "print", "report"):
        return True

    if ptype == "delete":
        return False

    # Check ownership / team-lead scope
    target_emp = getattr(doc, "employee", None)
    ctx = resolve_employee_context(user_id=user)
    if not ctx or not ctx.get("name"):
        return False

    my_emp = ctx.get("name")
    if target_emp == my_emp:
        return True

    if "Xavirgin Team Lead" in roles:
        lead_dept = ctx.get("department")
        doc_dept = getattr(doc, "department", None)
        if lead_dept and doc_dept and lead_dept == doc_dept:
            return True

    return False