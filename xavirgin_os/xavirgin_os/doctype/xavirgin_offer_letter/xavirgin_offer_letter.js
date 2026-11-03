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

	start_date(frm) {
		if (frm.doc.start_date && frm.doc.active_working_days_required) {
			// Calculate initial preview end-date on the client side
			let start = moment(frm.doc.start_date);
			let targetDays = parseInt(frm.doc.active_working_days_required || 90);
			let counted = 0;
			let curr = start.clone();
			while (counted < targetDays) {
				if (curr.day() !== 0) { // Exclude Sunday
					counted++;
				}
				if (counted < targetDays) {
					curr.add(1, "days");
				}
			}
			frm.set_value("end_date", curr.format("YYYY-MM-DD"));
		}
	},

	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("📧 Email Offer & NDA PDF"), () => {
				frappe.call({
					doc: frm.doc,
					method: "send_offer_letter_email",
					freeze: true,
					freeze_message: __("Generating 2-Page PDF & Sending Email..."),
					callback(r) {
						if (r.message) {
							frappe.show_alert({ message: r.message, indicator: "green" });
							frm.reload_doc();
						}
					},
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