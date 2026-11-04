frappe.ui.form.on("Xavirgin Job Opening", {
    onload(frm) {
        if (frm.is_new()) {
            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_hr_settings.xavirgin_hr_settings.get_global_hr_defaults",
                callback(r) {
                    if (r && r.message) {
                        const defs = r.message;
                        if (!frm.doc.internship_duration_days && frm.doc.engagement_category === "Intern") {
                            frm.set_value("internship_duration_days", defs.internship_required_active_days || 90);
                        }
                        if (!frm.doc.hiring_manager && defs.default_hiring_manager) {
                            frm.set_value("hiring_manager", defs.default_hiring_manager);
                        }
                        if (!frm.doc.assigned_recruiter) {
                            frm.set_value("assigned_recruiter", frappe.session.user);
                        }
                    }
                }
            });
        }
    },

    designation(frm) {
        if (frm.doc.designation) {
            // Suggest job title if not already written
            if (!frm.doc.job_title) {
                const suffix = frm.doc.engagement_category === "Intern" ? "Intern Cohort" : "Lead";
                frm.set_value("job_title", `${frm.doc.designation} ${suffix}`);
            }

            // Auto-sync learning track / skill area
            if (!frm.doc.skill_area) {
                frm.set_value("skill_area", frm.doc.designation);
            }

            // Intelligent Rubric matcher
            frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Xavirgin Assessment Template",
                    filters: [
                        ["is_active", "=", 1],
                        ["template_name", "like", `%${frm.doc.designation}%`]
                    ],
                    fieldname: "name"
                },
                callback(res) {
                    if (res && res.message && res.message.name && !frm.doc.assessment_template) {
                        frm.set_value("assessment_template", res.message.name);
                    }
                }
            });
        }
    },

    engagement_category(frm) {
        if (frm.doc.engagement_category === "Regular Employee") {
            if (frm.doc.employment_type === "Remote Unpaid Internship") {
                frm.set_value("employment_type", "Full-Time Permanent");
            }
            frm.set_df_property("internship_duration_days", "reqd", 0);
        } else {
            if (!frm.doc.employment_type || frm.doc.employment_type === "Full-Time Permanent") {
                frm.set_value("employment_type", "Remote Unpaid Internship");
            }
            frm.set_df_property("internship_duration_days", "reqd", 1);
        }
    },

    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("✨ AI Generate Description"), () => {
                if (!frm.doc.designation || !frm.doc.department) {
                    frappe.msgprint({
                        title: __("Missing Core Fields"),
                        message: __("Please select both a <b>Designation</b> and <b>Department</b> before consulting AI."),
                        indicator: "orange"
                    });
                    return;
                }

                frappe.confirm(
                    __("Generate a production-ready Job Description using Gemini AI based on <b>{0}</b>?", [frm.doc.job_title]),
                    () => {
                        frappe.call({
                            doc: frm.doc,
                            method: "generate_ai_job_description",
                            freeze: true,
                            freeze_message: __("Gemini AI is drafting technical specifications..."),
                            callback(r) {
                                if (r.message) {
                                    frm.reload_doc();
                                    frappe.show_alert({
                                        message: __("Job Description updated successfully!"),
                                        indicator: "green"
                                    });
                                }
                            }
                        });
                    }
                );
            }, __("AI Assistant"));

            if (frm.doc.public_application_url) {
                frm.add_custom_button(__("🔗 Copy Public URL"), () => {
                    frappe.utils.copy_to_clipboard(frm.doc.public_application_url);
                });

                frm.add_custom_button(__("🌐 View in Careers"), () => {
                    window.open(frm.doc.public_application_url, "_blank");
                });
            }

            // Quick shortcut to linked candidates
            frm.add_custom_button(__("👥 View Candidates"), () => {
                frappe.set_route("List", "Xavirgin Candidate", { job_opening: frm.doc.name });
            }, __("Recruitment"));
        }
    }
});