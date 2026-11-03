import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime
from xavirgin_os.ai import generate_employee_poa_summary
from xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session import (
	compute_badge_tier,
	resolve_employee_context,
)


class XavirginDailyPOA(Document):
	def before_validate(self):
		self.resolve_intelligent_employee_fields()
		self.sync_live_attendance_and_github()
		self.calculate_poa_metrics_and_xp()

	def validate(self):
		if not self.employee:
			frappe.throw(_("Employee ID could not be resolved. Please select an active Employee."))
		self.validate_unique_daily_poa()
		self.validate_task_explanations()

	def on_update(self):
		self.rollup_employee_gamification_totals()

	def after_delete(self):
		self.rollup_employee_gamification_totals()

	def resolve_intelligent_employee_fields(self):
		"""Automatically resolves Employee ID, Name, Department, Designation, and Manager."""
		ctx = resolve_employee_context(self.employee)
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
			self.user_id = emp_extra.get("user_id")
			self.reporting_manager = emp_extra.get("reports_to") or emp_extra.get("custom_team_lead")

	def validate_unique_daily_poa(self):
		"""Guarantees strictly 1 POA record per employee per calendar date (never overwrites history)."""
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
				_("A Daily POA ({0}) already exists for {1} on {2}. Please open and update that record instead of creating a duplicate.").format(
					existing, self.employee_name or self.employee, self.poa_date
				)
			)

	def validate_task_explanations(self):
		"""Requires a blocker/incomplete reason when submitting EOD report with Blocked or Pending tasks."""
		for idx, row in enumerate(self.tasks, start=1):
			if row.status == "Blocked" and not (row.blocker_reason or "").strip():
				frappe.throw(
					_("Row #{0} ('{1}') is marked as Blocked. Please provide a Blocker Explanation.").format(
						idx, row.task_title
					)
				)
			if self.status == "Submitted (EOD Report)" and row.status in ("Pending", "Planned") and not (row.blocker_reason or "").strip():
				frappe.throw(
					_("Row #{0} ('{1}') is incomplete on EOD submission. Please provide an explanation in Blocker / Incomplete Explanation or mark it Carried Forward.").format(
						idx, row.task_title
					)
				)

	def sync_live_attendance_and_github(self):
		"""Pulls same-day attendance sessions and GitHub webhook logs automatically."""
		if not self.employee or not self.poa_date:
			return
		p_date = getdate(self.poa_date)

		# 1. Attendance Sync
		sessions = frappe.get_all(
			"Xavirgin Attendance Session",
			filters={"employee": self.employee, "attendance_date": p_date},
			fields=["status", "worked_hours", "day_classification"],
		)
		if sessions:
			self.attendance_verified = 1
			total_att_hours = round(sum(float(s.worked_hours or 0) for s in sessions), 2)
			self.attendance_hours_logged = total_att_hours
			active_working = any(s.status == "Working" for s in sessions)
			self.attendance_status = (
				f"Checked In (Active - {total_att_hours}h so far)"
				if active_working
				else f"{sessions[-1].day_classification} ({total_att_hours}h)"
			)
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
		"""Calculates task tallies, blockers, and attendance-verified gamification XP."""
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
				if row.status == "Blocked":
					blocked += 1
					blocker_lines.append(f"• {row.task_title}: {row.blocker_reason or 'No reason specified'}")
				elif row.status in ("Planned", "In Progress", "Pending"):
					pending += 1

		self.total_planned_hours = round(planned_hrs, 2)
		self.total_actual_hours = round(actual_hrs, 2)
		self.completed_tasks_count = completed
		self.pending_tasks_count = pending
		self.blocked_tasks_count = blocked
		self.total_poa_xp = total_xp
		self.blockers_summary = "\n".join(blocker_lines) if blocker_lines else "No active blockers."

		if blocked > 0 and self.status not in ("Submitted (EOD Report)",):
			self.status = "Blocked"

	def rollup_employee_gamification_totals(self):
		"""Updates Employee master XP and completed task counters across Attendance + POA + GitHub."""
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
	def carry_forward_unfinished_tasks(self):
		"""Pulls Pending, Planned, or Blocked tasks from the employee's most recent previous POA."""
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
			frappe.msgprint(_("No previous Daily POA found to carry forward tasks from."))
			return 0

		prev_doc = frappe.get_doc("Xavirgin Daily POA", prev_poas[0].name)
		existing_titles = {(t.task_title or "").strip().lower() for t in self.tasks}
		added = 0

		for t in prev_doc.tasks:
			if t.status in ("Planned", "In Progress", "Pending", "Blocked", "Carried Forward"):
				if (t.task_title or "").strip().lower() not in existing_titles:
					self.append("tasks", {
						"task_title": t.task_title,
						"task_type": t.task_type,
						"priority": t.priority,
						"project": t.project,
						"status": "In Progress",
						"expected_hours": t.expected_hours,
						"description": t.description,
						"blocker_reason": t.blocker_reason,
						"carried_from_poa": prev_doc.name,
					})
					added += 1

		if added > 0:
			self.save()
		return added

	@frappe.whitelist()
	def submit_eod_report(self):
		"""Marks the Daily POA as formally submitted at End of Day and generates AI summary."""
		self.status = "Submitted (EOD Report)"
		self.submitted_at = now_datetime()
		self.save()
		return self.name

	@frappe.whitelist()
	def generate_individual_ai_summary(self):
		"""Generates and stores an AI performance review for this specific POA."""
		html_summary = generate_employee_poa_summary(self.name)
		self.db_set("ai_summary", html_summary, update_modified=False)
		return html_summary


def get_permission_query_conditions(user: str) -> str:
	"""Department Team Leads see their department's POAs; Interns see their own; HR/System Manager see all."""
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if roles.intersection({"System Manager", "Xavirgin HR Admin", "Xavirgin HR Manager"}):
		return ""

	ctx = resolve_employee_context(user_id=user)
	if not ctx or not ctx.get("name"):
		return f"`tabXavirgin Daily POA`.owner = {frappe.db.escape(user)}"

	emp_id = frappe.db.escape(ctx["name"])
	if "Xavirgin Team Lead" in roles and ctx.get("department"):
		dept = frappe.db.escape(ctx["department"])
		return f"(`tabXavirgin Daily POA`.department = {dept} OR `tabXavirgin Daily POA`.employee = {emp_id})"

	return f"`tabXavirgin Daily POA`.employee = {emp_id}"