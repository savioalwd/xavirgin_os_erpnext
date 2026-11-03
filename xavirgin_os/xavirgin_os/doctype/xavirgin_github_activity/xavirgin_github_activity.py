import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime


class XavirginGitHubActivity(Document):
	def before_insert(self):
		if not self.event_timestamp:
			self.event_timestamp = now_datetime()
		if not self.activity_date:
			self.activity_date = getdate(self.event_timestamp)

	def after_insert(self):
		self.sync_to_daily_poa_and_employee()

	def sync_to_daily_poa_and_employee(self):
		"""Links this GitHub contribution to today's Daily POA and updates Employee XP."""
		if not self.employee:
			return

		poa_name = frappe.db.get_value(
			"Xavirgin Daily POA",
			{"employee": self.employee, "poa_date": self.activity_date},
			"name",
		)
		if poa_name:
			self.db_set("daily_poa", poa_name, update_modified=False)
			poa_doc = frappe.get_doc("Xavirgin Daily POA", poa_name)
			poa_doc.flags.ignore_permissions = True
			poa_doc.save()
		else:
			# Directly increment Employee XP if no POA created yet today
			current_xp = int(frappe.db.get_value("Employee", self.employee, "custom_xp_points") or 0)
			frappe.db.set_value(
				"Employee",
				self.employee,
				"custom_xp_points",
				current_xp + int(self.xp_awarded or 0),
				update_modified=False,
			)