frappe.ui.form.on("Xavirgin Daily POA", {
    setup(frm) {
        frm.add_fetch("employee", "employee_name", "employee_name");
        frm.add_fetch("employee", "department", "department");
        frm.add_fetch("employee", "designation", "designation");
        frm.add_fetch("employee", "reports_to", "reporting_manager");
    },

    onload(frm) {
        if (frm.is_new() && !frm.doc.employee) {
            frappe.call({
                method: "xavirgin_os.api.resolve_current_user_employee_context",
                callback(r) {
                    if (r.message && r.message.has_employee) {
                        frm.set_value("employee", r.message.name);
                    }
                },
            });
        }
    },

    refresh(frm) {
        if (frm.is_new()) return;

        // Stage 1: Morning Plan -> Start Work
        if (frm.doc.status === "Morning Plan" || frm.doc.status === "Draft / Morning Plan") {
            frm.add_custom_button(__("▶️ Start Working on Tasks"), () => {
                if (!frm.doc.tasks || !frm.doc.tasks.length) {
                    frappe.msgprint({
                        title: __("Tasks Required"),
                        message: __("Please add at least 1 planned task before starting your workday."),
                        indicator: "orange"
                    });
                    return;
                }
                frm.set_value("status", "Working");
                frm.save("Update", () => {
                    frappe.show_alert({ message: __("Work started! Good luck today."), indicator: "green" });
                });
            }).addClass("btn-success");
        }

        // Stage 2: In Progress / Stuck -> Submit Completed Work
        if (frm.doc.status === "Working" || frm.doc.status === "In Progress" || frm.doc.status === "Stuck / Blocked" || frm.doc.status === "Blocked") {
            frm.add_custom_button(__("🏁 Finish & Submit Today's Work"), () => {
                // Client-side validation: Check for planned/pending tasks
                let unfinished = (frm.doc.tasks || []).filter(t => t.status === "Planned" || t.status === "In Progress" || t.status === "Pending");
                
                if (unfinished.length > 0) {
                    let d = new frappe.ui.Dialog({
                        title: __("You Have {0} Unfinished Tasks", [unfinished.length]),
                        fields: [
                            {
                                fieldtype: "HTML",
                                fieldname: "help",
                                options: `
                                    <p class="text-muted">
                                        You have <b>${unfinished.length}</b> tasks that are not marked as completed. 
                                        Before submitting for today, please choose an action:
                                    </p>
                                `
                            },
                            {
                                fieldname: "action_choice",
                                label: __("How would you like to handle them?"),
                                fieldtype: "Select",
                                options: "Mark all as Completed (I finished everything)\nProvide Blocker / Incomplete Reason\nMove unfinished to tomorrow automatically",
                                default: "Mark all as Completed (I finished everything)",
                                reqd: 1
                            },
                            {
                                fieldname: "reason",
                                label: __("Reason / Explanation"),
                                fieldtype: "Small Text",
                                depends_on: "eval:doc.action_choice=='Provide Blocker / Incomplete Reason'"
                            }
                        ],
                        primary_action_label: __("Confirm & Submit"),
                        primary_action: function(values) {
                            d.hide();
                            frappe.call({
                                doc: frm.doc,
                                method: "submit_eod_report_guided",
                                args: {
                                    action_choice: values.action_choice,
                                    reason: values.reason || ""
                                },
                                freeze: true,
                                freeze_message: __("Finalizing your day's work and awarding XP..."),
                                callback(r) {
                                    frm.reload_doc();
                                    frappe.show_alert({ message: __("Great work! Your daily plan is submitted."), indicator: "green" });
                                }
                            });
                        }
                    });
                    d.show();
                    return;
                }

                // If all tasks are already marked Completed or Blocked with reasons
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
                                frappe.show_alert({ message: __("Work successfully submitted for today!"), indicator: "green" });
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

        // Secondary Utilities
        frm.add_custom_button(__("📋 Copy Unfinished Tasks from Yesterday"), () => {
            frappe.call({
                doc: frm.doc,
                method: "carry_forward_unfinished_tasks",
                freeze: true,
                callback(r) {
                    if (r.message > 0) {
                        frm.reload_doc();
                        frappe.show_alert({
                            message: __("Added {0} unfinished tasks from your previous plan.", [r.message]),
                            indicator: "blue",
                        });
                    } else {
                        frappe.msgprint(__("No unfinished tasks found from previous days."));
                    }
                },
            });
        });

        frm.add_custom_button(__("✨ AI Daily Review"), () => {
            frappe.call({
                doc: frm.doc,
                method: "generate_individual_ai_summary",
                freeze: true,
                freeze_message: __("Generating AI feedback on your day's work..."),
                callback(r) {
                    if (r.message) {
                        frm.reload_doc();
                        frappe.show_alert({ message: __("AI feedback ready! Check the section below."), indicator: "green" });
                    }
                },
            });
        }, __("AI Assistant"));

        frm.add_custom_button(__("🎮 Points & XP Guide"), () => {
            frappe.msgprint({
                title: __("🎮 Daily Work Points (XP) Guide"),
                message: `
                    <div style="line-height: 1.6;">
                        <p><b>⚡ Finished Task:</b> +15 XP</p>
                        <p><b>🚀 Long Task (2 or more hours):</b> +10 Bonus XP (25 XP total)</p>
                        <p><b>🛑 Task done without Check-In:</b> +2 XP (Make sure to Check In first to get full points!)</p>
                        <hr/>
                        <p><b>💻 Automatic GitHub Points:</b></p>
                        <ul>
                            <li><b>Saved Code (Commit):</b> +5 XP</li>
                            <li><b>Pull Request Created:</b> +15 XP</li>
                            <li><b>Pull Request Merged:</b> +50 XP</li>
                        </ul>
                    </div>
                `,
                indicator: "purple",
            });
        });
    },
});