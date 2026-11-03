frappe.ui.form.on("Xavirgin Interview", {
	setup(frm) {
		frm.add_fetch("candidate", "full_name", "candidate_name");
		frm.add_fetch("candidate", "email", "candidate_email");
		frm.add_fetch("candidate", "phone", "candidate_phone");
		frm.add_fetch("candidate", "job_opening", "job_opening");
		frm.add_fetch("candidate", "department", "department");
		frm.add_fetch("candidate", "designation", "designation");
	},

	candidate(frm) {
		if (frm.doc.candidate) {
			frappe.call({
				method: "xavirgin_os.xavirgin_os.doctype.xavirgin_candidate.xavirgin_candidate.get_candidate_lifecycle_context",
				args: { candidate_name: frm.doc.candidate },
				callback(r) {
					const data = r.message || {};
					if (data.job_opening) {
						frm.set_value("job_opening", data.job_opening);
						// Lookup assessment template for this opening
						frappe.db.get_value("Xavirgin Job Opening", data.job_opening, "assessment_template", (res) => {
							if (res && res.assessment_template) {
								frm.set_value("assessment_template", res.assessment_template);
							}
						});
					}
					if (data.department) frm.set_value("department", data.department);
					if (data.designation) frm.set_value("designation", data.designation);
				}
			});
		}
	},

	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("📧 Send Candidate Invitation"), () => {
				frappe.call({
					doc: frm.doc,
					method: "send_candidate_interview_invitation",
					freeze: true,
					freeze_message: __("Sending Technical Interview Invitation..."),
					callback(r) {
						if (r.message) {
							frappe.show_alert({ message: r.message, indicator: "green" });
							frm.reload_doc();
						}
					},
				});
			});

			frm.add_custom_button(__("📝 Submit My Scorecard"), () => {
				frappe.new_doc("Xavirgin Interview Evaluation", {
					interview: frm.doc.name,
					candidate: frm.doc.candidate,
					candidate_name: frm.doc.candidate_name,
					job_opening: frm.doc.job_opening,
					assessment_template: frm.doc.assessment_template,
				});
			}, __("Actions"));
		}
	},
});

frappe.ui.form.on("Xavirgin Interview Participant", {
	employee(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.employee) {
			frappe.db.get_value(
				"Employee",
				row.employee,
				["employee_name", "company_email", "personal_email", "user_id", "designation", "department"],
				(r) => {
					if (r) {
						frappe.model.set_value(cdt, cdn, "full_name", r.employee_name);
						frappe.model.set_value(cdt, cdn, "email", r.company_email || r.personal_email);
						frappe.model.set_value(cdt, cdn, "interviewer_user", r.user_id);
						frappe.model.set_value(cdt, cdn, "designation", r.designation);
						frappe.model.set_value(cdt, cdn, "department", r.department);
					}
				}
			);
		}
	},
});