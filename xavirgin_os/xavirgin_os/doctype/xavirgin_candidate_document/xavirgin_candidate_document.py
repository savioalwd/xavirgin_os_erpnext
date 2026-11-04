import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class XavirginCandidateDocument(Document):
    def before_insert(self):
        if not self.uploaded_on:
            self.uploaded_on = now_datetime()

    def validate(self):
        if self.verified_by_hr:
            if not self.verified_by:
                self.verified_by = frappe.session.user
            if not getattr(self, "verified_on", None):
                self.verified_on = now_datetime()
        else:
            self.verified_by = None
            self.verified_on = None