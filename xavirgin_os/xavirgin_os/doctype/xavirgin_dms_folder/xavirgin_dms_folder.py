import io
import json
import zipfile
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime
from xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session import (
	resolve_employee_context,
)


def user_has_folder_access(folder_name: str, user: str = None) -> bool:
	"""Strict permission evaluator for DMS folders."""
	u = user or frappe.session.user
	if u in ("Administrator", "Guest") or "System Manager" in frappe.get_roles(u):
		return True

	folder = frappe.get_doc("Xavirgin DMS Folder", folder_name)
	if folder.visibility == "Public (All Active Employees)":
		return True

	ctx = resolve_employee_context(user_id=u)
	emp_dept = ctx.get("department")

	if folder.visibility == "Department Only" and folder.department and emp_dept == folder.department:
		return True

	# Check explicit permission rules table
	for p in folder.permissions:
		if p.permission_type == "User" and p.user == u and p.allow_read:
			return True
		if p.permission_type == "Role" and p.role in frappe.get_roles(u) and p.allow_read:
			return True

	return False


class XavirginXavirginDMSFolder(Document):
	pass


def get_permission_query_conditions(user: str) -> str:
	"""SQL query filter restricting folders to authorized members."""
	u = user or frappe.session.user
	if u in ("Administrator", "Guest") or "System Manager" in frappe.get_roles(u):
		return ""

	ctx = resolve_employee_context(user_id=u)
	emp_dept = frappe.db.escape(ctx.get("department") or "")

	return f"""
		(`tabXavirgin DMS Folder`.visibility = 'Public (All Active Employees)')
		OR (`tabXavirgin DMS Folder`.visibility = 'Department Only' AND `tabXavirgin DMS Folder`.department = {emp_dept})
		OR (`tabXavirgin DMS Folder`.name IN (
			SELECT parent FROM `tabXavirgin DMS Permission` 
			WHERE (permission_type = 'User' AND user = {frappe.db.escape(u)} AND allow_read = 1)
			   OR (permission_type = 'Role' AND role IN %(user_roles)s AND allow_read = 1)
		))
	"""


def has_permission(doc, ptype="read", user=None) -> bool:
	return user_has_folder_access(doc.name, user=user)


@frappe.whitelist()
def export_folder_zip(folder_name: str):
	"""Generates and streams a downloadable ZIP archive of all private file attachments in the folder."""
	if not user_has_folder_access(folder_name):
		frappe.throw(_("Access Denied: You do not have permission to export this folder."))

	folder = frappe.get_doc("Xavirgin DMS Folder", folder_name)
	zip_buffer = io.BytesIO()

	file_count = 0
	with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
		for f in folder.files:
			if f.item_type == "File Attachment" and f.file_attachment:
				file_path = frappe.get_site_path("private" if "private" in f.file_attachment else "public", f.file_attachment.lstrip("/files/").lstrip("/private/files/"))
				try:
					with open(file_path, "rb") as file_to_zip:
						zip_file.writestr(f.file_attachment.split("/")[-1], file_to_zip.read())
					file_count += 1
				except Exception:
					pass

	# Log audit event
	frappe.get_doc({
		"doctype": "Xavirgin DMS Audit Log",
		"timestamp": now_datetime(),
		"user": frappe.session.user,
		"action_type": "Export ZIP Archive",
		"folder": folder.name,
		"file_title": f"{file_count} files archived",
		"ip_address": frappe.local.request.remote_addr if frappe.local.request else "127.0.0.1",
	}).insert(ignore_permissions=True)
	frappe.db.commit()

	zip_buffer.seek(0)
	frappe.local.response.filename = f"{folder.folder_name}_Export.zip"
	frappe.local.response.filecontent = zip_buffer.read()
	frappe.local.response.type = "download"