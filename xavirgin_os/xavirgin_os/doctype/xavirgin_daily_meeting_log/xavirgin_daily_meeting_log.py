import frappe
from frappe.model.document import Document


class XavirginDailyMeetingLog(Document):
	def validate(self):
		self.present_count = sum(1 for r in self.entries if r.status == "Present")
		self.absent_count = sum(1 for r in self.entries if r.status == "Absent")
		self.excused_count = sum(1 for r in self.entries if r.status == "Excused (Approved Meeting Leave)")

	@frappe.whitelist()
	def populate_active_interns(self):
		"""Improvement #11: One-click batch population of active interns & approved meeting leaves."""
		filters = {"status": "Active", "custom_is_intern": 1}
		if self.department:
			filters["department"] = self.department

		interns = frappe.get_all(
			"Employee",
			filters=filters,
			fields=["name", "employee_name", "department"],
			order_by="department asc, employee_name asc",
		)

		excused_Format = set(
			frappe.get_all(
				"Xavirgin Leave Request",
				filters={
					"leave_type": "Mandatory Meeting Leave",
					"status": "Approved",
					"from_date": ["<=", self.meeting_date],
					"to_date": [">=", self.meeting_date],
				},
				pluck="employee",
			)
		)

		self.entries = []
		for emp in interns:
			is_excused = emp.name in excused_Format
			self.append("entries", {
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"department": emp.department,
				"status": "Excused (Approved Meeting Leave)" if is_excused else "Present",
				"remarks": "Auto-marked from approved Mandatory Meeting Leave" if is_excused else "",
			})
		self.validate()
		return len(self.entries)