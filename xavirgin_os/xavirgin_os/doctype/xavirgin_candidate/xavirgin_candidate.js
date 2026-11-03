frappe.ui.form.on("Xavirgin Candidate", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("📅 Schedule Interview"), () => {
			frappe.new_doc("Xavirgin Interview", {
				candidate: frm.doc.name,
				job_opening: frm.doc.job_opening,
				department: frm.doc.department,
			});
		}, __("Recruitment Actions"));

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
						label: __("Confidential HR Internal Notes (Never Shared Externally)"),
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

		if (!frm.doc.employee) {
			frm.add_custom_button(__("📄 Generate Offer Letter & NDA"), () => {
				frappe.new_doc("Xavirgin Offer Letter", {
					candidate: frm.doc.name,
					job_opening: frm.doc.job_opening,
					department: frm.doc.department,
					designation: frm.doc.designation,
					engagement_category: frm.doc.engagement_category || "Intern",
				});
			}, __("Recruitment Actions"));
		}
	},
});