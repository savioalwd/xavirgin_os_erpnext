frappe.ui.form.on("Xavirgin Candidate", {
    setup(frm) {
        frm.add_fetch("job_opening", "department", "department");
        frm.add_fetch("job_opening", "designation", "designation");
        frm.add_fetch("job_opening", "engagement_category", "engagement_category");
        frm.add_fetch("job_opening", "skill_area", "skill_area");
        frm.add_fetch("job_opening", "assigned_recruiter", "assigned_recruiter");
    },

    full_name(frm) {
        if (frm.doc.full_name) {
            let parts = frm.doc.full_name.trim().split(" ");
            let first = parts[0] || "";
            let rest = parts.slice(1).join(" ") || "";
            if (!frm.doc.first_name || frm.doc.first_name !== first) {
                frm.set_value("first_name", first);
            }
            if (!frm.doc.last_name || frm.doc.last_name !== rest) {
                frm.set_value("last_name", rest);
            }
        }
    },

    first_name(frm) {
        if (frm.doc.first_name) {
            let full = `${frm.doc.first_name} ${frm.doc.last_name || ""}`.trim();
            if (frm.doc.full_name !== full) {
                frm.set_value("full_name", full);
            }
        }
    },

    last_name(frm) {
        if (frm.doc.first_name) {
            let full = `${frm.doc.first_name} ${frm.doc.last_name || ""}`.trim();
            if (frm.doc.full_name !== full) {
                frm.set_value("full_name", full);
            }
        }
    },

    github_url(frm) {
        if (frm.doc.github_url) {
            let clean = frm.doc.github_url.trim().replace(/\/+$/, "");
            let handle = clean.split("/").pop();
            frm.set_value("github_username", handle);
        }
    },

    existing_employee(frm) {
        if (frm.doc.existing_employee) {
            frappe.db.get_value(
                "Employee",
                frm.doc.existing_employee,
                [
                    "employee_name",
                    "first_name",
                    "last_name",
                    "company_email",
                    "personal_email",
                    "cell_number",
                    "current_address",
                    "custom_github_username",
                    "department",
                    "designation",
                    "gender",
                    "date_of_birth"
                ],
                (r) => {
                    if (r) {
                        frm.set_value("full_name", r.employee_name);
                        frm.set_value("first_name", r.first_name);
                        frm.set_value("last_name", r.last_name);
                        frm.set_value("email", r.personal_email || r.company_email);
                        frm.set_value("phone", r.cell_number);
                        frm.set_value("address_line", r.current_address);
                        frm.set_value("gender", r.gender || "Prefer not to say");
                        if (r.date_of_birth) frm.set_value("date_of_birth", r.date_of_birth);
                        if (r.department) frm.set_value("department", r.department);
                        if (r.designation) frm.set_value("designation", r.designation);
                        if (r.custom_github_username) {
                            frm.set_value("github_username", r.custom_github_username);
                            frm.set_value("github_url", `https://github.com/${r.custom_github_username}`);
                        }
                    }
                }
            );
        }
    },

    refresh(frm) {
        if (frm.is_new()) return;

        // 1. Direct Convert to Employee Button (Bypasses Offer Letter requirement)
        if (!frm.doc.employee) {
            frm.add_custom_button(__("🚀 Convert to Employee / Intern"), () => {
                frappe.confirm(
                    __("Directly convert candidate <b>{0}</b> into an active ERPNext Employee record with auto-provisioned user access?", [frm.doc.full_name]),
                    () => {
                        frappe.call({
                            doc: frm.doc,
                            method: "convert_to_employee",
                            freeze: true,
                            freeze_message: __("Executing atomic Employee onboarding..."),
                            callback(r) {
                                if (r.message) {
                                    frappe.msgprint({
                                        title: __("Onboarding Complete"),
                                        message: __("Employee <b>{0}</b> created and linked to Candidate {1}.", [r.message, frm.doc.name]),
                                        indicator: "green",
                                    });
                                    frm.reload_doc();
                                }
                            },
                        });
                    }
                ).addClass("btn-primary");
            }).addClass("btn-primary");
        } else {
            frm.add_custom_button(__("👤 View Employee Card"), () => {
                frappe.set_route("Form", "Employee", frm.doc.employee);
            }, __("Lineage"));
        }

        // 2. AI Screening Button
        frm.add_custom_button(__("✨ Run AI Screening"), () => {
            frappe.call({
                doc: frm.doc,
                method: "run_ai_screening",
                freeze: true,
                freeze_message: __("Evaluating candidate profile against job opening..."),
                callback(r) {
                    if (r.message) {
                        frm.reload_doc();
                        frappe.show_alert({
                            message: __("AI Screening complete! Match Score: {0}/10", [r.message.score]),
                            indicator: "green",
                        });
                    }
                },
            });
        }, __("AI Assistant"));

        // 3. Schedule Interview
        frm.add_custom_button(__("📅 Schedule Interview"), () => {
            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_candidate.xavirgin_candidate.get_candidate_lifecycle_context",
                args: { candidate_name: frm.doc.name },
                callback(r) {
                    const ctx = r.message || {};
                    frappe.new_doc("Xavirgin Interview", {
                        candidate: ctx.name,
                        candidate_name: ctx.full_name,
                        candidate_email: ctx.email,
                        job_opening: ctx.job_opening,
                        department: ctx.department,
                    });
                },
            });
        }, __("Recruitment Actions"));

        // 4. Generate Offer Letter & NDA
        if (!frm.doc.employee) {
            frm.add_custom_button(__("📄 Generate Offer Letter & NDA"), () => {
                frappe.call({
                    method: "xavirgin_os.xavirgin_os.doctype.xavirgin_candidate.xavirgin_candidate.get_candidate_lifecycle_context",
                    args: { candidate_name: frm.doc.name },
                    callback(r) {
                        const ctx = r.message || {};
                        frappe.new_doc("Xavirgin Offer Letter", {
                            candidate: ctx.name,
                            candidate_name: ctx.full_name,
                            candidate_email: ctx.email,
                            candidate_phone: ctx.phone,
                            candidate_address: ctx.address_line,
                            job_opening: ctx.job_opening,
                            department: ctx.department,
                            designation: ctx.designation,
                            engagement_category: ctx.engagement_category,
                            skill_area: ctx.skill_area,
                        });
                    },
                });
            }, __("Recruitment Actions"));
        }

        // 5. Decision Recording Modal
        frm.add_custom_button(__("⚖️ Record HR Decision"), () => {
            frappe.prompt(
                [
                    {
                        fieldname: "decision",
                        label: __("Decision"),
                        fieldtype: "Select",
                        options: "Schedule Next Interview\nRequest Technical Assessment\nPut On Hold\nInitiate Offer Letter\nReject Candidate",
                        reqd: 1,
                    },
                    {
                        fieldname: "reason",
                        label: __("Candidate-Safe Reason (Sent in Email if Rejected)"),
                        fieldtype: "Small Text",
                    },
                    {
                        fieldname: "internal_remarks",
                        label: __("Confidential HR Internal Notes"),
                        fieldtype: "Small Text",
                    },
                ],
                (values) => {
                    frappe.call({
                        doc: frm.doc,
                        method: "record_hr_decision",
                        args: values,
                        freeze: true,
                        callback() {
                            frm.reload_doc();
                        },
                    });
                },
                __("Record Candidate Decision"),
                __("Confirm Decision")
            );
        }, __("Recruitment Actions"));
    },
});