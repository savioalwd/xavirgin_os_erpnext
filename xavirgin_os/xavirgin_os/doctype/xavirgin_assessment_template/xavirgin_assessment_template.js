frappe.ui.form.on("Xavirgin Assessment Template", {
	designation(frm) {
		if (frm.doc.designation && !frm.doc.template_name) {
			frm.set_value("template_name", frm.doc.designation);
		}
	},

	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("✨ AI Generate 5-Criteria Rubric"), () => {
				frappe.confirm(
					__("Generate a standardized 10-mark evaluation rubric using Gemini AI for {0}?", [frm.doc.template_name]),
					() => {
						frappe.call({
							doc: frm.doc,
							method: "generate_ai_rubric",
							freeze: true,
							freeze_message: __("Synthesizing technical rubric..."),
							callback(r) {
								if (r.message && r.message.status === "success") {
									frm.reload_doc();
									frappe.show_alert({
										message: __("Rubric generated successfully (5 criteria, 10 marks total)."),
										indicator: "green",
									});
								}
							},
						});
					}
				);
			}, __("AI Assistant"));
		}
	},
});

frappe.ui.form.on("Xavirgin Assessment Criteria", {
	max_marks(frm) {
		let total = 0;
		(frm.doc.criteria || []).forEach((row) => {
			total += flt(row.max_marks || 0);
		});
		frm.set_value("total_max_marks", flt(total, 2));
	},
});