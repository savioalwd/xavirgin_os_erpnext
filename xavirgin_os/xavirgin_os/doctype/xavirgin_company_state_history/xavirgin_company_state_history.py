import frappe
from frappe.model.document import Document


class XavirginCompanyStateHistory(Document):
	def before_trash(self):
		# 1. Unlink from Master Company State if referenced
		if frappe.db.exists("DocType", "Xavirgin Company State"):
			try:
				state_doc = frappe.get_single("Xavirgin Company State")
				if getattr(state_doc, "last_applied_history", None) == self.name:
					state_doc.db_set("last_applied_history", None)
			except Exception:
				pass

		# 2. Force nullify source summary log link to prevent downstream deletion locks
		if self.source_summary_log:
			self.db_set("source_summary_log", None)