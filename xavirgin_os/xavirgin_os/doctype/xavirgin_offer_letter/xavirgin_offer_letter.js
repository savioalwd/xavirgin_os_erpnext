frappe.ui.form.on("Xavirgin Offer Letter", {
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