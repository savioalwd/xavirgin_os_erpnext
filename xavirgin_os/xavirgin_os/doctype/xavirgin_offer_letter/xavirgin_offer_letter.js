frappe.ui.form.on("Xavirgin Offer Letter", {
    setup(frm) {
        frm.add_fetch("candidate", "full_name", "candidate_name");
        frm.add_fetch("candidate", "email", "candidate_email");
        frm.add_fetch("candidate", "phone", "candidate_phone");
        frm.add_fetch("candidate", "address_line", "candidate_address");
        frm.add_fetch("candidate", "job_opening", "job_opening");
        frm.add_fetch("candidate", "department", "department");
        frm.add_fetch("candidate", "designation", "designation");
        frm.add_fetch("candidate", "skill_area", "skill_area");
        frm.add_fetch("reporting_manager", "employee_name", "reporting_manager_name");
    },

    onload(frm) {
        if (frm.is_new()) {
            if (!frm.doc.issue_date) {
                frm.set_value("issue_date", frappe.datetime.get_today());
            }
            if (!frm.doc.acceptance_deadline && frm.doc.issue_date) {
                frm.trigger("calculate_acceptance_deadline");
            }
            if (!frm.doc.start_date) {
                frm.set_value("start_date", frappe.datetime.get_today());
            }
            if (!frm.doc.end_date && frm.doc.start_date) {
                frm.trigger("calculate_working_end_date");
            }
        }
    },

    issue_date(frm) {
        if (frm.doc.issue_date) {
            frm.trigger("calculate_acceptance_deadline");
        }
    },

    calculate_acceptance_deadline(frm) {
        if (frm.doc.issue_date) {
            let deadline = frappe.datetime.add_days(frm.doc.issue_date, 2);
            frm.set_value("acceptance_deadline", deadline);
        }
    },

    start_date(frm) {
        frm.trigger("calculate_working_end_date");
    },

    active_working_days_required(frm) {
        frm.trigger("calculate_working_end_date");
    },

    calculate_working_end_date(frm) {
        if (frm.doc.start_date && frm.doc.active_working_days_required) {
            let start = moment(frm.doc.start_date);
            let targetDays = parseInt(frm.doc.active_working_days_required || 90);
            let counted = 0;
            let curr = start.clone();
            while (counted < targetDays) {
                if (curr.day() !== 0) { // Exclude Sunday (0 = Sunday)
                    counted++;
                }
                if (counted < targetDays) {
                    curr.add(1, "days");
                }
            }
            frm.set_value("end_date", curr.format("YYYY-MM-DD"));
        }
    },

    candidate(frm) {
        if (frm.doc.candidate) {
            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_candidate.xavirgin_candidate.get_candidate_lifecycle_context",
                args: { candidate_name: frm.doc.candidate },
                callback(r) {
                    const data = r.message || {};
                    if (data.job_opening) frm.set_value("job_opening", data.job_opening);
                    if (data.department) frm.set_value("department", data.department);
                    if (data.designation) frm.set_value("designation", data.designation);
                    if (data.skill_area) frm.set_value("skill_area", data.skill_area);
                    if (data.candidate_address) frm.set_value("candidate_address", data.candidate_address);
                    if (data.engagement_category) frm.set_value("engagement_category", data.engagement_category);
                }
            });
        }
    },

    refresh(frm) {
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__("📧 Email Offer & NDA PDF"), () => {
                frappe.call({
                    doc: frm.doc,
                    method: "send_offer_letter_email",
                    freeze: true,
                    freeze_message: __("Compiling PDF & Dispatching Email..."),
                    callback(r) {
                        if (!r.message) return;

                        if (r.message.status === "error") {
                            frappe.msgprint({
                                title: __("Execution Error"),
                                indicator: "red",
                                message: `<p><b>Error:</b> ${r.message.message}</p>
                                        <details>
                                            <summary style="cursor:pointer; color:#0066cc;">View Full Traceback</summary>
                                            <pre style="max-height: 300px; overflow: auto; background: #1e1e1e; color: #fff; padding: 10px; border-radius: 4px; font-size: 11px;">${r.message.traceback || "No traceback captured."}</pre>
                                        </details>`
                            });
                        } else {
                            frappe.show_alert({ message: r.message.message, indicator: "green" });
                            frm.reload_doc();
                        }
                    },
                    error(r) {
                        let errorText = r._server_messages 
                            ? JSON.parse(r._server_messages).join("\n") 
                            : (r.responseText || "Internal Server Error");
                        frappe.msgprint({
                            title: __("Server 500 Intercepted"),
                            indicator: "red",
                            message: `<pre style="max-height: 300px; overflow: auto;">${frappe.utils.escape_html(errorText)}</pre>`
                        });
                    }
                });
            });

            if (frm.doc.workflow_state !== "Accepted" && !frm.doc.employee) {
                frm.add_custom_button(__("✅ Mark Offer Accepted"), () => {
                    frm.set_value("workflow_state", "Accepted");
                    frm.save("Update");
                }, __("Status"));
            }

            if (frm.doc.workflow_state === "Accepted" && frm.doc.documents_verified && !frm.doc.employee) {
                frm.add_custom_button(__("🚀 Convert to Employee / Intern"), () => {
                    frappe.confirm(
                        __("Convert {0} into an active ERPNext Employee record with full lineage?", [frm.doc.candidate_name]),
                        () => {
                            frappe.call({
                                doc: frm.doc,
                                method: "convert_to_employee",
                                freeze: true,
                                freeze_message: __("Executing atomic Employee creation..."),
                                callback(r) {
                                    if (r.message) {
                                        frappe.msgprint({
                                            title: __("Onboarding Complete"),
                                            message: __("Employee <b>{0}</b> created and linked to Candidate {1}.", [r.message, frm.doc.candidate]),
                                            indicator: "green",
                                        });
                                        frm.reload_doc();
                                    }
                                },
                            });
                        }
                    );
                }).addClass("btn-primary");
            }
        }
    },
});