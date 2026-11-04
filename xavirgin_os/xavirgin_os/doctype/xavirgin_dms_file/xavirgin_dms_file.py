import frappe
from frappe import _
from frappe.model.document import Document
from xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder import user_has_folder_access


class XavirginDMSFile(Document):
    def before_validate(self):
        if not self.folder and self.parent:
            self.folder = self.parent
            
        if self.item_type == "File Attachment" and self.file_attachment:
            if frappe.db.exists("File", {"file_url": self.file_attachment}):
                frappe.db.set_value("File", {"file_url": self.file_attachment}, "is_private", 1, update_modified=False)

    def validate(self):
        if self.folder and not user_has_folder_access(self.folder):
            frappe.throw(_("Permission Denied: You do not have upload or edit access to folder {0}.").format(self.folder))

        if self.item_type == "Login Credential" and not (self.credential_username or self.credential_password):
            frappe.throw(_("Please provide a username or password for this credential record."))

    def after_insert(self):
        self.log_dms_audit("Upload File" if self.item_type == "File Attachment" else "Add Credential")

    def on_trash(self):
        if self.folder and not user_has_folder_access(self.folder):
            frappe.throw(_("Permission Denied: You cannot delete items from this folder."))
        self.log_dms_audit("Delete Item")

    def log_dms_audit(self, action_type: str):
        try:
            frappe.get_doc({
                "doctype": "Xavirgin DMS Audit Log",
                "timestamp": frappe.utils.now_datetime(),
                "user": frappe.session.user,
                "action_type": action_type,
                "folder": self.folder,
                "file_title": self.title,
                "ip_address": frappe.local.request.remote_addr if frappe.local.request else "127.0.0.1",
            }).insert(ignore_permissions=True)
        except Exception:
            pass