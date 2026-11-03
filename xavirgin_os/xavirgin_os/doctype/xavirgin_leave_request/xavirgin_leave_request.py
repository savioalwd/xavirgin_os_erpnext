import math
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_first_day, get_last_day, getdate
from xavirgin_os.xavirgin_os.doctype.xavirgin_offer_letter.xavirgin_offer_letter import calculate_working_end_date


def recalculate_intern_extension(employee: str):
	"""
	Improvement #2: Mathematical enforcement of Section 2 of the Offer Letter.
	Extends custom_internship_end_date by the exact number of approved general leave days.
	"""
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
		if not self.employee:
			self.employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")

	def validate(self):
		start = getdate(self.from_date)
		end = getdate(self.to_date)
		if end < start:
			frappe.throw(_("End Date cannot be earlier than Start Date."))

		# Improvement #9: Count working days excluding Sundays
		if self.is_half_day:
			self.leave_days = 0.5
		else:
			days = 0
			curr = start
			while curr <= end:
				if curr.weekday() != 6:  # Exclude Sunday
					days += 1
				curr = add_days(curr, 1)
			self.leave_days = float(days)

		if self.leave_type == "Medical / Sick Leave" and self.leave_days > 1 and not self.proof_attachment:
			frappe.throw(_("Supporting medical proof attachment is required for Sick Leave exceeding 1 day."))

		if self.is_new():
			self.auto_evaluate_monthly_limits()

	def auto_evaluate_monthly_limits(self):
		"""Ported & fixed from Odoo _auto_evaluate_leave_limits (sums leave_days instead of search_count)."""
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
			else:
				self.status = "Rejected"
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
			else:
				self.status = "Pending Approval"

	def on_update(self):
		recalculate_intern_extension(self.employee)

	def after_delete(self):
		recalculate_intern_extension(self.employee)

	@frappe.whitelist()
	def decide_leave(self, new_status: str):
		"""Improvement #10: Allow HR Admins or Department Team Leads to approve/reject pending requests."""
		if new_status not in ("Approved", "Rejected"):
			frappe.throw(_("Invalid status"))

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
				frappe.throw(_("Only an HR Administrator or a Team Lead of the {0} department can approve this request.").format(self.department))
			if approver_emp.name == self.employee:
				frappe.throw(_("Team Leads cannot self-approve their own over-limit leave requests."))

		self.status = new_status
		self.approved_by = frappe.session.user
		self.save(ignore_permissions=True)
		return self.status