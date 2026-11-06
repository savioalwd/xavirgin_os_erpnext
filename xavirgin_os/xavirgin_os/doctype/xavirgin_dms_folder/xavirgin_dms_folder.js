frappe.ui.form.on("Xavirgin DMS Folder", {
    onload(frm) {
        if (frm.is_new() && !frm.doc.created_by_user) {
            frm.set_value("created_by_user", frappe.session.user);
        }
    },

    refresh(frm) {
        if (frm.is_new()) return;
        frm._xav_active_dms_tab = frm._xav_active_dms_tab || "all";

        frappe.call({
            method: "xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder.get_dms_folder_workspace",
            args: { folder_name: frm.doc.name },
            callback(r) {
                const data = r.message || {};
                const perms = data.permissions || {};

                // Enforce Read-Only UI if user is not Folder Admin / Upload authorized
                if (!perms.can_edit && !perms.can_upload) {
                    frm.disable_save();
                    frm.set_read_only();
                } else {
                    frm.events.bind_folder_action_buttons(frm, data);
                }

                if (perms.can_download) {
                    frm.add_custom_button(__("📦 Export Folder ZIP"), () => {
                        window.open(
                            `/api/method/xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder.export_folder_zip?folder_name=${encodeURIComponent(frm.doc.name)}`
                        );
                    });
                }

                frm.events.render_folder_workspace(frm, data);
            },
        });
    },

    bind_folder_action_buttons(frm, data) {
        const perms = data.permissions || {};
        if (perms.can_upload) {
            frm.add_custom_button(__("📎 Upload File"), () => {
                let d = new frappe.ui.Dialog({
                    title: __("Upload Document to {0}", [frm.doc.folder_name]),
                    fields: [
                        { fieldname: "title", label: __("Document Title / Name"), fieldtype: "Data", reqd: 1 },
                        { fieldname: "file_attachment", label: __("Select File (Private Storage)"), fieldtype: "Attach", reqd: 1 },
                        { fieldname: "notes", label: __("Description / Notes"), fieldtype: "Small Text" },
                    ],
                    primary_action_label: __("Upload & Save"),
                    primary_action(values) {
                        d.hide();
                        frm.add_child("files", {
                            item_type: "File Attachment",
                            title: values.title,
                            file_attachment: values.file_attachment,
                            folder: frm.doc.name,
                            notes: values.notes || "",
                        });
                        frm.refresh_field("files");
                        frm.save();
                    },
                });
                d.show();
            }).addClass("btn-primary");

            frm.add_custom_button(__("🔑 Add Secure Credential"), () => {
                let d = new frappe.ui.Dialog({
                    title: __("Add Portal Credential to {0}", [frm.doc.folder_name]),
                    fields: [
                        { fieldname: "title", label: __("Service / Credential Name (e.g. AWS Production)"), fieldtype: "Data", reqd: 1 },
                        { fieldname: "credential_url", label: __("Portal / Service URL"), fieldtype: "Data" },
                        { fieldname: "credential_username", label: __("Username / Email / ID"), fieldtype: "Data", reqd: 1 },
                        { fieldname: "credential_password", label: __("Password / Secret Key (AES Encrypted)"), fieldtype: "Password", reqd: 1 },
                        { fieldname: "notes", label: __("Access Notes"), fieldtype: "Small Text" },
                    ],
                    primary_action_label: __("Save Credential"),
                    primary_action(values) {
                        d.hide();
                        frm.add_child("files", {
                            item_type: "Login Credential",
                            title: values.title,
                            credential_url: values.credential_url,
                            credential_username: values.credential_username,
                            credential_password: values.credential_password,
                            folder: frm.doc.name,
                            notes: values.notes || "",
                        });
                        frm.refresh_field("files");
                        frm.save();
                    },
                });
                d.show();
            });

            frm.add_custom_button(__("📁 New Subfolder"), () => {
                let d = new frappe.ui.Dialog({
                    title: __("Create Subfolder inside {0}", [frm.doc.folder_name]),
                    fields: [
                        { fieldname: "folder_name", label: __("Subfolder Name"), fieldtype: "Data", reqd: 1 },
                        {
                            fieldname: "visibility",
                            label: __("Visibility Scope"),
                            fieldtype: "Select",
                            options: "Public (All Active Employees)\nDepartment Only\nRestricted (Permissions Table Only)",
                            default: frm.doc.visibility || "Department Only",
                        },
                    ],
                    primary_action_label: __("Create Subfolder"),
                    primary_action(values) {
                        d.hide();
                        frappe.call({
                            method: "xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder.create_dms_subfolder",
                            args: {
                                folder_name: values.folder_name,
                                parent_folder: frm.doc.name,
                                department: frm.doc.department,
                                visibility: values.visibility,
                            },
                            callback(res) {
                                if (res.message) {
                                    frappe.show_alert({ message: __("Subfolder created!"), indicator: "green" });
                                    frm.reload_doc();
                                }
                            },
                        });
                    },
                });
                d.show();
            });
        }
    },

    render_folder_workspace(frm, data) {
        const perms = data.permissions || {};
        const tab = frm._xav_active_dms_tab || "all";
        const files = data.files || [];
        const creds = data.credentials || [];
        const subs = data.subfolders || [];
        const rules = data.access_rules || [];
        const logs = data.audit_logs || [];

        // Interactive Breadcrumbs
        const crumbsHtml = [`<a href="/app/xavirgin-dms-folder" style="color:#2563eb; font-weight:700; text-decoration:none;">🗄️ Company Drive</a>`]
            .concat(
                (data.breadcrumbs || []).map((b, idx, arr) => {
                    if (idx === arr.length - 1) {
                        return `<span style="font-weight:800; color:#0f172a;">📁 ${frappe.utils.escape_html(b.folder_name)}</span>`;
                    }
                    return b.accessible
                        ? `<a href="/app/xavirgin-dms-folder/${encodeURIComponent(b.name)}" style="color:#2563eb; font-weight:600; text-decoration:none;">📁 ${frappe.utils.escape_html(b.folder_name)}</a>`
                        : `<span style="color:#94a3b8;">🔒 ${frappe.utils.escape_html(b.folder_name)}</span>`;
                })
            )
            .join(` <span style="color:#94a3b8; margin:0 4px;">/</span> `);

        const visStyle =
            data.visibility === "Public (All Active Employees)"
                ? { bg: "#dcfce7", text: "#166534", label: "🌐 Shared / Public" }
                : data.visibility === "Department Only"
                ? { bg: "#dbeafe", text: "#1e40af", label: `🛡️ Dept: ${data.department}` }
                : { bg: "#fee2e2", text: "#991b1b", label: "🔒 Restricted Vault" };

        const permBadge = perms.is_folder_admin
            ? `<span style="background:#f3e8ff; color:#6b21a8; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700;">👑 Admin Managed</span>`
            : perms.can_upload
            ? `<span style="background:#e0f2fe; color:#0369a1; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700;">⬆️ Upload Enabled</span>`
            : `<span style="background:#f1f5f9; color:#475569; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700;">👁️ Read Only</span>`;

        const tabBtn = (id, label, count) => {
            const act = tab === id;
            return `<button class="btn btn-xs xav-dms-ws-tab" data-tab="${id}" style="font-weight:700; border-radius:999px; padding:4px 12px; background:${act ? "#2563eb" : "#f1f5f9"}; color:${act ? "#fff" : "#334155"}; border:none;">
                ${label} ${count !== undefined ? `(${count})` : ""}
            </button>`;
        };

        // Subfolders Section
        let subfoldersHtml = "";
        if ((tab === "all" || tab === "subfolders") && subs.length > 0) {
            subfoldersHtml = `
            <div style="margin-bottom:14px;">
                <div style="font-size:11px; font-weight:800; color:#64748b; text-transform:uppercase; margin-bottom:6px;">📂 Subfolders (${subs.length})</div>
                <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(210px, 1fr)); gap:8px;">
                    ${subs
                        .map(
                            (sf) => `
                        <a href="/app/xavirgin-dms-folder/${encodeURIComponent(sf.name)}" style="display:flex; align-items:center; gap:10px; padding:10px 12px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; text-decoration:none; color:#0f172a;">
                            <span style="font-size:20px;">📁</span>
                            <div style="min-width:0; flex:1;">
                                <div style="font-size:12px; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${frappe.utils.escape_html(sf.folder_name)}</div>
                                <div style="font-size:10px; color:#64748b;">Updated ${sf.modified_date}</div>
                            </div>
                        </a>`
                        )
                        .join("")}
                </div>
            </div>`;
        } else if (tab === "subfolders" && subs.length === 0) {
            subfoldersHtml = `<div class="text-muted" style="padding:12px;">No subfolders inside this folder.</div>`;
        }

        // Files Section
        let filesHtml = "";
        if (tab === "all" || tab === "files") {
            const fileRows = files
                .map((f) => {
                    const b = f.badge || {};
                    const itemActions = perms.can_edit
                        ? `<button class="btn btn-xs btn-default xav-dms-rename-btn" data-row="${f.row_name}" data-title="${frappe.utils.escape_html(f.title)}" title="Rename">✏️</button>
                           <button class="btn btn-xs btn-default xav-dms-move-btn" data-row="${f.row_name}" title="Move to Folder">📁↗</button>
                           ${perms.can_delete ? `<button class="btn btn-xs btn-danger xav-dms-del-btn" data-row="${f.row_name}" title="Delete">🗑️</button>` : ""}`
                        : "";

                    return `
                    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; padding:8px 12px; background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; margin-bottom:6px;">
                        <div style="display:flex; align-items:center; gap:10px; min-width:0; flex:1;">
                            <span style="background:${b.bg}; color:${b.color}; padding:4px 8px; border-radius:6px; font-weight:800; font-size:11px;">
                                ${b.icon} ${b.ext}
                            </span>
                            <div style="min-width:0;">
                                <div style="font-size:13px; font-weight:700; color:#0f172a;">${frappe.utils.escape_html(f.title)}</div>
                                <div style="font-size:11px; color:#64748b;">
                                    Size: ${f.file_size} • Uploaded: ${f.uploaded_date} by ${frappe.utils.escape_html(f.owner)}
                                    ${f.notes ? `• ${frappe.utils.escape_html(f.notes)}` : ""}
                                </div>
                            </div>
                        </div>
                        <div style="display:flex; align-items:center; gap:6px;">
                            ${
                                f.file_attachment
                                    ? `<a href="${f.file_attachment}" target="_blank" class="btn btn-xs btn-primary" style="font-weight:700;">⬇️ Open / Download</a>`
                                    : `<span style="font-size:11px; color:#94a3b8;">🔒 Download Restricted</span>`
                            }
                            ${itemActions}
                        </div>
                    </div>`;
                })
                .join("");

            filesHtml = `
            <div style="margin-bottom:14px;">
                <div style="font-size:11px; font-weight:800; color:#64748b; text-transform:uppercase; margin-bottom:6px;">📄 Documents & Files (${files.length})</div>
                ${fileRows || `<div style="font-size:12px; color:#94a3b8; padding:10px; background:#f8fafc; border-radius:8px;">No files uploaded to this folder yet.</div>`}
            </div>`;
        }

        // Credentials Vault Section
        let credsHtml = "";
        if (tab === "all" || tab === "credentials") {
            const credRows = creds
                .map((c) => {
                    const adminBtns = perms.can_edit
                        ? `<button class="btn btn-xs btn-default xav-dms-rename-btn" data-row="${c.row_name}" data-title="${frappe.utils.escape_html(c.title)}" title="Rename">✏️</button>
                           ${perms.can_delete ? `<button class="btn btn-xs btn-danger xav-dms-del-btn" data-row="${c.row_name}" title="Delete">🗑️</button>` : ""}`
                        : "";

                    return `
                    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; padding:10px 12px; background:#fffbeb; border:1px solid #fde68a; border-radius:8px; margin-bottom:6px;">
                        <div style="min-width:0; flex:1;">
                            <div style="display:flex; align-items:center; gap:8px;">
                                <span style="background:#fef3c7; color:#92400e; padding:2px 8px; border-radius:6px; font-weight:800; font-size:11px;">🔑 CREDENTIAL</span>
                                <span style="font-size:13px; font-weight:800; color:#0f172a;">${frappe.utils.escape_html(c.title)}</span>
                                ${c.credential_url ? `<a href="${c.credential_url}" target="_blank" style="font-size:11px; color:#2563eb; font-weight:600;">🔗 Open Portal ↗</a>` : ""}
                            </div>
                            <div style="font-size:12px; color:#334155; margin-top:4px;">
                                <strong>Username / ID:</strong> <code style="color:#0f172a;">${frappe.utils.escape_html(c.credential_username || "-")}</code>
                                • <strong>Password:</strong> <code class="xav-pw-mask-${c.row_name}" style="color:#b45309; font-weight:700;">${c.masked_password}</code>
                            </div>
                            ${c.notes ? `<div style="font-size:11px; color:#64748b; margin-top:2px;">Note: ${frappe.utils.escape_html(c.notes)}</div>` : ""}
                        </div>
                        <div style="display:flex; align-items:center; gap:6px;">
                            <button class="btn btn-xs btn-default xav-reveal-cred-btn" data-row="${c.row_name}" style="font-weight:700;">👁️ Reveal</button>
                            <button class="btn btn-xs btn-default xav-copy-cred-btn" data-row="${c.row_name}" style="font-weight:700;">📋 Copy Password</button>
                            ${adminBtns}
                        </div>
                    </div>`;
                })
                .join("");

            credsHtml = `
            <div style="margin-bottom:14px;">
                <div style="font-size:11px; font-weight:800; color:#92400e; text-transform:uppercase; margin-bottom:6px;">🔐 Passwords & Sensitive Credentials Vault (${creds.length})</div>
                ${credRows || `<div style="font-size:12px; color:#94a3b8; padding:10px; background:#f8fafc; border-radius:8px;">No credentials stored in this folder.</div>`}
            </div>`;
        }

        // Permissions & Audit Tab
        let accessHtml = "";
        if (tab === "access") {
            const ruleRows = rules
                .map(
                    (r) => `
                <tr>
                    <td style="padding:6px 8px; font-weight:700;">${frappe.utils.escape_html(r.target)}</td>
                    <td style="padding:6px 8px; text-align:center;">${r.read ? "✅" : "—"}</td>
                    <td style="padding:6px 8px; text-align:center;">${r.download ? "✅" : "—"}</td>
                    <td style="padding:6px 8px; text-align:center;">${r.upload ? "✅" : "—"}</td>
                    <td style="padding:6px 8px; text-align:center;">${r.edit ? "👑 Admin" : "—"}</td>
                    <td style="padding:6px 8px; text-align:center;">${r.delete ? "✅" : "—"}</td>
                </tr>`
                )
                .join("");

            const auditRows = logs
                .map(
                    (lg) => `
                <tr>
                    <td style="padding:5px 8px;">${lg.timestamp}</td>
                    <td style="padding:5px 8px; font-weight:600;">${frappe.utils.escape_html(lg.user)}</td>
                    <td style="padding:5px 8px;"><span style="background:#f1f5f9; padding:2px 6px; border-radius:4px; font-weight:700;">${frappe.utils.escape_html(lg.action_type)}</span></td>
                    <td style="padding:5px 8px;">${frappe.utils.escape_html(lg.file_title)}</td>
                    <td style="padding:5px 8px; color:#64748b;">${frappe.utils.escape_html(lg.ip_address)}</td>
                </tr>`
                )
                .join("");

            accessHtml = `
            <div>
                <div style="margin-bottom:12px; font-size:12px;">
                    <strong>👑 Folder Administrators:</strong> ${(data.folder_admins || []).map((a) => `<span style="background:#f3e8ff; color:#6b21a8; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700; margin-right:4px;">${frappe.utils.escape_html(a)}</span>`).join("")}
                </div>
                <table class="table table-bordered" style="font-size:11px; background:#fff;">
                    <thead><tr style="background:#f8fafc;"><th>User / Role</th><th>Read</th><th>Download</th><th>Upload</th><th>Edit / Admin</th><th>Delete</th></tr></thead>
                    <tbody>${ruleRows || `<tr><td colspan="6" class="text-center text-muted">No custom overrides — governed by ${frappe.utils.escape_html(data.visibility)} scope.</td></tr>`}</tbody>
                </table>
                ${
                    perms.is_folder_admin
                        ? `<div style="font-size:11px; font-weight:800; color:#64748b; text-transform:uppercase; margin:12px 0 6px 0;">🛡️ Folder Security Audit Log (Last 20 Events)</div>
                           <table class="table table-bordered" style="font-size:11px; background:#fff;">
                               <thead><tr style="background:#f8fafc;"><th>Timestamp</th><th>User</th><th>Action</th><th>Item</th><th>IP</th></tr></thead>
                               <tbody>${auditRows || `<tr><td colspan="5" class="text-center text-muted">No audit events recorded yet.</td></tr>`}</tbody>
                           </table>`
                        : ""
                }
            </div>`;
        }

        const html = `
        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:14px 16px; margin-bottom:12px; box-shadow:0 1px 4px rgba(0,0,0,0.03);">
            <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px; padding-bottom:10px; border-bottom:1px solid #f1f5f9;">
                <div style="font-size:13px;">
                    ${crumbsHtml}
                </div>
                <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                    <span style="background:${visStyle.bg}; color:${visStyle.text}; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700;">
                        ${frappe.utils.escape_html(visStyle.label)}
                    </span>
                    ${permBadge}
                </div>
            </div>

            <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px; padding:10px 0; border-bottom:1px solid #f1f5f9; margin-bottom:12px;">
                <div style="display:flex; flex-wrap:wrap; gap:6px;">
                    ${tabBtn("all", "🗂️ Overview", subs.length + files.length + creds.length)}
                    ${tabBtn("files", "📄 Files", files.length)}
                    ${tabBtn("subfolders", "📂 Subfolders", subs.length)}
                    ${tabBtn("credentials", "🔑 Credentials Vault", creds.length)}
                    ${tabBtn("access", "🛡️ Access & Audit", rules.length)}
                </div>
                <div style="font-size:11px; color:#64748b;">
                    Owner: <b>${frappe.utils.escape_html(data.created_by)}</b> • Updated: ${data.modified_on}
                </div>
            </div>

            ${subfoldersHtml}
            ${filesHtml}
            ${credsHtml}
            ${accessHtml}
        </div>`;

        frm.dashboard.clear_headline();
        frm.dashboard.set_headline_alert(html);

        const $wrap = frm.dashboard.wrapper;

        $wrap.find(".xav-dms-ws-tab").on("click", function () {
            frm._xav_active_dms_tab = $(this).attr("data-tab");
            frm.events.render_folder_workspace(frm, data);
        });

        // Reveal Credential Password
        $wrap.find(".xav-reveal-cred-btn").on("click", function () {
            const rowName = $(this).attr("data-row");
            const $code = $wrap.find(`.xav-pw-mask-${rowName}`);
            if ($(this).attr("data-revealed") === "1") {
                $code.text("••••••••••••");
                $(this).attr("data-revealed", "0").text("👁️ Reveal");
                return;
            }
            const $btn = $(this);
            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder.reveal_dms_credential",
                args: { folder_name: frm.doc.name, row_name: rowName },
                callback(res) {
                    if (res.message) {
                        $code.text(res.message.password || "(Empty)");
                        $btn.attr("data-revealed", "1").text("🙈 Hide");
                    }
                },
            });
        });

        // Copy Credential Password
        $wrap.find(".xav-copy-cred-btn").on("click", function () {
            const rowName = $(this).attr("data-row");
            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder.reveal_dms_credential",
                args: { folder_name: frm.doc.name, row_name: rowName },
                callback(res) {
                    if (res.message && res.message.password) {
                        frappe.utils.copy_to_clipboard(res.message.password);
                        frappe.show_alert({ message: __("Password copied to clipboard (Audit logged)."), indicator: "green" });
                    }
                },
            });
        });

        // Rename Item
        $wrap.find(".xav-dms-rename-btn").on("click", function () {
            const rowName = $(this).attr("data-row");
            const curTitle = $(this).attr("data-title");
            frappe.prompt(
                [{ fieldname: "new_title", label: __("New Title"), fieldtype: "Data", default: curTitle, reqd: 1 }],
                (values) => {
                    frappe.call({
                        method: "xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder.manage_dms_item",
                        args: { action: "rename", folder_name: frm.doc.name, row_name: rowName, new_title: values.new_title },
                        callback() {
                            frm.reload_doc();
                        },
                    });
                },
                __("Rename Item"),
                __("Save")
            );
        });

        // Move Item
        $wrap.find(".xav-dms-move-btn").on("click", function () {
            const rowName = $(this).attr("data-row");
            frappe.prompt(
                [{ fieldname: "target_folder", label: __("Destination Folder"), fieldtype: "Link", options: "Xavirgin DMS Folder", reqd: 1 }],
                (values) => {
                    frappe.call({
                        method: "xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder.manage_dms_item",
                        args: { action: "move", folder_name: frm.doc.name, row_name: rowName, target_folder: values.target_folder },
                        callback() {
                            frappe.show_alert({ message: __("Item moved to {0}", [values.target_folder]), indicator: "green" });
                            frm.reload_doc();
                        },
                    });
                },
                __("Move Item to Another Folder"),
                __("Move")
            );
        });

        // Delete Item
        $wrap.find(".xav-dms-del-btn").on("click", function () {
            const rowName = $(this).attr("data-row");
            frappe.confirm(__("Permanently delete this item from the folder?"), () => {
                frappe.call({
                    method: "xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder.manage_dms_item",
                    args: { action: "delete", folder_name: frm.doc.name, row_name: rowName },
                    callback() {
                        frappe.show_alert({ message: __("Item deleted."), indicator: "orange" });
                        frm.reload_doc();
                    },
                });
            });
        });
    },
});