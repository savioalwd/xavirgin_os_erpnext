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
                frappe.db.set_value(
                    "File",
                    {"file_url": self.file_attachment},
                    "is_private",
                    1,
                    update_modified=False,
                )

    def validate(self):
        # Enforce upload/edit access on folder, not just read access
        if self.folder and not user_has_folder_access(self.folder, mode="upload"):
            frappe.throw(
                _("Permission Denied: You do not have upload or edit access to folder '{0}'.").format(self.folder),
                frappe.PermissionError,
            )

        if self.item_type == "Login Credential" and not (self.credential_username or self.credential_password):
            frappe.throw(_("Please provide a username or password for this credential record."))

    def after_insert(self):
        self.log_dms_audit("Upload File" if self.item_type == "File Attachment" else "Add Credential")

    def on_trash(self):
        # Enforce delete access on folder
        if self.folder and not user_has_folder_access(self.folder, mode="delete"):
            frappe.throw(
                _("Permission Denied: You cannot delete items from folder '{0}'.").format(self.folder),
                frappe.PermissionError,
            )
        self.log_dms_audit("Delete Item")

    def log_dms_audit(self, action_type: str):
        try:
            valid_actions = {
                "View Folder",
                "Download File",
                "Reveal Credential",
                "Export ZIP Archive",
                "Upload File",
                "Add Credential",
                "Delete Item",
            }
            safe_action = action_type if action_type in valid_actions else "View Folder"

            frappe.get_doc({
                "doctype": "Xavirgin DMS Audit Log",
                "timestamp": frappe.utils.now_datetime(),
                "user": frappe.session.user,
                "action_type": safe_action,
                "folder": self.folder,
                "file_title": f"[{action_type}] {self.title or ''}".strip()[:140],
                "ip_address": frappe.local.request.remote_addr if getattr(frappe.local, "request", None) else "127.0.0.1",
            }).insert(ignore_permissions=True)
        except Exception:
            pass