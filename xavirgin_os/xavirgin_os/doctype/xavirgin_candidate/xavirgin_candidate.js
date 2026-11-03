frappe.ui.form.on("Xavirgin Candidate", {
	setup(frm) {
		// Auto-fetch details from Job Opening without manual input
		frm.add_fetch("job_opening", "department", "department");
		frm.add_fetch("job_opening", "designation", "designation");
		frm.add_fetch("job_opening", "engagement_category", "engagement_category");
		frm.add_fetch("job_opening", "skill_area", "skill_area");
		frm.add_fetch("job_opening", "assigned_recruiter", "assigned_recruiter");

		// Auto-fetch details from existing Employee if re-engaging alumni/intern
		frm.add_fetch("existing_employee", "employee_name", "full_name");
		frm.add_fetch("existing_employee", "cell_number", "phone");
		frm.add_fetch("existing_employee", "current_address", "address_line");
		frm.add_fetch("existing_employee", "department", "department");
		frm.add_fetch("existing_employee", "designation", "designation");
	},

	existing_employee(frm) {
		if (frm.doc.existing_employee) {
			frappe.db.get_value(
				"Employee",
				frm.doc.existing_employee,
				["company_email", "personal_email", "custom_github_username"],
				(r) => {
					if (r) {
						if (!frm.doc.email) {
							frm.set_value("email", r.personal_email || r.company_email);
						}
						if (!frm.doc.github_url && r.custom_github_username) {
							frm.set_value("github_url", `https://github.com/${r.custom_github_username}`);
						}
					}
				}
			);
		}
	},

	refresh(frm) {
		if (frm.is_new()) return;

		// 1. AI Screening Button
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

		// 2. Schedule Interview with automatic context passing
		frm.add_custom_button(__("📅 Schedule Interview"), () => {
			frappe.call({
				method: "xavirgin_os.xavirgin_os.doctype.xavirgin_candidate.xavirgin_candidate.get_candidate_lifecycle_context",
				args: { candidate_name: frm.doc.name },
				callback(r) {
					const ctx = r.message || {};
					frappe.new_doc("Xavirgin Interview", {
						candidate: ctx.candidate,
						candidate_name: ctx.candidate_name,
						candidate_email: ctx.candidate_email,
						job_opening: ctx.job_opening,
						department: ctx.department,
					});
				},
			});
		}, __("Recruitment Actions"));

		// 3. Generate Offer Letter with full biographical propagation
		if (!frm.doc.employee) {
			frm.add_custom_button(__("📄 Generate Offer Letter & NDA"), () => {
				frappe.call({
					method: "xavirgin_os.xavirgin_os.doctype.xavirgin_candidate.xavirgin_candidate.get_candidate_lifecycle_context",
					args: { candidate_name: frm.doc.name },
					callback(r) {
						const ctx = r.message || {};
						frappe.new_doc("Xavirgin Offer Letter", {
							candidate: ctx.candidate,
							candidate_name: ctx.candidate_name,
							candidate_email: ctx.candidate_email,
							candidate_phone: ctx.candidate_phone,
							candidate_address: ctx.candidate_address,
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

		// 4. Decision Recording Modal
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