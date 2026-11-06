import io
import os
import zipfile
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import format_datetime, formatdate, now_datetime
from frappe.utils.password import get_decrypted_password
from xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session import (
    resolve_employee_context,
)


def is_dms_super_admin(user: str = None) -> bool:
    u = user or frappe.session.user
    if u == "Administrator":
        return True
    roles = set(frappe.get_roles(u))
    return bool(roles.intersection({"System Manager", "Xavirgin HR Admin"}))


def get_user_folder_permissions(folder_name: str, user: str = None) -> dict:
    """Computes granular access flags for `user` on `folder_name`:
    - `can_read`: Can open folder and view files/metadata.
    - `can_download`: Can download/preview files.
    - `can_upload`: Can upload files or add credentials.
    - `can_edit`: Can edit folder settings, rename/move items, and reveal credentials.
    - `can_delete`: Can delete files/items or archive folder.
    - `is_folder_admin`: True for Super Admins, folder creator/owner, or explicit `allow_edit` rule.
    """
    u = user or frappe.session.user
    deny_all = {
        "can_read": False,
        "can_download": False,
        "can_upload": False,
        "can_edit": False,
        "can_delete": False,
        "is_folder_admin": False,
    }
    if not u or u == "Guest":
        return deny_all

    if is_dms_super_admin(u):
        return {
            "can_read": True,
            "can_download": True,
            "can_upload": True,
            "can_edit": True,
            "can_delete": True,
            "is_folder_admin": True,
        }

    if not folder_name or not frappe.db.exists("Xavirgin DMS Folder", folder_name):
        roles = set(frappe.get_roles(u))
        can_create = bool(roles.intersection({"System Manager", "Xavirgin HR Admin", "Xavirgin Team Lead"}))
        return {
            "can_read": True,
            "can_download": True,
            "can_upload": can_create,
            "can_edit": can_create,
            "can_delete": False,
            "is_folder_admin": can_create,
        }

    folder = frappe.get_doc("Xavirgin DMS Folder", folder_name)
    user_roles = set(frappe.get_roles(u))

    # Creator / Owner of the folder is a Folder Administrator
    if folder.created_by_user == u or folder.owner == u:
        return {
            "can_read": True,
            "can_download": True,
            "can_upload": True,
            "can_edit": True,
            "can_delete": True,
            "is_folder_admin": True,
        }

    perms = dict(deny_all)

    # 1. Check baseline visibility scope (Read & Download only — never grants edit/upload automatically)
    if folder.visibility == "Public (All Active Employees)":
        perms["can_read"] = True
        perms["can_download"] = True
    elif folder.visibility == "Department Only" and folder.department:
        ctx = resolve_employee_context(user_id=u)
        if ctx and ctx.get("department") == folder.department:
            perms["can_read"] = True
            perms["can_download"] = True
            # Team Lead of this department gets folder management privileges
            if "Xavirgin Team Lead" in user_roles or ctx.get("custom_is_team_lead"):
                perms["can_upload"] = True
                perms["can_edit"] = True
                perms["is_folder_admin"] = True

    # 2. Check explicit Granular Permission Rules table
    for p in folder.permissions or []:
        matched = (p.permission_type == "User" and p.user == u) or (
            p.permission_type == "Role" and p.role in user_roles
        )
        if matched:
            if p.allow_read:
                perms["can_read"] = True
            if p.allow_download:
                perms["can_download"] = True
            if p.allow_upload:
                perms["can_upload"] = True
                perms["can_read"] = True
            if p.allow_edit:
                perms["can_edit"] = True
                perms["can_upload"] = True
                perms["can_read"] = True
                perms["is_folder_admin"] = True
            if p.allow_delete:
                perms["can_delete"] = True

    return perms


def user_has_folder_access(folder_name: str, user: str = None, mode: str = "read") -> bool:
    """Backward-compatible helper verifying folder access by mode ('read', 'upload', 'edit', 'delete', 'download')."""
    perms = get_user_folder_permissions(folder_name, user=user)
    if mode == "upload":
        return perms["can_upload"]
    if mode == "edit":
        return perms["can_edit"]
    if mode == "delete":
        return perms["can_delete"]
    if mode == "download":
        return perms["can_download"]
    return perms["can_read"]


def log_dms_event(action_type: str, folder: str = None, file_title: str = None):
    try:
        valid_actions = {"View Folder", "Download File", "Reveal Credential", "Export ZIP Archive"}
        safe_action = action_type if action_type in valid_actions else "View Folder"
        frappe.get_doc({
            "doctype": "Xavirgin DMS Audit Log",
            "timestamp": now_datetime(),
            "user": frappe.session.user,
            "action_type": safe_action,
            "folder": folder,
            "file_title": f"[{action_type}] {file_title or ''}".strip()[:140],
            "ip_address": frappe.local.request.remote_addr if getattr(frappe.local, "request", None) else "127.0.0.1",
        }).insert(ignore_permissions=True)
    except Exception:
        pass


class XavirginDMSFolder(Document):
    def before_insert(self):
        if not self.created_by_user:
            self.created_by_user = frappe.session.user
        if not self.created_on:
            self.created_on = now_datetime()

    def validate(self):
        if not self.is_new():
            perms = get_user_folder_permissions(self.name, frappe.session.user)
            if not (perms["can_edit"] or perms["can_upload"]):
                frappe.throw(
                    _("Permission Denied: You have Read-Only access to folder '{0}'.").format(self.folder_name),
                    frappe.PermissionError,
                )

        if self.parent_folder and self.parent_folder == self.name:
            frappe.throw(_("A folder cannot be its own Parent Folder."))


# ==============================================================================
# Google Drive–Style File Browser & Folder Workspace APIs
# ==============================================================================

def detect_file_type_badge(file_url: str, item_type: str) -> dict:
    if item_type == "Login Credential":
        return {"ext": "KEY", "category": "Credential", "icon": "🔑", "bg": "#fef3c7", "color": "#92400e"}
    ext = os.path.splitext((file_url or "").lower())[1].lstrip(".")
    if ext == "pdf":
        return {"ext": "PDF", "category": "PDF", "icon": "📕", "bg": "#fee2e2", "color": "#991b1b"}
    if ext in ("doc", "docx", "txt", "md", "rtf"):
        return {"ext": ext.upper() or "DOC", "category": "Document", "icon": "📘", "bg": "#dbeafe", "color": "#1e40af"}
    if ext in ("xls", "xlsx", "csv"):
        return {"ext": ext.upper() or "XLS", "category": "Spreadsheet", "icon": "📗", "bg": "#dcfce7", "color": "#166534"}
    if ext in ("ppt", "pptx"):
        return {"ext": ext.upper() or "PPT", "category": "Presentation", "icon": "📙", "bg": "#ffedd5", "color": "#9a3412"}
    if ext in ("png", "jpg", "jpeg", "gif", "svg", "webp"):
        return {"ext": ext.upper() or "IMG", "category": "Image", "icon": "🖼️", "bg": "#f3e8ff", "color": "#6b21a8"}
    if ext in ("zip", "tar", "gz", "rar", "7z"):
        return {"ext": ext.upper() or "ZIP", "category": "Archive", "icon": "📦", "bg": "#e2e8f0", "color": "#334155"}
    return {"ext": (ext.upper() if ext else "FILE"), "category": "Other", "icon": "📄", "bg": "#f1f5f9", "color": "#475569"}


def build_folder_breadcrumbs(folder_name: str) -> list:
    """Walks parent_folder links safely (preventing cycles) to build interactive breadcrumbs."""
    crumbs = []
    curr = folder_name
    visited = set()
    while curr and curr not in visited and frappe.db.exists("Xavirgin DMS Folder", curr):
        visited.add(curr)
        info = frappe.db.get_value("Xavirgin DMS Folder", curr, ["name", "folder_name", "parent_folder"], as_dict=True)
        if not info:
            break
        # Only include ancestor in breadcrumb link if user has read access to it
        accessible = user_has_folder_access(info.name, mode="read")
        crumbs.append({
            "name": info.name,
            "folder_name": info.folder_name,
            "accessible": accessible,
        })
        curr = info.parent_folder
    crumbs.reverse()
    return crumbs


@frappe.whitelist()
def get_dms_drive_browser(
    parent_folder: str = None,
    nav_scope: str = "root",
    department: str = None,
    search_text: str = None,
    file_type_filter: str = None,
    sort_by: str = "folder_name",
) -> dict:
    """Powers the main Google Drive–inspired DMS File Browser."""
    user = frappe.session.user
    ctx = resolve_employee_context(user_id=user)
    my_dept = ctx.get("department") if ctx else None
    super_admin = is_dms_super_admin(user)

    all_folders = frappe.get_all(
        "Xavirgin DMS Folder",
        fields=[
            "name",
            "folder_name",
            "parent_folder",
            "department",
            "visibility",
            "created_by_user",
            "created_on",
            "modified",
            "owner",
        ],
        order_by="folder_name asc",
    )

    # Filter to only folders this user is authorized to read
    accessible_folders = {}
    perms_by_folder = {}
    for f in all_folders:
        p = get_user_folder_permissions(f.name, user=user)
        if p["can_read"]:
            accessible_folders[f.name] = f
            perms_by_folder[f.name] = p

    # Count subfolders & files in a single batch query
    subfolder_counts = {}
    for f in all_folders:
        if f.parent_folder and f.name in accessible_folders:
            subfolder_counts[f.parent_folder] = subfolder_counts.get(f.parent_folder, 0) + 1

    accessible_names = list(accessible_folders.keys())
    all_items = []
    if accessible_names:
        all_items = frappe.get_all(
            "Xavirgin DMS File",
            filters={"parent": ["in", accessible_names]},
            fields=[
                "name",
                "parent",
                "title",
                "item_type",
                "folder",
                "file_attachment",
                "credential_url",
                "credential_username",
                "notes",
                "creation",
                "modified",
                "owner",
            ],
            order_by="modified desc",
        )

    # Lookup file sizes from File doctype in batch
    file_urls = [it.file_attachment for it in all_items if it.file_attachment]
    file_size_map = {}
    if file_urls:
        for f_meta in frappe.get_all("File", filters={"file_url": ["in", file_urls]}, fields=["file_url", "file_size"]):
            file_size_map[f_meta.file_url] = int(f_meta.file_size or 0)

    files_count_by_folder = {}
    creds_count_by_folder = {}
    for it in all_items:
        p_folder = it.parent
        if it.item_type == "Login Credential":
            creds_count_by_folder[p_folder] = creds_count_by_folder.get(p_folder, 0) + 1
        else:
            files_count_by_folder[p_folder] = files_count_by_folder.get(p_folder, 0) + 1

    search_q = (search_text or "").strip().lower()

    # Determine displayed folders
    displayed_folders = []
    for f_name, f in accessible_folders.items():
        if department and f.department != department:
            continue

        if parent_folder:
            if f.parent_folder != parent_folder:
                continue
        elif not search_q:
            if nav_scope == "root":
                # Root folders (or folders whose parent is not accessible/set)
                if f.parent_folder and f.parent_folder in accessible_folders:
                    continue
            elif nav_scope == "my_department":
                if not my_dept or f.department != my_dept:
                    continue
            elif nav_scope == "public":
                if f.visibility != "Public (All Active Employees)":
                    continue

        if search_q:
            hay = f"{f.folder_name} {f.name} {f.department or ''} {f.created_by_user or ''}".lower()
            if search_q not in hay:
                continue

        fp = perms_by_folder[f_name]
        displayed_folders.append({
            "name": f.name,
            "folder_name": f.folder_name,
            "parent_folder": f.parent_folder,
            "department": f.department or "General",
            "visibility": f.visibility,
            "owner": f.created_by_user or f.owner,
            "modified_date": formatdate(f.modified, "dd MMM yyyy") if f.modified else "-",
            "files_count": files_count_by_folder.get(f.name, 0),
            "credentials_count": creds_count_by_folder.get(f.name, 0),
            "subfolders_count": subfolder_counts.get(f.name, 0),
            "access_badge": "Admin Managed" if fp["is_folder_admin"] else ("Upload Enabled" if fp["can_upload"] else "Read Only"),
            "is_folder_admin": fp["is_folder_admin"],
        })

    # Determine displayed files & credentials
    displayed_items = []
    for it in all_items:
        p_folder = it.parent
        if parent_folder and p_folder != parent_folder:
            continue
        if not parent_folder and nav_scope == "my_department":
            f_obj = accessible_folders.get(p_folder)
            if not f_obj or f_obj.department != my_dept:
                continue
        if department:
            f_obj = accessible_folders.get(p_folder)
            if not f_obj or f_obj.department != department:
                continue

        badge = detect_file_type_badge(it.file_attachment, it.item_type)
        if file_type_filter and badge["category"] != file_type_filter:
            continue

        if search_q:
            ihay = f"{it.title or ''} {it.notes or ''} {it.credential_username or ''} {it.credential_url or ''} {badge['ext']}".lower()
            if search_q not in ihay:
                continue

        raw_size = file_size_map.get(it.file_attachment, 0)
        size_kb = f"{round(raw_size / 1024, 1)} KB" if raw_size > 0 else ("Vault Secret" if it.item_type == "Login Credential" else "-")
        fp = perms_by_folder.get(p_folder, {})
        f_doc = accessible_folders.get(p_folder)

        displayed_items.append({
            "row_name": it.name,
            "title": it.title,
            "item_type": it.item_type,
            "folder": p_folder,
            "folder_name": f_doc.folder_name if f_doc else p_folder,
            "file_attachment": it.file_attachment if fp.get("can_download") else None,
            "credential_url": it.credential_url,
            "credential_username": it.credential_username,
            "is_password_protected": it.item_type == "Login Credential",
            "notes": it.notes or "",
            "type_badge": badge,
            "file_size": size_kb,
            "raw_size": raw_size,
            "uploaded_date": formatdate(it.creation, "dd MMM yyyy") if it.creation else "-",
            "modified_date": formatdate(it.modified, "dd MMM yyyy") if it.modified else "-",
            "owner": it.owner,
            "can_download": bool(fp.get("can_download")),
            "can_edit": bool(fp.get("can_edit")),
            "can_delete": bool(fp.get("can_delete")),
        })

    # Sorting
    if sort_by == "modified":
        displayed_folders.sort(key=lambda x: x["modified_date"], reverse=True)
    elif sort_by == "size":
        displayed_items.sort(key=lambda x: x["raw_size"], reverse=True)
    else:
        displayed_folders.sort(key=lambda x: (x["folder_name"] or "").lower())
        displayed_items.sort(key=lambda x: (x["title"] or "").lower())

    breadcrumbs = build_folder_breadcrumbs(parent_folder) if parent_folder else []
    current_folder_perms = get_user_folder_permissions(parent_folder, user=user) if parent_folder else {
        "can_read": True,
        "can_upload": bool(super_admin or "Xavirgin Team Lead" in frappe.get_roles(user)),
        "can_edit": bool(super_admin or "Xavirgin Team Lead" in frappe.get_roles(user)),
        "can_delete": super_admin,
        "is_folder_admin": bool(super_admin or "Xavirgin Team Lead" in frappe.get_roles(user)),
    }

    all_depts = frappe.get_all("Department", pluck="name")

    return {
        "current_folder": parent_folder,
        "current_folder_name": accessible_folders[parent_folder].folder_name if (parent_folder and parent_folder in accessible_folders) else "All Drive Folders",
        "parent_of_current": accessible_folders[parent_folder].parent_folder if (parent_folder and parent_folder in accessible_folders) else None,
        "breadcrumbs": breadcrumbs,
        "permissions": current_folder_perms,
        "my_department": my_dept,
        "all_departments": sorted(all_depts),
        "folders": displayed_folders,
        "items": displayed_items,
        "counts": {
            "total_accessible_folders": len(accessible_folders),
            "displayed_folders": len(displayed_folders),
            "displayed_files": sum(1 for x in displayed_items if x["item_type"] == "File Attachment"),
            "displayed_credentials": sum(1 for x in displayed_items if x["item_type"] == "Login Credential"),
        },
    }


@frappe.whitelist()
def get_dms_folder_workspace(folder_name: str) -> dict:
    """Returns complete workspace data for an individual DMS Folder view:
    Breadcrumbs, Subfolders, Separated Files vs. Masked Credentials, Folder Admins, and Audit Logs.
    """
    if not folder_name or not frappe.db.exists("Xavirgin DMS Folder", folder_name):
        return {}

    perms = get_user_folder_permissions(folder_name, frappe.session.user)
    if not perms["can_read"]:
        frappe.throw(_("Access Denied: You do not have permission to view this folder."), frappe.PermissionError)

    log_dms_event("View Folder", folder=folder_name, file_title=folder_name)

    folder = frappe.get_doc("Xavirgin DMS Folder", folder_name)
    breadcrumbs = build_folder_breadcrumbs(folder_name)

    subfolders = frappe.get_all(
        "Xavirgin DMS Folder",
        filters={"parent_folder": folder_name},
        fields=["name", "folder_name", "department", "visibility", "created_by_user", "modified"],
        order_by="folder_name asc",
    )
    visible_subfolders = [sf for sf in subfolders if user_has_folder_access(sf.name, mode="read")]
    for sf in visible_subfolders:
        sf["modified_date"] = formatdate(sf.modified, "dd MMM yyyy") if sf.modified else "-"

    # Separate Files vs Credentials (NEVER send plain-text password in workspace payload)
    file_urls = [r.file_attachment for r in (folder.files or []) if r.file_attachment]
    size_map = {}
    if file_urls:
        for fm in frappe.get_all("File", filters={"file_url": ["in", file_urls]}, fields=["file_url", "file_size"]):
            size_map[fm.file_url] = int(fm.file_size or 0)

    files_list = []
    credentials_list = []

    for row in folder.files or []:
        badge = detect_file_type_badge(row.file_attachment, row.item_type)
        if row.item_type == "Login Credential":
            credentials_list.append({
                "row_name": row.name,
                "title": row.title,
                "credential_url": row.credential_url or "",
                "credential_username": row.credential_username or "",
                "masked_password": "••••••••••••",
                "notes": row.notes or "",
                "owner": row.owner,
                "modified_date": formatdate(row.modified, "dd MMM yyyy") if row.modified else "-",
            })
        else:
            sz = size_map.get(row.file_attachment, 0)
            files_list.append({
                "row_name": row.name,
                "title": row.title,
                "file_attachment": row.file_attachment if perms["can_download"] else None,
                "notes": row.notes or "",
                "badge": badge,
                "file_size": f"{round(sz / 1024, 1)} KB" if sz > 0 else "-",
                "owner": row.owner,
                "uploaded_date": formatdate(row.creation, "dd MMM yyyy") if row.creation else "-",
                "modified_date": formatdate(row.modified, "dd MMM yyyy") if row.modified else "-",
            })

    # Folder Administrators & Access Rules
    folder_admins = [folder.created_by_user or folder.owner]
    access_rules = []
    for p in folder.permissions or []:
        target = p.user if p.permission_type == "User" else f"Role: {p.role}"
        if p.allow_edit and target not in folder_admins:
            folder_admins.append(target)
        access_rules.append({
            "type": p.permission_type,
            "target": target,
            "read": bool(p.allow_read),
            "download": bool(p.allow_download),
            "upload": bool(p.allow_upload),
            "edit": bool(p.allow_edit),
            "delete": bool(p.allow_delete),
        })

    # Recent Audit Activity (visible to Folder Admins & Super Admins)
    audit_logs = []
    if perms["is_folder_admin"]:
        raw_logs = frappe.get_all(
            "Xavirgin DMS Audit Log",
            filters={"folder": folder_name},
            fields=["timestamp", "user", "action_type", "file_title", "ip_address"],
            order_by="timestamp desc",
            limit=20,
        )
        for lg in raw_logs:
            audit_logs.append({
                "timestamp": format_datetime(lg.timestamp, "dd MMM yyyy hh:mm a") if lg.timestamp else "-",
                "user": lg.user,
                "action_type": lg.action_type,
                "file_title": lg.file_title or "-",
                "ip_address": lg.ip_address or "-",
            })

    return {
        "folder_name": folder.folder_name,
        "parent_folder": folder.parent_folder,
        "department": folder.department or "All / Unassigned",
        "visibility": folder.visibility,
        "created_by": folder.created_by_user or folder.owner,
        "created_on": formatdate(folder.created_on, "dd MMM yyyy") if folder.created_on else "-",
        "modified_on": formatdate(folder.modified, "dd MMM yyyy") if folder.modified else "-",
        "breadcrumbs": breadcrumbs,
        "permissions": perms,
        "folder_admins": folder_admins,
        "access_rules": access_rules,
        "subfolders": visible_subfolders,
        "files": files_list,
        "credentials": credentials_list,
        "audit_logs": audit_logs,
    }


@frappe.whitelist()
def reveal_dms_credential(folder_name: str, row_name: str) -> dict:
    """Securely decrypts and returns a credential password ONLY after verifying server-side permissions
    and writing an immutable audit trail entry.
    """
    perms = get_user_folder_permissions(folder_name, frappe.session.user)
    if not perms["can_read"]:
        frappe.throw(_("Access Denied: You are not authorized to access this credential."), frappe.PermissionError)

    row = frappe.db.get_value(
        "Xavirgin DMS File",
        {"name": row_name, "parent": folder_name, "item_type": "Login Credential"},
        ["name", "title", "credential_username", "credential_url"],
        as_dict=True,
    )
    if not row:
        frappe.throw(_("Credential record not found in folder {0}.").format(folder_name))

    secret = None
    try:
        secret = get_decrypted_password("Xavirgin DMS File", row_name, "credential_password", raise_exception=False)
    except Exception:
        pass

    if not secret:
        # Fallback if stored directly on child row during session
        secret = frappe.db.get_value("Xavirgin DMS File", row_name, "credential_password") or ""

    log_dms_event("Reveal Credential", folder=folder_name, file_title=row.title)
    frappe.db.commit()

    return {
        "title": row.title,
        "username": row.credential_username or "",
        "password": secret,
    }


@frappe.whitelist()
def manage_dms_item(
    action: str,
    folder_name: str,
    row_name: str = None,
    new_title: str = None,
    target_folder: str = None,
) -> dict:
    """Handles Rename, Move between folders, and Delete of DMS files/credentials with strict permission checks."""
    perms = get_user_folder_permissions(folder_name, frappe.session.user)
    folder_doc = frappe.get_doc("Xavirgin DMS Folder", folder_name)

    target_row = None
    for r in folder_doc.files:
        if r.name == row_name:
            target_row = r
            break

    if not target_row:
        frappe.throw(_("Item not found in folder {0}.").format(folder_name))

    if action == "rename":
        if not perms["can_edit"]:
            frappe.throw(_("Permission Denied: You cannot rename items in this folder."), frappe.PermissionError)
        if not new_title or not new_title.strip():
            frappe.throw(_("Please provide a valid title."))
        target_row.title = new_title.strip()
        folder_doc.save(ignore_permissions=True)
        return {"status": "renamed", "title": target_row.title}

    if action == "move":
        if not perms["can_edit"]:
            frappe.throw(_("Permission Denied: You cannot move items out of this folder."), frappe.PermissionError)
        dest_perms = get_user_folder_permissions(target_folder, frappe.session.user)
        if not dest_perms["can_upload"]:
            frappe.throw(_("Permission Denied: You do not have upload access to destination folder {0}.").format(target_folder), frappe.PermissionError)

        dest_doc = frappe.get_doc("Xavirgin DMS Folder", target_folder)
        secret_pw = None
        if target_row.item_type == "Login Credential":
            try:
                secret_pw = get_decrypted_password("Xavirgin DMS File", target_row.name, "credential_password", raise_exception=False)
            except Exception:
                pass

        dest_doc.append("files", {
            "title": target_row.title,
            "item_type": target_row.item_type,
            "folder": dest_doc.name,
            "file_attachment": target_row.file_attachment,
            "credential_url": target_row.credential_url,
            "credential_username": target_row.credential_username,
            "credential_password": secret_pw or target_row.credential_password,
            "notes": target_row.notes,
        })
        dest_doc.save(ignore_permissions=True)

        folder_doc.remove(target_row)
        folder_doc.save(ignore_permissions=True)
        return {"status": "moved", "target_folder": target_folder}

    if action == "delete":
        if not (perms["can_delete"] or perms["is_folder_admin"]):
            frappe.throw(_("Permission Denied: Only Folder Administrators can delete items."), frappe.PermissionError)
        title_backup = target_row.title
        folder_doc.remove(target_row)
        folder_doc.save(ignore_permissions=True)
        log_dms_event("View Folder", folder=folder_name, file_title=f"Deleted: {title_backup}")
        return {"status": "deleted"}

    frappe.throw(_("Unsupported action: {0}").format(action))


@frappe.whitelist()
def create_dms_subfolder(
    folder_name: str,
    parent_folder: str = None,
    department: str = None,
    visibility: str = "Department Only",
) -> str:
    """Creates a new root folder or subfolder after verifying folder creation permissions."""
    user = frappe.session.user
    if parent_folder:
        parent_perms = get_user_folder_permissions(parent_folder, user=user)
        if not (parent_perms["can_upload"] or parent_perms["can_edit"]):
            frappe.throw(_("Permission Denied: You cannot create subfolders inside this folder."), frappe.PermissionError)
        if not department:
            department = frappe.db.get_value("Xavirgin DMS Folder", parent_folder, "department")
    else:
        roles = set(frappe.get_roles(user))
        if not is_dms_super_admin(user) and "Xavirgin Team Lead" not in roles:
            frappe.throw(_("Permission Denied: Only Administrators and Team Leads can create root folders."), frappe.PermissionError)

    doc = frappe.get_doc({
        "doctype": "Xavirgin DMS Folder",
        "folder_name": folder_name.strip(),
        "parent_folder": parent_folder or None,
        "department": department or None,
        "visibility": visibility or "Department Only",
        "created_by_user": user,
        "created_on": now_datetime(),
    })
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def export_folder_zip(folder_name: str):
    """Generates and streams a downloadable ZIP archive of all private file attachments in the folder."""
    perms = get_user_folder_permissions(folder_name, frappe.session.user)
    if not (perms["can_read"] and perms["can_download"]):
        frappe.throw(_("Access Denied: You do not have permission to export this folder."), frappe.PermissionError)

    folder = frappe.get_doc("Xavirgin DMS Folder", folder_name)
    zip_buffer = io.BytesIO()

    file_count = 0
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for f in folder.files:
            if f.item_type == "File Attachment" and f.file_attachment:
                rel_path = f.file_attachment.lstrip("/")
                if rel_path.startswith("private/files/"):
                    file_path = frappe.get_site_path("private", "files", rel_path[len("private/files/"):])
                elif rel_path.startswith("files/"):
                    file_path = frappe.get_site_path("public", "files", rel_path[len("files/"):])
                else:
                    file_path = frappe.get_site_path(rel_path)

                try:
                    with open(file_path, "rb") as file_to_zip:
                        zip_file.writestr(os.path.basename(file_path), file_to_zip.read())
                    file_count += 1
                except Exception:
                    pass

    log_dms_event("Export ZIP Archive", folder=folder.name, file_title=f"{file_count} files archived")
    frappe.db.commit()

    zip_buffer.seek(0)
    frappe.local.response.filename = f"{folder.folder_name}_Export.zip"
    frappe.local.response.filecontent = zip_buffer.read()
    frappe.local.response.type = "download"


# ==============================================================================
# Module-Level Permission Hooks for Xavirgin DMS Folder
# ==============================================================================

def get_permission_query_conditions(user: str = None) -> str:
    """SQL query filter restricting folders to authorized members (with properly escaped roles tuple)."""
    u = user or frappe.session.user
    if not u or u == "Guest":
        return "1=0"

    if is_dms_super_admin(u):
        return ""

    ctx = resolve_employee_context(user_id=u)
    emp_dept = frappe.db.escape(ctx.get("department") or "")
    escaped_user = frappe.db.escape(u)

    user_roles = [r for r in frappe.get_roles(u) if r]
    escaped_roles = ", ".join(frappe.db.escape(r) for r in user_roles) if user_roles else "''"

    return f"""(
        (`tabXavirgin DMS Folder`.visibility = 'Public (All Active Employees)')
        OR (`tabXavirgin DMS Folder`.created_by_user = {escaped_user})
        OR (`tabXavirgin DMS Folder`.owner = {escaped_user})
        OR (`tabXavirgin DMS Folder`.visibility = 'Department Only' AND `tabXavirgin DMS Folder`.department = {emp_dept})
        OR (`tabXavirgin DMS Folder`.name IN (
            SELECT parent FROM `tabXavirgin DMS Permission`
            WHERE (permission_type = 'User' AND user = {escaped_user} AND allow_read = 1)
               OR (permission_type = 'Role' AND role IN ({escaped_roles}) AND allow_read = 1)
        ))
    )"""


def has_permission(doc, ptype="read", user=None, debug=False) -> bool:
    u = user or frappe.session.user
    if not u or u == "Guest":
        return False

    if is_dms_super_admin(u):
        return True

    if isinstance(doc, str) or not doc:
        return True

    perms = get_user_folder_permissions(doc.name, user=u)
    if ptype in ("read", "select", "print", "report", "export"):
        return perms["can_read"]
    if ptype in ("write", "create"):
        return perms["can_edit"] or perms["can_upload"]
    if ptype == "delete":
        return perms["can_delete"]
    return perms["can_read"]