import math
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_first_day, get_last_day, getdate, now_datetime
from xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session import (
	resolve_employee_context,
)
from xavirgin_os.xavirgin_os.doctype.xavirgin_offer_letter.xavirgin_offer_letter import calculate_working_end_date


def recalculate_intern_extension(employee: str):
	"""Section 2 Enforcement: Extends custom_internship_end_date by the exact number of approved general leave days."""
	if not employee:
		return
	emp_data = frappe.db.get_value(
		"Employee",
		employee,
		["custom_is_intern", "custom_internship_start_date", "custom_initial_internship_end_date"],
		as_dict=True,
	)
	if not emp_data:
		return

	approved_leaves = frappe.get_all(
		"Xavirgin Leave Request",
		filters={
			"employee": employee,
			"status": "Approved",
			"leave_type": ["in", ["Medical / Sick Leave", "Personal / Casual Leave"]],
		},
		fields=["leave_days"],
	)
	total_leave_days = sum(float(r.leave_days or 0) for r in approved_leaves)

	updates = {"custom_approved_leaves_days": math.ceil(total_leave_days)}
	if emp_data.custom_is_intern and emp_data.custom_internship_start_date:
		base_days = int(
			frappe.db.get_single_value("Xavirgin HR Settings", "internship_required_active_days") or 90
		)
		new_end_date = calculate_working_end_date(
			emp_data.custom_internship_start_date,
			base_days + math.ceil(total_leave_days),
		)
		updates["custom_internship_end_date"] = new_end_date

	frappe.db.set_value("Employee", employee, updates, update_modified=False)


class XavirginLeaveRequest(Document):
	def before_validate(self):
		self.resolve_intelligent_employee_fields()

	def resolve_intelligent_employee_fields(self):
		"""Intelligently pulls employee context if left blank or logged in via user account."""
		ctx = resolve_employee_context(self.employee)
		if ctx:
			self.employee = ctx.get("name")
			self.employee_name = ctx.get("employee_name")
			self.department = ctx.get("department")
			self.designation = ctx.get("designation")
			self.team_lead = ctx.get("custom_team_lead")

	def validate(self):
		if not self.employee:
			frappe.throw(_("Employee ID could not be identified. Please ensure an active employee profile is linked."))

		start = getdate(self.from_date)
		end = getdate(self.to_date)
		if end < start:
			frappe.throw(_("End Date cannot be earlier than Start Date."))

		# Count working days excluding Sundays
		if self.is_half_day:
			self.leave_days = 0.5
		else:
			days = 0
			curr = start
			while curr <= end:
				if curr.weekday() != 6:  # 6 = Sunday
					days += 1
				curr = add_days(curr, 1)
			self.leave_days = float(days)

		if self.leave_type == "Medical / Sick Leave" and self.leave_days > 1 and not self.proof_attachment:
			frappe.throw(_("Medical proof attachment is required for Sick Leave exceeding 1 day."))

		if self.is_new():
			self.auto_evaluate_monthly_limits()

	def auto_evaluate_monthly_limits(self):
		"""Evaluates monthly allowances (auto-approves within limit, flags pending or rejects if exceeded)."""
		first_day = get_first_day(self.from_date)
		last_day = get_last_day(self.from_date)
		settings = frappe.get_single("Xavirgin HR Settings")

		emp_limits = frappe.db.get_value(
			"Employee",
			self.employee,
			["custom_monthly_leave_limit", "custom_monthly_meeting_leave_limit"],
			as_dict=True,
		) or {}

		if self.leave_type == "Mandatory Meeting Leave":
			limit = int(emp_limits.get("custom_monthly_meeting_leave_limit") or settings.monthly_meeting_leave_limit or 3)
			existing_rows = frappe.get_all(
				"Xavirgin Leave Request",
				filters={
					"employee": self.employee,
					"leave_type": "Mandatory Meeting Leave",
					"status": "Approved",
					"from_date": ["between", [first_day, last_day]],
					"name": ["!=", self.name or ""],
				},
				fields=["leave_days"],
			)
			taken = sum(float(r.leave_days or 0) for r in existing_rows)
			if (taken + self.leave_days) <= limit:
				self.status = "Approved"
				self.approved_by = "System Auto-Approval"
				self.decision_on = now_datetime()
			else:
				self.status = "Rejected"
				self.rejection_reason = f"Monthly meeting leave limit exceeded ({taken + self.leave_days}/{limit} days)."
		else:
			limit = int(emp_limits.get("custom_monthly_leave_limit") or settings.monthly_general_leave_limit or 3)
			existing_rows = frappe.get_all(
				"Xavirgin Leave Request",
				filters={
					"employee": self.employee,
					"leave_type": ["in", ["Medical / Sick Leave", "Personal / Casual Leave"]],
					"status": "Approved",
					"from_date": ["between", [first_day, last_day]],
					"name": ["!=", self.name or ""],
				},
				fields=["leave_days"],
			)
			taken = sum(float(r.leave_days or 0) for r in existing_rows)
			if (taken + self.leave_days) <= limit:
				self.status = "Approved"
				self.approved_by = "System Auto-Approval"
				self.decision_on = now_datetime()
			else:
				self.status = "Pending Approval"

	def on_update(self):
		recalculate_intern_extension(self.employee)

	def after_delete(self):
		recalculate_intern_extension(self.employee)

	@frappe.whitelist()
	def decide_leave(self, new_status: str, rejection_reason: str = ""):
		"""Enables HR Admins or Squad Team Leads to approve or reject pending leave requests."""
		if new_status not in ("Approved", "Rejected"):
			frappe.throw(_("Invalid status value."))

		roles = set(frappe.get_roles(frappe.session.user))
		is_hr = bool(roles.intersection({"System Manager", "Xavirgin HR Admin", "Xavirgin HR Manager"}))
		if not is_hr:
			approver_emp = frappe.db.get_value(
				"Employee",
				{"user_id": frappe.session.user, "custom_is_team_lead": 1},
				["name", "department"],
				as_dict=True,
			)
			if not approver_emp or approver_emp.department != self.department:
				frappe.throw(_("Only HR or a Team Lead of the {0} department can decide on this request.").format(self.department))
			if approver_emp.name == self.employee:
				frappe.throw(_("Team Leads cannot self-approve over-limit leave requests."))

		self.status = new_status
		self.approved_by = frappe.session.user
		self.decision_on = now_datetime()
		if rejection_reason:
			self.rejection_reason = rejection_reason
		self.save(ignore_permissions=True)
		return self.status