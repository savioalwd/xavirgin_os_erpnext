frappe.ui.form.on("Xavirgin Interview Evaluation", {
	setup(frm) {
		frm.add_fetch("interview", "candidate", "candidate");
		frm.add_fetch("interview", "candidate_name", "candidate_name");
		frm.add_fetch("interview", "job_opening", "job_opening");
		frm.add_fetch("interview", "assessment_template", "assessment_template");
	},

	interview(frm) {
		if (frm.doc.interview) {
			frappe.db.get_value(
				"Xavirgin Interview",
				frm.doc.interview,
				["candidate", "candidate_name", "job_opening", "assessment_template"],
				(r) => {
					if (r) {
						frm.set_value("candidate", r.candidate);
						frm.set_value("candidate_name", r.candidate_name);
						frm.set_value("job_opening", r.job_opening);
						frm.set_value("assessment_template", r.assessment_template);
					}
				}
			);
		}
	},

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
						child.category = row.category;
						child.max_marks = row.max_marks;
						child.weightage = row.weightage;
						child.guidelines = row.guidelines;
						child.score_obtained = 0;
					});
					frm.refresh_field("scores");
				}
			},
		});
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0 && (frm.doc.scores || []).length > 0) {
			frm.add_custom_button(__("✨ AI Draft Strengths & Weaknesses"), () => {
				frappe.call({
					doc: frm.doc,
					method: "generate_ai_evaluation_summary",
					freeze: true,
					freeze_message: __("Synthesizing scorecard notes with Gemini..."),
					callback(r) {
						if (r.message) {
							frm.set_value("strengths", r.message.strengths || "");
							frm.set_value("weaknesses", r.message.weaknesses || "");
							if (r.message.verdict && !frm.doc.recommendation) {
								frm.set_value("recommendation", r.message.verdict);
							}
							frappe.show_alert({ message: __("AI feedback populated into scorecard."), indicator: "green" });
						}
					},
				});
			}, __("AI Assistant"));
		}
	},
});

frappe.ui.form.on("Xavirgin Evaluation Score", {
	score_obtained(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (flt(row.score_obtained) > flt(row.max_marks)) {
			frappe.msgprint(__("Score cannot exceed Maximum Marks ({0})", [row.max_marks]));
			frappe.model.set_value(cdt, cdn, "score_obtained", row.max_marks);
		}
		let total = 0;
		(frm.doc.scores || []).forEach((r) => {
			total += flt(r.score_obtained);
		});
		frm.set_value("total_score", flt(total, 2));

		let maxPossible = flt(frm.doc.max_possible_score || 10.0);
		let pct = (total / maxPossible) * 100;
		if (pct >= 85) frm.set_value("recommendation", "Strongly Recommended");
		else if (pct >= 65) frm.set_value("recommendation", "Recommended");
		else if (pct >= 50) frm.set_value("recommendation", "Hold");
		else frm.set_value("recommendation", "Not Recommended");
	},
});