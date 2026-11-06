frappe.ui.form.on("Xavirgin GitHub Activity", {
    refresh(frm) {
        if (frm.is_new()) return;

        const isMapped = Boolean(frm.doc.employee);
        const repo = frm.doc.repository || "";
        const ref = frm.doc.reference_id || "";
        let ghUrl = "";

        if (repo && repo.includes("/")) {
            if (ref.startsWith("PR #")) {
                const prNum = ref.replace("PR #", "").split(" ")[0];
                ghUrl = `https://github.com/${repo}/pull/${prNum}`;
            } else if (ref.startsWith("Issue #")) {
                const issNum = ref.replace("Issue #", "").split(" ")[0];
                ghUrl = `https://github.com/${repo}/issues/${issNum}`;
            } else if (ref && ref.length >= 7) {
                ghUrl = `https://github.com/${repo}/commit/${ref}`;
            } else {
                ghUrl = `https://github.com/${repo}`;
            }
        }

        if (ghUrl) {
            frm.add_custom_button(__("🔗 Open on GitHub ↗"), () => {
                window.open(ghUrl, "_blank");
            }).addClass("btn-primary");
        }

        if (frm.doc.daily_poa) {
            frm.add_custom_button(__("📋 Open Linked Daily POA"), () => {
                frappe.set_route("Form", "Xavirgin Daily POA", frm.doc.daily_poa);
            });
        }

        if (!isMapped && frappe.user.has_role(["System Manager", "Xavirgin HR Admin", "Xavirgin Team Lead"])) {
            frm.add_custom_button(__("👤 Link to Employee"), () => {
                frappe.prompt(
                    [
                        {
                            fieldname: "employee",
                            label: __("Select Employee (Saves @{0} to Employee Profile)", [frm.doc.github_username]),
                            fieldtype: "Link",
                            options: "Employee",
                            reqd: 1,
                        },
                    ],
                    (values) => {
                        frappe.call({
                            method: "xavirgin_os.xavirgin_os.doctype.xavirgin_github_activity.xavirgin_github_activity.link_activity_to_employee",
                            args: {
                                activity_name: frm.doc.name,
                                employee: values.employee,
                            },
                            freeze: true,
                            callback(r) {
                                if (r.message) {
                                    frappe.show_alert({
                                        message: __("Webhook linked to {0}!", [r.message.employee_name]),
                                        indicator: "green",
                                    });
                                    frm.reload_doc();
                                }
                            },
                        });
                    },
                    __("Map GitHub Webhook Event to Employee"),
                    __("Link Employee")
                );
            });
        }

        const badgeBg = isMapped ? "#dcfce7" : "#fef9c3";
        const badgeText = isMapped ? "#166534" : "#854d0e";
        const badgeLabel = isMapped ? `✅ Processed (${frm.doc.employee_name || frm.doc.employee})` : "⚠️ Unmapped GitHub Handle";

        const bannerHtml = `
        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:12px 16px; margin-bottom:10px; display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px;">
            <div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px;">
                <span style="background:${badgeBg}; color:${badgeText}; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px;">
                    ${frappe.utils.escape_html(badgeLabel)}
                </span>
                <span style="background:#e0e7ff; color:#3730a3; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px;">
                    📡 Event: ${frappe.utils.escape_html(frm.doc.event_type)} ${frm.doc.action ? `(${frappe.utils.escape_html(frm.doc.action)})` : ""}
                </span>
                <span style="background:#f3e8ff; color:#6b21a8; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px;">
                    📦 ${frappe.utils.escape_html(repo || "Repository")} ${frm.doc.branch ? `• 🌿 ${frappe.utils.escape_html(frm.doc.branch)}` : ""}
                </span>
                <span style="background:#fef3c7; color:#92400e; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px;">
                    ⚡ +${frm.doc.xp_awarded || 0} XP
                </span>
            </div>
            <div style="font-size:12px; color:#64748b; font-weight:600;">
                Sender: <code>@${frappe.utils.escape_html(frm.doc.github_username || "unknown")}</code>
            </div>
        </div>`;

        frm.dashboard.clear_headline();
        frm.dashboard.set_headline_alert(bannerHtml);
    },
});