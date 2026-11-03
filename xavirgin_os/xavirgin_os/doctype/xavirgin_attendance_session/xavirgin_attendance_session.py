import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_datetime, getdate, now_datetime, time_diff_in_hours, today

from xavirgin_os.api import resolve_current_user_employee_context as _resolve_user_emp_context


def resolve_employee_context(employee: str = None, user_id: str = None) -> dict:
	"""Bridge resolver that inspects explicit employee ID first, or routes

	directly into the centralized xavirgin_os.api context resolution chain.
	"""
	if employee and frappe.db.exists("Employee", employee):
		emp_data = frappe.db.get_value(
			"Employee",
			employee,
			[
				"name",
				"employee_name",
				"department",
				"designation",
				"custom_team_lead",
				"status",
				"company",
				"holiday_list",
			],
			as_dict=True,
		)
		if emp_data and emp_data.status == "Active":
			emp_data["has_employee"] = True
			return emp_data

	# Centralized fallback via user_id, email, or candidate-conversion lineage
	ctx = _resolve_user_emp_context(target_user=user_id or frappe.session.user)
	if ctx and ctx.get("has_employee"):
		# Ensure holiday_list and company are present for streak calculations
		extra = frappe.db.get_value("Employee", ctx["name"], ["company", "holiday_list"], as_dict=True) or {}
		ctx.update(extra)
		return ctx

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
	4. Denormalized Employee master telemetry.
	"""
	if not employee or not attendance_date:
		return

	day_date = getdate(attendance_date)
	day_sessions = frappe.get_all(
		"Xavirgin Attendance Session",
		filters={"employee": employee, "attendance_date": day_date},
		fields=["name", "worked_hours", "status", "check_in"],
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
	total_xp = sum(int(r.xp_earned or 0) for r in all_xp_rows)
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
		ctx = resolve_employee_context(self.employee)
		if ctx:
			self.employee = ctx.get("name")
			self.employee_name = ctx.get("employee_name")
			self.department = ctx.get("department")
			self.designation = ctx.get("designation")
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
def get_today_session_status():
	"""Returns the current active session, check-in count, and cumulative hours for the logged-in user."""
	ctx = resolve_employee_context()
	if not ctx or not ctx.get("name"):
		return {"has_employee": False}

	emp_id = ctx["name"]
	current_date = getdate(today())
	today_sessions = frappe.get_all(
		"Xavirgin Attendance Session",
		filters={"employee": emp_id, "attendance_date": current_date},
		fields=["name", "status", "worked_hours", "check_in"],
		order_by="check_in asc",
	)
	active_session = next((s.name for s in today_sessions if s.status == "Working"), None)
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

	current_date = getdate(today())
	settings = frappe.get_single("Xavirgin HR Settings")

	prior_checkins_today = frappe.db.count(
		"Xavirgin Attendance Session",
		{"employee": employee, "attendance_date": current_date},
	)
	session_number = prior_checkins_today + 1

	# Award Check-In XP only on Session #1 of the day
	xp_gained = int(settings.checkin_xp or 10) if session_number == 1 else 0

	# Calculate Sunday- and holiday-safe streak on first check-in of the day
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
		"check_in": now_datetime(),
		"status": "Working",
		"xp_earned": xp_gained,
	}).insert(ignore_permissions=True)

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
def stop_session(work_log: str, target_employee: str = None):
	"""Allows check-out only if an active 'Working' session exists. Validates work log length."""
	ctx = resolve_employee_context(target_employee)
	if not ctx or not ctx.get("name"):
		frappe.throw(_("No active Employee record found."))

	employee = ctx["name"]
	session_name = frappe.db.get_value(
		"Xavirgin Attendance Session",
		{"employee": employee, "status": "Working"},
		"name",
	)
	if not session_name:
		frappe.throw(_("Cannot Check Out: No active working session found. Please Check In first."))

	settings = frappe.get_single("Xavirgin HR Settings")
	min_chars = int(settings.min_work_log_chars or 20)
	if not work_log or len(work_log.strip()) < min_chars:
		frappe.throw(_("Please enter a Work Summary of at least {0} characters before checking out.").format(min_chars))

	doc = frappe.get_doc("Xavirgin Attendance Session", session_name)
	doc.check_out = now_datetime()
	doc.work_log = work_log.strip()
	doc.status = "Completed"
	session_hours = round(time_diff_in_hours(doc.check_out, doc.check_in), 2)
	doc.worked_hours = session_hours

	# Calculate cumulative hours worked today to award capped XP accurately
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