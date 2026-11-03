import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate
from xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session import (
	resolve_employee_context,
)


class XavirginDailyMeetingLog(Document):
	def before_validate(self):
		self.resolve_intelligent_conductor_and_defaults()

	def validate(self):
		self.validate_duplicate_meeting_log()
		self.calculate_aggregate_tallies()

	def resolve_intelligent_conductor_and_defaults(self):
		"""Pulls conductor details from the logged-in session user and global HR settings."""
		if not self.conducted_by:
			self.conducted_by = frappe.session.user

		# Resolve conductor Employee ID
		ctx = resolve_employee_context(user_id=self.conducted_by)
		if ctx:
			self.conductor_employee = ctx.get("name")
			self.conductor_name = ctx.get("employee_name")

		# Pull default sync time and Google Meet link from global settings if blank
		settings = frappe.get_single("Xavirgin HR Settings")
		if not self.sync_time:
			self.sync_time = settings.daily_team_sync_time or "20:00:00"
		if not self.meeting_url:
			self.meeting_url = settings.default_meet_link

	def validate_duplicate_meeting_log(self):
		"""Prevents duplicate sync logs for the same date and department."""
		filters = {
			"meeting_date": getdate(self.meeting_date),
			"name": ["!=", self.name or ""],
		}
		if self.department:
			filters["department"] = self.department
		else:
			filters["department"] = ["in", ["", None]]

		existing = frappe.db.get_value("Xavirgin Daily Meeting Log", filters, "name")
		if existing:
			dept_label = self.department or "All Departments"
			frappe.throw(
				_("A Daily Meeting Log ({0}) already exists for {1} on {2}.").format(
					existing, dept_label, self.meeting_date
				)
			)

	def calculate_aggregate_tallies(self):
		"""Recalculates roll call statistics."""
		self.total_participants = len(self.entries)
		self.present_count = sum(1 for r in self.entries if r.status == "Present")
		self.absent_count = sum(1 for r in self.entries if r.status == "Absent")
		self.excused_count = sum(1 for r in self.entries if r.status == "Excused (Approved Meeting Leave)")

	@frappe.whitelist()
	def populate_active_interns(self):
		"""Populates active interns, checks approved meeting leaves, and pulls today's worked hours."""
		filters = {"status": "Active", "custom_is_intern": 1}
		if self.department:
			filters["department"] = self.department

		interns = frappe.get_all(
			"Employee",
			filters=filters,
			fields=["name", "employee_name", "department", "designation"],
			order_by="department asc, employee_name asc",
		)

		if not interns:
			frappe.throw(_("No active interns found matching the criteria."))

		m_date = getdate(self.meeting_date)

		# Fetch all approved mandatory meeting leaves for this date
		excused_interns = set(
			frappe.get_all(
				"Xavirgin Leave Request",
				filters={
					"leave_type": "Mandatory Meeting Leave",
					"status": "Approved",
					"from_date": ["<=", m_date],
					"to_date": [">=", m_date],
				},
				pluck="employee",
			)
		)

		# Fetch today's completed attendance sessions to show hours worked before sync
		today_sessions = frappe.get_all(
			"Xavirgin Attendance Session",
			filters={
				"attendance_date": m_date,
				"status": ["in", ["Completed", "Corrected", "Working"]],
			},
			fields=["employee", "worked_hours"],
		)

		hours_by_emp = {}
		for sess in today_sessions:
			hours_by_emp[sess.employee] = hours_by_emp.get(sess.employee, 0.0) + float(sess.worked_hours or 0)

		self.entries = []
		for emp in interns:
			is_excused = emp.name in excused_interns
			logged_hours = round(hours_by_emp.get(emp.name, 0.0), 2)

			status = "Excused (Approved Meeting Leave)" if is_excused else "Present"
			remarks = "Approved Mandatory Meeting Leave" if is_excused else ""
			if not is_excused and logged_hours < 4.0:
				remarks = f"Logged {logged_hours}h prior to sync"

			self.append("entries", {
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"department": emp.department,
				"designation": emp.designation,
				"status": status,
				"today_worked_hours": logged_hours,
				"remarks": remarks,
			})

		self.calculate_aggregate_tallies()
		self.save()
		return len(self.entries)