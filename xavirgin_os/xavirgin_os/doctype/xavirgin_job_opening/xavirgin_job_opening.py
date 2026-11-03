import frappe
from frappe.model.document import Document
from frappe.utils import get_url


class XavirginJobOpening(Document):
	def validate(self):
		if self.name and not self.is_new():
			self.public_application_url = f"{get_url()}/apply-job?job={self.name}"

	def after_insert(self):
		self.db_set("public_application_url", f"{get_url()}/apply-job?job={self.name}", update_modified=False)