frappe.ui.form.on("Xavirgin Interview Evaluation", {
	assessment_template(frm) {
		if (!frm.doc.assessment_template) return;
		frappe.call({
			method: "xavirgin_os.xavirgin_os.doctype.xavirgin_interview_evaluation.xavirgin_interview_evaluation.fetch_template_criteria",
			args: { assessment_template: frm.doc.assessment_template },
			callback(r) {
				if (r.message) {
					frm.clear_table("scores");
					r.message.forEach((row) => {
						let child = frm.add_child("scores");
						child.criterion_name = row.criterion_name;
						child.max_marks = row.max_marks;
						child.score_obtained = 0;
					});
					frm.refresh_field("scores");
				}
			},
		});
	},
});

frappe.ui.form.on("Xavirgin Evaluation Score", {
	score_obtained(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.score_obtained > row.max_marks) {
			frappe.msgprint(__("Score cannot exceed Maximum Marks ({0})", [row.max_marks]));
			frappe.model.set_value(cdt, cdn, "score_obtained", row.max_marks);
		}
		let total = 0;
		(frm.doc.scores || []).forEach((r) => {
			total += flt(r.score_obtained);
		});
		frm.set_value("total_score", flt(total, 2));
	},
});