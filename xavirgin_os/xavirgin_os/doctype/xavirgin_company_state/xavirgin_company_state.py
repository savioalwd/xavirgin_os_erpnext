import frappe
from frappe.model.document import Document


class XavirginCompanyState(Document):
	def before_trash(self):
		# Single doc types shouldn't normally be deleted, but if forced, clear links
		pass