frappe.listview_settings["Xavirgin DMS Folder"] = {
    add_fields: ["folder_name", "parent_folder", "department", "visibility", "created_by_user", "modified"],

    onload(listview) {
        listview._xav_current_folder = "";
        listview._xav_nav_scope = "root"; // root | my_department | public | all
        listview._xav_view_mode = "grid"; // grid | list
        listview._xav_file_type = "";
        listview._xav_sort_by = "folder_name";
        listview._xav_search = "";
        listview._xav_collapsed = false;

        if (!listview.page.wrapper.find(".xav-dms-drive-browser").length) {
            const $drive = $(`<div class="xav-dms-drive-browser" style="padding: 12px 15px 4px 15px;"></div>`);
            listview.page.main.prepend($drive);
        }

        listview.refresh_drive_browser = function () {
            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder.get_dms_drive_browser",
                args: {
                    parent_folder: listview._xav_current_folder || "",
                    nav_scope: listview._xav_nav_scope || "root",
                    search_text: listview._xav_search || "",
                    file_type_filter: listview._xav_file_type || "",
                    sort_by: listview._xav_sort_by || "folder_name",
                },
                callback(r) {
                    if (r.message) {
                        listview.render_drive_browser(r.message);
                    }
                },
            });
        };

        listview.render_drive_browser = function (data) {
            const $container = listview.page.wrapper.find(".xav-dms-drive-browser");
            if (!$container.length) return;

            const perms = data.permissions || {};
            const folders = data.folders || [];
            const items = data.items || [];
            const mode = listview._xav_view_mode || "grid";

            // Breadcrumbs
            let crumbs = [
                `<a href="#" class="xav-drive-crumb" data-folder="" style="color:#2563eb; font-weight:800; text-decoration:none;">🗄️ My Drive</a>`,
            ];
            (data.breadcrumbs || []).forEach((b, idx, arr) => {
                if (idx === arr.length - 1) {
                    crumbs.push(`<span style="font-weight:800; color:#0f172a;">📁 ${frappe.utils.escape_html(b.folder_name)}</span>`);
                } else {
                    crumbs.push(
                        `<a href="#" class="xav-drive-crumb" data-folder="${frappe.utils.escape_html(b.name)}" style="color:#2563eb; font-weight:600; text-decoration:none;">📁 ${frappe.utils.escape_html(b.folder_name)}</a>`
                    );
                }
            });

            // Sidebar Items
            const sideBtn = (scope, icon, label) => {
                const act = !listview._xav_current_folder && listview._xav_nav_scope === scope;
                return `<div class="xav-drive-nav-item" data-scope="${scope}" style="padding:7px 10px; border-radius:8px; font-size:12px; font-weight:${act ? "800" : "600"}; background:${act ? "#eff6ff" : "transparent"}; color:${act ? "#1d4ed8" : "#334155"}; cursor:pointer; margin-bottom:4px; display:flex; align-items:center; gap:8px;">
                    <span>${icon}</span><span>${label}</span>
                </div>`;
            };

            // Render Folders (Grid vs List)
            let foldersSection = "";
            if (folders.length > 0) {
                if (mode === "grid") {
                    const cards = folders
                        .map(
                            (f) => `
                        <div class="xav-drive-folder-card" data-folder="${frappe.utils.escape_html(f.name)}" style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:12px; cursor:pointer; display:flex; flex-direction:column; justify-content:space-between; box-shadow:0 1px 2px rgba(0,0,0,0.03); transition:all 0.15s;">
                            <div>
                                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px;">
                                    <span style="font-size:24px;">📁</span>
                                    <button class="btn btn-xs btn-default xav-open-folder-doc" data-folder="${frappe.utils.escape_html(f.name)}" title="Open Folder Settings" style="font-size:10px; font-weight:700;">⚙️ Details</button>
                                </div>
                                <div style="font-size:13px; font-weight:800; color:#0f172a; margin-bottom:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                                    ${frappe.utils.escape_html(f.folder_name)}
                                </div>
                                <div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:6px;">
                                    <span style="background:#f3e8ff; color:#6b21a8; padding:1px 6px; border-radius:999px; font-size:9px; font-weight:700;">
                                        🛡️ ${frappe.utils.escape_html(f.department)}
                                    </span>
                                    <span style="background:${f.is_folder_admin ? "#dcfce7" : "#f1f5f9"}; color:${f.is_folder_admin ? "#166534" : "#475569"}; padding:1px 6px; border-radius:999px; font-size:9px; font-weight:700;">
                                        ${frappe.utils.escape_html(f.access_badge)}
                                    </span>
                                </div>
                            </div>
                            <div style="display:flex; justify-content:space-between; font-size:10px; color:#64748b; padding-top:6px; border-top:1px solid #f1f5f9;">
                                <span>📄 ${f.files_count} • 🔑 ${f.credentials_count} • 📂 ${f.subfolders_count}</span>
                                <span>${f.modified_date}</span>
                            </div>
                        </div>`
                        )
                        .join("");
                    foldersSection = `
                    <div style="margin-bottom:14px;">
                        <div style="font-size:11px; font-weight:800; color:#64748b; text-transform:uppercase; margin-bottom:8px;">📁 Folders (${folders.length})</div>
                        <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(220px, 1fr)); gap:10px;">
                            ${cards}
                        </div>
                    </div>`;
                } else {
                    const rows = folders
                        .map(
                            (f) => `
                        <tr class="xav-drive-folder-card" data-folder="${frappe.utils.escape_html(f.name)}" style="cursor:pointer;">
                            <td style="font-weight:700; color:#0f172a;">📁 ${frappe.utils.escape_html(f.folder_name)}</td>
                            <td><span style="background:#f3e8ff; color:#6b21a8; padding:2px 6px; border-radius:999px; font-size:10px; font-weight:700;">${frappe.utils.escape_html(f.department)}</span></td>
                            <td>📄 ${f.files_count} Files, 🔑 ${f.credentials_count} Creds, 📂 ${f.subfolders_count} Subfolders</td>
                            <td><span style="font-size:10px; font-weight:700;">${frappe.utils.escape_html(f.access_badge)}</span></td>
                            <td>${f.modified_date}</td>
                            <td style="text-align:right;"><button class="btn btn-xs btn-default xav-open-folder-doc" data-folder="${frappe.utils.escape_html(f.name)}">Open Workspace</button></td>
                        </tr>`
                        )
                        .join("");
                    foldersSection = `
                    <div style="margin-bottom:14px;">
                        <div style="font-size:11px; font-weight:800; color:#64748b; text-transform:uppercase; margin-bottom:6px;">📁 Folders (${folders.length})</div>
                        <table class="table table-bordered" style="background:#fff; font-size:12px;">
                            <thead><tr style="background:#f8fafc;"><th>Folder Name</th><th>Department</th><th>Contents</th><th>Access</th><th>Modified</th><th></th></tr></thead>
                            <tbody>${rows}</tbody>
                        </table>
                    </div>`;
                }
            }

            // Render Files & Credentials
            let itemsSection = "";
            if (items.length > 0) {
                const itemCards = items
                    .map((it) => {
                        const b = it.type_badge || {};
                        if (it.is_password_protected) {
                            return `
                            <div style="background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:10px 12px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:6px;">
                                <div>
                                    <div style="display:flex; align-items:center; gap:6px;">
                                        <span style="background:#fef3c7; color:#92400e; padding:2px 7px; border-radius:6px; font-size:10px; font-weight:800;">🔑 CREDENTIAL</span>
                                        <span style="font-weight:800; font-size:13px; color:#0f172a;">${frappe.utils.escape_html(it.title)}</span>
                                        <span style="font-size:11px; color:#64748b;">(in 📁 ${frappe.utils.escape_html(it.folder_name)})</span>
                                    </div>
                                    <div style="font-size:11px; color:#334155; margin-top:3px;">
                                        User: <code>${frappe.utils.escape_html(it.credential_username || "-")}</code> • Password: <code class="xav-drv-pw-${it.row_name}">••••••••••••</code>
                                    </div>
                                </div>
                                <div style="display:flex; gap:6px;">
                                    <button class="btn btn-xs btn-default xav-drv-reveal-btn" data-folder="${frappe.utils.escape_html(it.folder)}" data-row="${it.row_name}" style="font-weight:700;">👁️ Reveal</button>
                                    <button class="btn btn-xs btn-default xav-drv-copy-btn" data-folder="${frappe.utils.escape_html(it.folder)}" data-row="${it.row_name}" style="font-weight:700;">📋 Copy</button>
                                </div>
                            </div>`;
                        }

                        return `
                        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:8px 12px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:6px;">
                            <div style="display:flex; align-items:center; gap:10px;">
                                <span style="background:${b.bg}; color:${b.color}; padding:4px 8px; border-radius:6px; font-size:11px; font-weight:800;">${b.icon} ${b.ext}</span>
                                <div>
                                    <div style="font-size:13px; font-weight:700; color:#0f172a;">${frappe.utils.escape_html(it.title)}</div>
                                    <div style="font-size:10px; color:#64748b;">📁 ${frappe.utils.escape_html(it.folder_name)} • ${it.file_size} • ${it.modified_date}</div>
                                </div>
                            </div>
                            <div style="display:flex; gap:6px;">
                                ${
                                    it.file_attachment
                                        ? `<a href="${it.file_attachment}" target="_blank" class="btn btn-xs btn-primary" style="font-weight:700;">⬇️ Download</a>`
                                        : `<span style="font-size:10px; color:#94a3b8;">🔒 Restricted</span>`
                                }
                                <button class="btn btn-xs btn-default xav-open-folder-doc" data-folder="${frappe.utils.escape_html(it.folder)}">📁 Folder</button>
                            </div>
                        </div>`;
                    })
                    .join("");

                itemsSection = `
                <div>
                    <div style="font-size:11px; font-weight:800; color:#64748b; text-transform:uppercase; margin-bottom:8px;">📄 Files & Vault Credentials (${items.length})</div>
                    ${itemCards}
                </div>`;
            }

            const html = `
            <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:14px 16px; margin-bottom:10px; box-shadow:0 1px 4px rgba(0,0,0,0.03);">
                <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px; padding-bottom:10px; border-bottom:1px solid #f1f5f9; margin-bottom:${listview._xav_collapsed ? "0" : "12px"};">
                    <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                        ${
                            data.current_folder
                                ? `<button class="btn btn-xs btn-default xav-drive-up-btn" data-parent="${frappe.utils.escape_html(data.parent_of_current || "")}" style="font-weight:700;">⬅️ Up</button>`
                                : ""
                        }
                        <div style="font-size:13px;">${crumbs.join(` <span style="color:#94a3b8; margin:0 4px;">/</span> `)}</div>
                    </div>

                    <div style="display:flex; flex-wrap:wrap; align-items:center; gap:6px;">
                        <input type="text" class="form-control input-xs xav-drive-search" placeholder="Search files, folders, secrets..." value="${frappe.utils.escape_html(listview._xav_search)}" style="width:180px; height:28px;" />
                        <select class="form-control input-xs xav-drive-type-filter" style="width:130px; height:28px; font-weight:600;">
                            <option value="">All File Types</option>
                            <option value="PDF" ${listview._xav_file_type === "PDF" ? "selected" : ""}>📕 PDFs</option>
                            <option value="Document" ${listview._xav_file_type === "Document" ? "selected" : ""}>📘 Documents</option>
                            <option value="Spreadsheet" ${listview._xav_file_type === "Spreadsheet" ? "selected" : ""}>📗 Spreadsheets</option>
                            <option value="Image" ${listview._xav_file_type === "Image" ? "selected" : ""}>🖼️ Images</option>
                            <option value="Archive" ${listview._xav_file_type === "Archive" ? "selected" : ""}>📦 ZIP Archives</option>
                            <option value="Credential" ${listview._xav_file_type === "Credential" ? "selected" : ""}>🔑 Credentials</option>
                        </select>
                        <button class="btn btn-xs btn-default xav-drive-mode-btn" style="font-weight:700;">
                            ${mode === "grid" ? "☰ List View" : "⊞ Grid View"}
                        </button>
                        ${
                            perms.can_upload
                                ? `<button class="btn btn-xs btn-primary xav-drive-new-folder-btn" style="font-weight:700;">➕ New Folder</button>`
                                : ""
                        }
                        ${
                            data.current_folder
                                ? `<button class="btn btn-xs btn-default xav-open-folder-doc" data-folder="${frappe.utils.escape_html(data.current_folder)}" style="font-weight:700;">⚙️ Manage Folder</button>`
                                : ""
                        }
                        <button class="btn btn-xs btn-default xav-drive-collapse-btn" style="font-weight:600;">
                            ${listview._xav_collapsed ? "▼ Expand Drive" : "▲ Collapse"}
                        </button>
                    </div>
                </div>

                <div style="display:${listview._xav_collapsed ? "none" : "grid"}; grid-template-columns:190px 1fr; gap:14px;">
                    <div style="border-right:1px solid #f1f5f9; padding-right:10px;">
                        ${sideBtn("root", "🗄️", "Root Drive")}
                        ${sideBtn("my_department", "🛡️", "My Squad Drive")}
                        ${sideBtn("public", "🌐", "Shared / Public")}
                        ${sideBtn("all", "📂", "All Accessible")}
                    </div>

                    <div style="min-width:0;">
                        ${foldersSection}
                        ${itemsSection}
                        ${!folders.length && !items.length ? `<div style="padding:24px; text-align:center; color:#94a3b8; font-size:13px;">This folder or filter view is empty.</div>` : ""}
                    </div>
                </div>
            </div>`;

            $container.html(html);

            // Navigation Events
            $container.find(".xav-drive-nav-item").on("click", function () {
                listview._xav_current_folder = "";
                listview._xav_nav_scope = $(this).attr("data-scope");
                listview.refresh_drive_browser();
            });

            $container.find(".xav-drive-crumb").on("click", function (e) {
                e.preventDefault();
                listview._xav_current_folder = $(this).attr("data-folder") || "";
                listview.refresh_drive_browser();
            });

            $container.find(".xav-drive-up-btn").on("click", function () {
                listview._xav_current_folder = $(this).attr("data-parent") || "";
                listview.refresh_drive_browser();
            });

            $container.find(".xav-drive-folder-card").on("click", function () {
                const target = $(this).attr("data-folder");
                if (target) {
                    listview._xav_current_folder = target;
                    listview.refresh_drive_browser();
                }
            });

            $container.find(".xav-open-folder-doc").on("click", function (e) {
                e.stopPropagation();
                const target = $(this).attr("data-folder");
                if (target) frappe.set_route("Form", "Xavirgin DMS Folder", target);
            });

            $container.find(".xav-drive-search").on("change", function () {
                listview._xav_search = $(this).val() || "";
                listview.refresh_drive_browser();
            });

            $container.find(".xav-drive-type-filter").on("change", function () {
                listview._xav_file_type = $(this).val() || "";
                listview.refresh_drive_browser();
            });

            $container.find(".xav-drive-mode-btn").on("click", function () {
                listview._xav_view_mode = listview._xav_view_mode === "grid" ? "list" : "grid";
                listview.render_drive_browser(data);
            });

            $container.find(".xav-drive-collapse-btn").on("click", function () {
                listview._xav_collapsed = !listview._xav_collapsed;
                listview.render_drive_browser(data);
            });

            $container.find(".xav-drive-new-folder-btn").on("click", function () {
                let d = new frappe.ui.Dialog({
                    title: listview._xav_current_folder ? __("Create Subfolder") : __("Create New Root Folder"),
                    fields: [
                        { fieldname: "folder_name", label: __("Folder Name"), fieldtype: "Data", reqd: 1 },
                        { fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department", default: data.my_department || "" },
                        {
                            fieldname: "visibility",
                            label: __("Visibility Scope"),
                            fieldtype: "Select",
                            options: "Public (All Active Employees)\nDepartment Only\nRestricted (Permissions Table Only)",
                            default: "Department Only",
                        },
                    ],
                    primary_action_label: __("Create Folder"),
                    primary_action(values) {
                        d.hide();
                        frappe.call({
                            method: "xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder.create_dms_subfolder",
                            args: {
                                folder_name: values.folder_name,
                                parent_folder: listview._xav_current_folder || "",
                                department: values.department,
                                visibility: values.visibility,
                            },
                            callback() {
                                frappe.show_alert({ message: __("Folder created!"), indicator: "green" });
                                listview.refresh_drive_browser();
                                listview.refresh();
                            },
                        });
                    },
                });
                d.show();
            });

            // Credential Reveal & Copy inside Drive Browser
            $container.find(".xav-drv-reveal-btn").on("click", function () {
                const fName = $(this).attr("data-folder");
                const rName = $(this).attr("data-row");
                const $code = $container.find(`.xav-drv-pw-${rName}`);
                const $btn = $(this);
                if ($btn.attr("data-open") === "1") {
                    $code.text("••••••••••••");
                    $btn.attr("data-open", "0").text("👁️ Reveal");
                    return;
                }
                frappe.call({
                    method: "xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder.reveal_dms_credential",
                    args: { folder_name: fName, row_name: rName },
                    callback(res) {
                        if (res.message) {
                            $code.text(res.message.password || "(Empty)");
                            $btn.attr("data-open", "1").text("🙈 Hide");
                        }
                    },
                });
            });

            $container.find(".xav-drv-copy-btn").on("click", function () {
                const fName = $(this).attr("data-folder");
                const rName = $(this).attr("data-row");
                frappe.call({
                    method: "xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder.reveal_dms_credential",
                    args: { folder_name: fName, row_name: rName },
                    callback(res) {
                        if (res.message && res.message.password) {
                            frappe.utils.copy_to_clipboard(res.message.password);
                            frappe.show_alert({ message: __("Password copied (Audit logged)."), indicator: "green" });
                        }
                    },
                });
            });
        };

        listview.refresh_drive_browser();
    },

    refresh(listview) {
        if (listview.refresh_drive_browser) {
            listview.refresh_drive_browser();
        }
    },
};