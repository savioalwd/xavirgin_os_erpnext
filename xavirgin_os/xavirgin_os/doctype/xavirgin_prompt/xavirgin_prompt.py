import frappe
from frappe.model.document import Document


class XavirginPrompt(Document):
	def validate(self):
		# If marked default for a category, unmark other defaults in the same category
		if self.is_default and self.is_active:
			frappe.db.sql(
				"""
				UPDATE `tabXavirgin Prompt`
				SET is_default = 0
				WHERE category = %s AND name != %s
				""",
				(self.category, self.name),
			)