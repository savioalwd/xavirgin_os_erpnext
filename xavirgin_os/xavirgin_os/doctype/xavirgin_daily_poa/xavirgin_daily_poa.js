frappe.ui.form.on("Xavirgin Daily POA", {
    setup(frm) {
        frm.add_fetch("employee", "employee_name", "employee_name");
        frm.add_fetch("employee", "department", "department");
        frm.add_fetch("employee", "designation", "designation");
        frm.add_fetch("employee", "reports_to", "reporting_manager");
    },

    onload(frm) {
        if (frm.is_new() && !frm.doc.poa_date) {
            frm.set_value("poa_date", frappe.datetime.get_today());
        }
        frm.trigger("bootstrap_employee_and_telemetry");
    },

    refresh(frm) {
        frm.trigger("bootstrap_employee_and_telemetry");
        frm.trigger("setup_workflow_buttons");
    },

    poa_date(frm) {
        if (frm.doc.poa_date) {
            frm.trigger("bootstrap_employee_and_telemetry");
        }
    },

    employee(frm) {
        if (frm.doc.employee) {
            frm.trigger("bootstrap_employee_and_telemetry");
        }
    },

    bootstrap_employee_and_telemetry(frm) {
        if (frm._bootstrapping_poa) return;
        frm._bootstrapping_poa = true;

        frappe.call({
            method: "xavirgin_os.xavirgin_os.doctype.xavirgin_daily_poa.xavirgin_daily_poa.get_session_poa_Bootstrap",
            args: {
                employee: frm.doc.employee || "",
                poa_date: frm.doc.poa_date || frappe.datetime.get_today(),
            },
            callback(r) {
                frm._bootstrapping_poa = false;
                const data = r.message || {};
                if (!data.has_employee) return;

                // 1. Auto-link Employee on new records without asking user
                if (frm.is_new()) {
                    if (!frm.doc.employee || (!data.is_admin && !data.is_team_lead && frm.doc.employee !== data.employee)) {
                        frm.doc.employee = data.employee;
                        frm.doc.employee_name = data.employee_name;
                        frm.doc.user_id = data.user_id;
                        frm.doc.department = data.department;
                        frm.doc.designation = data.designation;
                        frm.doc.reporting_manager = data.reporting_manager;
                        frm.refresh_fields(["employee", "employee_name", "user_id", "department", "designation", "reporting_manager"]);
                    }

                    // Lock Employee field for regular interns/employees so they never manually select it
                    if (!data.is_admin && !data.is_team_lead) {
                        frm.set_df_property("employee", "read_only", 1);
                    } else if (data.is_team_lead && !data.is_admin && data.session_department) {
                        frm.set_query("employee", () => ({
                            filters: { department: data.session_department, status: "Active" },
                        }));
                    }

                    // If a POA already exists for this employee + date, offer instant navigation
                    if (data.existing_poa && data.existing_poa.name) {
                        frappe.show_alert({
                            message: __("Opening existing Daily POA ({0}) for {1} on {2}...", [
                                data.existing_poa.name,
                                data.employee_name,
                                data.poa_date,
                            ]),
                            indicator: "blue",
                        });
                        frappe.set_route("Form", "Xavirgin Daily POA", data.existing_poa.name);
                        return;
                    }

                    // Auto-populate attendance fields on new unsaved form
                    if (data.attendance) {
                        frm.doc.attendance_verified = data.attendance.verified ? 1 : 0;
                        frm.doc.attendance_hours_logged = data.attendance.hours_logged || 0.0;
                        frm.doc.attendance_status = data.attendance.status || "Not Checked In";
                        frm.refresh_fields(["attendance_verified", "attendance_hours_logged", "attendance_status"]);

                        // Auto-populate tasks from attendance work logs if tasks table is empty
                        if ((!frm.doc.tasks || !frm.doc.tasks.length) && data.attendance.sessions && data.attendance.sessions.length) {
                            let addedAny = false;
                            data.attendance.sessions.forEach((sess) => {
                                let cleanLog = (sess.work_log || "").trim();
                                if (cleanLog) {
                                    let row = frm.add_child("tasks");
                                    row.task_title = cleanLog.substring(0, 140);
                                    row.task_type = "Code/LogicImplementation";
                                    row.priority = "Medium";
                                    row.status = sess.status === "Completed" || sess.status === "Corrected" ? "Completed" : "In Progress";
                                    row.expected_hours = sess.worked_hours > 0 ? sess.worked_hours : 1.0;
                                    row.actual_hours = sess.status === "Completed" ? (sess.worked_hours || 1.0) : 0.0;
                                    row.description = `Synced from Attendance Session ${sess.name} (Session #${sess.session_number}):\n${cleanLog}`;
                                    addedAny = true;
                                }
                            });
                            if (addedAny) {
                                frm.refresh_field("tasks");
                            }
                        }
                    }
                } else {
                    // Existing record: enforce read-only UI if user does not have edit authorization
                    frm.set_df_property("employee", "read_only", 1);
                    if (!data.can_edit) {
                        frm.disable_save();
                        frm.set_read_only();
                        frm.fields.forEach((f) => {
                            if (f.df && f.df.fieldname) {
                                frm.set_df_property(f.df.fieldname, "read_only", 1);
                            }
                        });
                    }
                }

                // Render Status Badges & Engineering/HR Telemetry Panel
                frm.events.render_telemetry_and_badges(frm, data);
            },
        });
    },

    setup_workflow_buttons(frm) {
        if (frm.is_new()) {
            frm.add_custom_button(__("🔄 Sync Tasks from Attendance"), () => {
                frm.trigger("bootstrap_employee_and_telemetry");
                frappe.show_alert({ message: __("Attendance & tasks synchronized."), indicator: "green" });
            });
            return;
        }

        // Only show edit/submission workflow buttons if user is authorized to edit this POA
        frappe.call({
            method: "xavirgin_os.xavirgin_os.doctype.xavirgin_daily_poa.xavirgin_daily_poa.get_session_poa_Bootstrap",
            args: { employee: frm.doc.employee, poa_date: frm.doc.poa_date },
            callback(r) {
                const data = r.message || {};
                if (!data.can_edit) return;

                // Stage 1: Morning Plan -> Start Work
                if (frm.doc.status === "Morning Plan" || frm.doc.status === "Draft / Morning Plan") {
                    frm.add_custom_button(__("▶️ Start Working on Tasks"), () => {
                        if (!frm.doc.tasks || !frm.doc.tasks.length) {
                            frappe.msgprint({
                                title: __("Tasks Required"),
                                message: __("Please add at least 1 planned task before starting your workday."),
                                indicator: "orange",
                            });
                            return;
                        }
                        frm.set_value("status", "Working");
                        frm.save("Update", () => {
                            frappe.show_alert({ message: __("Work started! Good luck today."), indicator: "green" });
                        });
                    }).addClass("btn-success");
                }

                // Stage 2: Working / Blocked -> Submit Completed Work
                if (
                    frm.doc.status === "Working" ||
                    frm.doc.status === "In Progress" ||
                    frm.doc.status === "Stuck / Blocked" ||
                    frm.doc.status === "Blocked"
                ) {
                    frm.add_custom_button(__("🏁 Finish & Submit Today's Work"), () => {
                        let unfinished = (frm.doc.tasks || []).filter(
                            (t) => t.status === "Planned" || t.status === "In Progress" || t.status === "InProgress" || t.status === "Pending"
                        );
                        if (unfinished.length > 0) {
                            let d = new frappe.ui.Dialog({
                                title: __("You Have {0} Unfinished Tasks", [unfinished.length]),
                                fields: [
                                    {
                                        fieldtype: "HTML",
                                        fieldname: "help",
                                        options: `<p class="text-muted">You have <b>${unfinished.length}</b> tasks that are not marked as completed. Before submitting for today, please choose an action:</p>`,
                                    },
                                    {
                                        fieldname: "action_choice",
                                        label: __("How would you like to handle them?"),
                                        fieldtype: "Select",
                                        options:
                                            "Mark all as Completed (I finished everything)\nProvide Blocker / Incomplete Reason\nMove unfinished to tomorrow automatically",
                                        default: "Mark all as Completed (I finished everything)",
                                        reqd: 1,
                                    },
                                    {
                                        fieldname: "reason",
                                        label: __("Reason / Explanation"),
                                        fieldtype: "Small Text",
                                        depends_on: "eval:doc.action_choice=='Provide Blocker / Incomplete Reason'",
                                    },
                                ],
                                primary_action_label: __("Confirm & Submit"),
                                primary_action: function (values) {
                                    d.hide();
                                    frappe.call({
                                        doc: frm.doc,
                                        method: "submit_eod_report_guided",
                                        args: {
                                            action_choice: values.action_choice,
                                            reason: values.reason || "",
                                        },
                                        freeze: true,
                                        freeze_message: __("Finalizing your day's work and awarding XP..."),
                                        callback() {
                                            frm.reload_doc();
                                            frappe.show_alert({
                                                message: __("Great work! Your daily plan is submitted."),
                                                indicator: "green",
                                            });
                                        },
                                    });
                                },
                            });
                            d.show();
                            return;
                        }

                        frappe.confirm(
                            __("Submit today's completed work report? You will earn XP based on your logged work."),
                            () => {
                                frappe.call({
                                    doc: frm.doc,
                                    method: "submit_eod_report",
                                    freeze: true,
                                    freeze_message: __("Finalizing work submission..."),
                                    callback() {
                                        frm.reload_doc();
                                        frappe.show_alert({
                                            message: __("Work successfully submitted for today!"),
                                            indicator: "green",
                                        });
                                    },
                                });
                            }
                        );
                    }).addClass("btn-primary");
                }

                // Stage 3: Completed -> Reopen button for edits
                if (frm.doc.status === "Completed for Today" || frm.doc.status === "Submitted (EOD Report)") {
                    frm.add_custom_button(__("↩️ Reopen Work Plan"), () => {
                        frm.set_value("status", "Working");
                        frm.save("Update", () => {
                            frappe.show_alert({ message: __("Plan reopened for edits."), indicator: "blue" });
                        });
                    });
                }

                // Attendance & Task Sync Utilities
                frm.add_custom_button(
                    __("🔄 Sync Attendance & Logs"),
                    () => {
                        frappe.call({
                            doc: frm.doc,
                            method: "sync_deliverables_from_attendance",
                            freeze: true,
                            freeze_message: __("Synchronizing attendance sessions & deliverables..."),
                            callback(res) {
                                frm.reload_doc();
                                const msg = res.message || {};
                                frappe.show_alert({
                                    message: __("Synced {0} attendance sessions ({1}h). Added {2} new deliverable(s).", [
                                        msg.sessions_count || 0,
                                        msg.attendance_hours_logged || 0,
                                        msg.added_tasks || 0,
                                    ]),
                                    indicator: "green",
                                });
                            },
                        });
                    },
                    __("Tools")
                );

                frm.add_custom_button(
                    __("📋 Copy Unfinished Tasks from Yesterday"),
                    () => {
                        frappe.call({
                            doc: frm.doc,
                            method: "carry_forward_unfinished_tasks",
                            freeze: true,
                            callback(res) {
                                if (res.message > 0) {
                                    frm.reload_doc();
                                    frappe.show_alert({
                                        message: __("Added {0} unfinished tasks from your previous plan.", [res.message]),
                                        indicator: "blue",
                                    });
                                } else {
                                    frappe.msgprint(__("No unfinished tasks found from previous days."));
                                }
                            },
                        });
                    },
                    __("Tools")
                );

                frm.add_custom_button(
                    __("✨ AI Daily Review"),
                    () => {
                        frappe.call({
                            doc: frm.doc,
                            method: "generate_individual_ai_summary",
                            freeze: true,
                            freeze_message: __("Generating AI feedback on your day's work..."),
                            callback(res) {
                                if (res.message) {
                                    frm.reload_doc();
                                    frappe.show_alert({
                                        message: __("AI feedback ready! Check the section below."),
                                        indicator: "green",
                                    });
                                }
                            },
                        });
                    },
                    __("AI Assistant")
                );
            },
        });

        frm.add_custom_button(__("🎮 Points & XP Guide"), () => {
            frappe.msgprint({
                title: __("🎮 Daily Work Points (XP) Guide"),
                message: `<div style="line-height:1.6;">
                    <p><b>⚡ Finished Task (With Attendance Check-In):</b> +15 XP</p>
                    <p><b>🚀 Deep-Work Bonus (Task >= 2.0 Hours):</b> +10 Bonus XP (25 XP total)</p>
                    <p><b>🛑 Unverified Task (Completed without Check-In):</b> +2 XP</p>
                    <hr/>
                    <p><b>💻 Automatic GitHub Points:</b></p>
                    <ul>
                        <li><b>Commit Push Batch:</b> +5 XP</li>
                        <li><b>Pull Request Opened:</b> +15 XP</li>
                        <li><b>Pull Request Merged:</b> +50 XP</li>
                    </ul>
                </div>`,
                indicator: "purple",
            });
        });
    },

    render_telemetry_and_badges(frm, data) {
        const statusColors = {
            "Completed for Today": { bg: "#dcfce7", text: "#166534", border: "#86efac", icon: "✅" },
            "Working": { bg: "#dbeafe", text: "#1e40af", border: "#93c5fd", icon: "⚡" },
            "Morning Plan": { bg: "#fef9c3", text: "#854d0e", border: "#fde047", icon: "🌅" },
            "Stuck / Blocked": { bg: "#fee2e2", text: "#991b1b", border: "#fca5a5", icon: "🛑" },
        };
        const curStatus = frm.doc.status || "Morning Plan";
        const stStyle = statusColors[curStatus] || statusColors["Morning Plan"];

        const deptName = frm.doc.department || data.department || "Unassigned Squad";
        const attVerified = frm.doc.attendance_verified || (data.attendance && data.attendance.verified);
        const attStyle = attVerified
            ? { bg: "#dcfce7", text: "#15803d", border: "#86efac", icon: "🟢" }
            : { bg: "#fee2e2", text: "#b91c1c", border: "#fca5a5", icon: "⚪" };

        const tel = data.telemetry || {};
        const sessions = (data.attendance && data.attendance.sessions) || [];

        let sessionsHtml = "";
        if (sessions.length > 0) {
            let rows = sessions
                .map(
                    (s) => `
                <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 10px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; margin-bottom:4px; font-size:12px;">
                    <div>
                        <a href="/app/xavirgin-attendance-session/${encodeURIComponent(s.name)}" style="font-weight:700; color:#2563eb; text-decoration:none;">
                            #${s.session_number} (${s.name})
                        </a>
                        <span style="color:#475569; margin-left:8px;">🕒 ${s.check_in} → ${s.check_out}</span>
                    </div>
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="background:${s.status === "Working" ? "#dbeafe" : "#dcfce7"}; color:${s.status === "Working" ? "#1e40af" : "#166534"}; padding:2px 8px; border-radius:999px; font-weight:600; font-size:11px;">
                            ${s.status} (${s.worked_hours}h)
                        </span>
                    </div>
                </div>`
                )
                .join("");

            sessionsHtml = `
                <div style="margin-top:12px;">
                    <div style="font-size:11px; font-weight:700; text-transform:uppercase; color:#64748b; margin-bottom:6px;">
                        ⏱️ Same-Day Attendance Sessions (${sessions.length})
                    </div>
                    ${rows}
                </div>`;
        } else {
            sessionsHtml = `
                <div style="margin-top:10px; padding:8px 12px; background:#fff1f2; border:1px solid #fecdd3; border-radius:6px; font-size:12px; color:#be123c; display:flex; justify-content:space-between; align-items:center;">
                    <span>⚠️ No attendance check-in recorded for ${frm.doc.poa_date || "this date"}.</span>
                    <a href="/app/xavirgin-attendance-session" style="font-weight:700; color:#be123c; text-decoration:underline;">Go to Check-In →</a>
                </div>`;
        }

        // Cross-Module Engineering & HR Telemetry Links
        let shortcutPills = [];
        if (tel.employee) {
            shortcutPills.push(
                `<a href="/app/employee/${encodeURIComponent(tel.employee)}" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px;">👤 Employee (${tel.employee})</a>`
            );
        }
        shortcutPills.push(
            `<a href="/app/xavirgin-attendance-session?employee=${encodeURIComponent(tel.employee || "")}" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px;">⏱️ Attendance (${tel.today_attendance_count || 0} Today / ${tel.total_attendance_count || 0} Total)</a>`
        );
        if (tel.candidate) {
            shortcutPills.push(
                `<a href="/app/xavirgin-candidate/${encodeURIComponent(tel.candidate)}" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px;">🧬 Candidate (${tel.candidate})</a>`
            );
        }
        if (tel.candidate) {
            shortcutPills.push(
                `<a href="/app/xavirgin-interview?candidate=${encodeURIComponent(tel.candidate)}" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px;">🎤 Interviews (${tel.interviews_count || 0})</a>`
            );
        }
        if (tel.offer_letter) {
            shortcutPills.push(
                `<a href="/app/xavirgin-offer-letter/${encodeURIComponent(tel.offer_letter)}" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px;">📄 Offer Letter</a>`
            );
        }
        shortcutPills.push(
            `<a href="/app/xavirgin-github-activity?employee=${encodeURIComponent(tel.employee || "")}" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px;">💻 GitHub (${tel.github_today_count || 0} Today / ${tel.github_total_count || 0} Total)</a>`
        );

        const readOnlyNotice = !data.can_edit && !frm.is_new()
            ? `<div style="margin-bottom:10px; padding:6px 12px; background:#eff6ff; border:1px solid #bfdbfe; border-radius:6px; color:#1e40af; font-size:12px; font-weight:600;">
                👁️ Read-Only View — You are viewing ${frappe.utils.escape_html(frm.doc.employee_name || frm.doc.employee)}'s Daily POA.
               </div>`
            : "";

        const bannerHtml = `
            <div class="xav-poa-telemetry-banner" style="padding:14px 16px; background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; margin-bottom:14px; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
                ${readOnlyNotice}
                <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px; border-bottom:1px solid #f1f5f9; padding-bottom:10px;">
                    <div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px;">
                        <span style="background:${stStyle.bg}; color:${stStyle.text}; border:1px solid ${stStyle.border}; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px;">
                            ${stStyle.icon} ${frappe.utils.escape_html(curStatus)}
                        </span>
                        <span style="background:#f3e8ff; color:#6b21a8; border:1px solid #d8b4fe; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px;">
                            🛡️ ${frappe.utils.escape_html(deptName)}
                        </span>
                        <span style="background:${attStyle.bg}; color:${attStyle.text}; border:1px solid ${attStyle.border}; padding:4px 10px; border-radius:999px; font-weight:600; font-size:12px;">
                            ${attStyle.icon} ${frappe.utils.escape_html(frm.doc.attendance_status || (data.attendance && data.attendance.status) || "Not Checked In")}
                        </span>
                    </div>
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="background:#fef3c7; color:#92400e; border:1px solid #fde68a; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px;">
                            🏆 ${tel.badge_level || "Bronze Tier"} (${tel.xp_points || 0} Total XP)
                        </span>
                        <span style="background:#e0e7ff; color:#3730a3; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px;">
                            ⚡ +${frm.doc.total_poa_xp || 0} POA XP Today
                        </span>
                    </div>
                </div>
                ${sessionsHtml}
                <div style="margin-top:12px; padding-top:10px; border-top:1px solid #f1f5f9;">
                    <div style="font-size:11px; font-weight:700; text-transform:uppercase; color:#64748b; margin-bottom:6px;">
                        🔗 Engineering, HR & Recruitment Telemetry Links
                    </div>
                    <div style="display:flex; flex-wrap:wrap; gap:6px;">
                        ${shortcutPills.join("")}
                    </div>
                </div>
            </div>
        `;

        frm.dashboard.clear_headline();
        frm.dashboard.set_headline_alert(bannerHtml);
    },
});