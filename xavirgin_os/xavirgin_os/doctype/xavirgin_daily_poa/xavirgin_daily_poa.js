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
                        frm.refresh_fields([
                            "employee",
                            "employee_name",
                            "user_id",
                            "department",
                            "designation",
                            "reporting_manager",
                        ]);
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

                    // Auto-populate attendance & GitHub fields on new unsaved form
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
                                    row.task_type = "Code / Logic Implementation";
                                    row.priority = "Medium";
                                    row.status =
                                        sess.status === "Completed" || sess.status === "Corrected" ? "Completed" : "In Progress";
                                    row.expected_hours = sess.worked_hours > 0 ? sess.worked_hours : 1.0;
                                    row.actual_hours = sess.status === "Completed" ? sess.worked_hours || 1.0 : 0.0;
                                    row.description = `Synced from Attendance Session ${sess.name} (Session #${sess.session_number}):\n${cleanLog}`;
                                    addedAny = true;
                                }
                            });
                            if (addedAny) {
                                frm.refresh_field("tasks");
                            }
                        }
                    }

                    if (data.github_activity) {
                        frm.doc.github_events_count = data.github_activity.today_count || 0;
                        frm.refresh_field("github_events_count");
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

                // Render Status Badges, Same-Day GitHub Events & Modern AI Summary Workspace
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
                            (t) =>
                                t.status === "Planned" ||
                                t.status === "In Progress" ||
                                t.status === "InProgress" ||
                                t.status === "Pending"
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
                    __("🔄 Sync Attendance & GitHub Logs"),
                    () => {
                        frappe.call({
                            doc: frm.doc,
                            method: "sync_deliverables_from_attendance",
                            freeze: true,
                            freeze_message: __("Synchronizing attendance sessions, GitHub activity & deliverables..."),
                            callback(res) {
                                frm.reload_doc();
                                const msg = res.message || {};
                                frappe.show_alert({
                                    message: __(
                                        "Synced {0} attendance sessions ({1}h), {2} GitHub event(s), and added {3} new deliverable(s).",
                                        [
                                            msg.sessions_count || 0,
                                            msg.attendance_hours_logged || 0,
                                            msg.github_events_count || 0,
                                            msg.added_tasks || 0,
                                        ]
                                    ),
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
                    __("✨ Generate AI Daily Review"),
                    () => {
                        frm.events.trigger_ai_summary_generation(frm);
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
                    <p><b>💻 Automatic GitHub Points (Optional for Dev/QA):</b></p>
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

    trigger_ai_summary_generation(frm) {
        if (frm._generating_ai_summary) return;
        frm._generating_ai_summary = true;

        const $aiCard = frm.dashboard.wrapper.find(".xav-poa-ai-workspace");
        if ($aiCard.length) {
            $aiCard.find(".xav-ai-status-pill").html(
                `<span style="background:#fef9c3; color:#854d0e; border:1px solid #fde047; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700;">⏳ Generating AI Summary...</span>`
            );
        }

        frappe.call({
            doc: frm.doc,
            method: "generate_individual_ai_summary",
            freeze: true,
            freeze_message: __("Analyzing Daily POA, Attendance & Deliverables with AI..."),
            callback(res) {
                frm._generating_ai_summary = false;
                const payload = res.message || {};

                if (payload.status === "success" || typeof payload === "string") {
                    frappe.show_alert({
                        message: __("AI Daily Summary generated successfully!"),
                        indicator: "green",
                    });
                    frm.reload_doc();
                } else {
                    const userMsg = payload.user_message || __("AI Summary generation could not be completed.");
                    const adminHint = payload.admin_hint || "";
                    const errCat = payload.error_category || "error";

                    if ($aiCard.length) {
                        $aiCard.find(".xav-ai-status-pill").html(
                            `<span style="background:#fee2e2; color:#991b1b; border:1px solid #fca5a5; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700;">⚠️ Generation Failed</span>`
                        );
                        $aiCard.find(".xav-ai-error-box").remove();
                        $aiCard.prepend(`
                            <div class="xav-ai-error-box" style="background:#fef2f2; border:1px solid #fca5a5; border-radius:8px; padding:10px 14px; margin-bottom:10px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                                <div>
                                    <div style="font-weight:800; color:#991b1b; font-size:12px;">⚠️ AI Generation Failed (${frappe.utils.escape_html(errCat.toUpperCase())})</div>
                                    <div style="color:#b91c1c; font-size:12px;">${frappe.utils.escape_html(userMsg)}</div>
                                    ${
                                        adminHint
                                            ? `<div style="color:#64748b; font-size:11px; margin-top:2px;">💡 <b>Admin Guidance:</b> ${frappe.utils.escape_html(adminHint)} <a href="/app/xavirgin-hr-settings" style="color:#2563eb; font-weight:700;">Open AI Settings →</a></div>`
                                            : ""
                                    }
                                </div>
                                <button class="btn btn-xs btn-danger xav-retry-ai-btn" style="font-weight:700;">🔄 Retry Generation</button>
                            </div>
                        `);
                        $aiCard.find(".xav-retry-ai-btn").on("click", () => frm.events.trigger_ai_summary_generation(frm));
                    } else {
                        frappe.msgprint({
                            title: __("AI Summary Generation Notice"),
                            message: `<b>${frappe.utils.escape_html(userMsg)}</b><br><span class="text-muted">${frappe.utils.escape_html(adminHint)}</span>`,
                            indicator: "orange",
                        });
                    }
                }
            },
            error() {
                frm._generating_ai_summary = false;
            },
        });
    },

    render_telemetry_and_badges(frm, data) {
        const statusColors = {
            "Completed for Today": { bg: "#dcfce7", text: "#166534", border: "#86efac", icon: "✅" },
            Working: { bg: "#dbeafe", text: "#1e40af", border: "#93c5fd", icon: "⚡" },
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

        // --- Employee-Wise GitHub Activity Section (Optional / Non-Blocking) ---
        const gh = data.github_activity || {};
        const ghEvents = gh.events || [];
        let githubSectionHtml = "";

        if (ghEvents.length > 0) {
            const ghRows = ghEvents
                .map(
                    (ev) => `
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; padding:6px 10px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; margin-bottom:4px; font-size:12px;">
                    <div style="min-width:0; flex:1;">
                        <span style="background:#e0e7ff; color:#3730a3; padding:1px 7px; border-radius:999px; font-size:10px; font-weight:800; margin-right:6px;">
                            ${frappe.utils.escape_html(ev.event_type)}
                        </span>
                        <strong style="color:#0f172a;">${frappe.utils.escape_html(ev.repository)}</strong>
                        ${ev.branch ? `<span style="color:#64748b; font-size:11px;">(${frappe.utils.escape_html(ev.branch)})</span>` : ""}
                        <span style="color:#334155; margin-left:6px;">— ${frappe.utils.escape_html(ev.summary)}</span>
                    </div>
                    <div style="display:flex; align-items:center; gap:8px;">
                        ${ev.short_sha ? `<code style="font-size:11px; color:#2563eb;">#${frappe.utils.escape_html(ev.short_sha)}</code>` : ""}
                        <span style="font-size:11px; color:#64748b;">🕒 ${ev.event_timestamp}</span>
                        ${ev.xp_awarded ? `<span style="background:#dcfce7; color:#166534; padding:1px 6px; border-radius:999px; font-size:10px; font-weight:700;">+${ev.xp_awarded} XP</span>` : ""}
                        ${ev.event_url ? `<a href="${ev.event_url}" target="_blank" class="btn btn-xs btn-default" style="font-weight:700; font-size:10px;">🔗 GitHub ↗</a>` : ""}
                    </div>
                </div>`
                )
                .join("");

            githubSectionHtml = `
                <div style="margin-top:12px; padding-top:10px; border-top:1px solid #f1f5f9;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                        <span style="font-size:11px; font-weight:700; text-transform:uppercase; color:#64748b;">
                            💻 Same-Day GitHub Webhook Activity (${ghEvents.length} Event${ghEvents.length > 1 ? "s" : ""} • @${frappe.utils.escape_html(gh.github_username || "linked")})
                        </span>
                        <a href="/app/xavirgin-github-activity?employee=${encodeURIComponent(tel.employee || "")}" style="font-size:11px; font-weight:700; color:#2563eb;">Open GitHub Dashboard →</a>
                    </div>
                    ${ghRows}
                </div>`;
        } else if (gh.has_github_account) {
            githubSectionHtml = `
                <div style="margin-top:10px; padding:8px 12px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; font-size:12px; color:#475569; display:flex; justify-content:space-between; align-items:center;">
                    <span>💻 GitHub Account Linked (<b>@${frappe.utils.escape_html(gh.github_username)}</b>) — No commits/PRs received for ${frm.doc.poa_date || "this date"}.</span>
                    <a href="/app/xavirgin-github-activity?employee=${encodeURIComponent(tel.employee || "")}" style="font-weight:700; color:#2563eb;">View All Activity (${gh.total_count || 0}) →</a>
                </div>`;
        } else {
            githubSectionHtml = `
                <div style="margin-top:10px; padding:8px 12px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; font-size:12px; color:#64748b; display:flex; justify-content:space-between; align-items:center;">
                    <span>ℹ️ <b>GitHub Integration Optional:</b> No GitHub username linked for this role. Daily POA & AI Summary evaluate your tasks and attendance directly.</span>
                </div>`;
        }

        // --- Cross-Module Engineering & HR Telemetry Links ---
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

        // --- Modern AI Summary Workspace Card ---
        const hasSummary = Boolean((frm.doc.ai_summary || "").trim());
        const aiCfg = data.ai_config || {};
        const aiStatusPill = hasSummary
            ? `<span style="background:#dcfce7; color:#166534; border:1px solid #86efac; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700;">✅ AI Summary Generated</span>`
            : `<span style="background:#f1f5f9; color:#475569; border:1px solid #cbd5e1; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700;">⚪ Not Generated Yet</span>`;

        const ghSourceBadge =
            ghEvents.length > 0
                ? `<span style="background:#dcfce7; color:#166534; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700;">💻 GitHub Data Available (${ghEvents.length})</span>`
                : `<span style="background:#f1f5f9; color:#64748b; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:600;">ℹ️ GitHub Data Optional / None Today</span>`;

        const aiWorkspaceHtml = !frm.is_new()
            ? `
            <div class="xav-poa-ai-workspace" style="margin-top:12px; padding:12px 14px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;">
                <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px; margin-bottom:10px;">
                    <div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px;">
                        <span style="font-size:13px; font-weight:800; color:#0f172a;">✨ AI Daily Performance Workspace</span>
                        <span class="xav-ai-status-pill">${aiStatusPill}</span>
                        ${ghSourceBadge}
                        <span style="background:#f3e8ff; color:#6b21a8; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700;">
                            Model: ${frappe.utils.escape_html(aiCfg.configured_model || "gemini-2.5-flash")}
                        </span>
                    </div>
                    <div style="display:flex; align-items:center; gap:6px;">
                        ${
                            data.can_edit
                                ? `<button class="btn btn-xs btn-primary xav-gen-ai-summary-btn" style="font-weight:700;">
                                    ${hasSummary ? "🔄 Regenerate AI Summary" : "✨ Generate AI Summary"}
                                   </button>`
                                : ""
                        }
                        ${
                            hasSummary
                                ? `<button class="btn btn-xs btn-default xav-copy-ai-summary-btn" style="font-weight:600;">📋 Copy Summary</button>`
                                : ""
                        }
                    </div>
                </div>
                <div class="xav-ai-summary-body" style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:12px;">
                    ${
                        hasSummary
                            ? frm.doc.ai_summary
                            : `<div style="font-size:12px; color:#64748b; text-align:center; padding:12px;">
                                Click <b>✨ Generate AI Summary</b> to synthesize an objective review from today's tasks (${(frm.doc.tasks || []).length}), attendance (${sessions.length} session(s)), and optional GitHub activity.
                               </div>`
                    }
                </div>
            </div>`
            : "";

        const readOnlyNotice =
            !data.can_edit && !frm.is_new()
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
                ${githubSectionHtml}
                ${aiWorkspaceHtml}
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

        const $wrap = frm.dashboard.wrapper;
        $wrap.find(".xav-gen-ai-summary-btn").on("click", function () {
            frm.events.trigger_ai_summary_generation(frm);
        });
        $wrap.find(".xav-copy-ai-summary-btn").on("click", function () {
            const plainText = $("<div/>").html(frm.doc.ai_summary || "").text().trim();
            if (plainText) {
                frappe.utils.copy_to_clipboard(plainText);
                frappe.show_alert({ message: __("AI Summary copied to clipboard."), indicator: "green" });
            }
        });
    },
});