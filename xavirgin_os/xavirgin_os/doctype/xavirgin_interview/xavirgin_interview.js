frappe.ui.form.on("Xavirgin Interview", {
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
					assessment_template: frm.doc.assessment_template,
				});
			}, __("Actions"));
		}
	},
});