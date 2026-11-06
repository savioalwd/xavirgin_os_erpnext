frappe.ui.form.on("Xavirgin Interview Evaluation", {
    setup(frm) {
        frm.add_fetch("interview", "candidate", "candidate");
        frm.add_fetch("interview", "candidate_name", "candidate_name");
        frm.add_fetch("interview", "job_opening", "job_opening");
        frm.add_fetch("interview", "assessment_template", "assessment_template");
    },

    onload(frm) {
        if (frm.is_new() && frm.doc.assessment_template && (!frm.doc.scores || !frm.doc.scores.length)) {
            frm.trigger("assessment_template");
        }
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
        // Preserve existing scores if already entered on saved evaluation
        if (!frm.is_new() && frm.doc.scores && frm.doc.scores.length > 0) return;

        frappe.call({
            method: "xavirgin_os.xavirgin_os.doctype.xavirgin_interview_evaluation.xavirgin_interview_evaluation.fetch_template_criteria",
            args: { assessment_template: frm.doc.assessment_template },
            callback(r) {
                if (r.message) {
                    const payload = Array.isArray(r.message)
                        ? { criteria: r.message, total_max_marks: r.message.reduce((s, x) => s + flt(x.max_marks), 0) }
                        : r.message;

                    frm.clear_table("scores");
                    (payload.criteria || []).forEach((row) => {
                        let child = frm.add_child("scores");
                        child.criterion_name = row.criterion_name;
                        child.category = row.category;
                        child.max_marks = flt(row.max_marks);
                        child.weightage = flt(row.weightage || 1.0);
                        child.guidelines = row.guidelines;
                        child.score_obtained = 0;
                    });
                    frm.refresh_field("scores");
                    frm.trigger("recalculate_dynamic_scores");
                }
            },
        });
    },

    recalculate_dynamic_scores(frm) {
        let total = 0.0;
        let maxPossible = 0.0;
        (frm.doc.scores || []).forEach((r) => {
            total += flt(r.score_obtained || 0);
            maxPossible += flt(r.max_marks || 0);
        });
        total = flt(total, 2);
        maxPossible = flt(maxPossible, 2);

        frm.set_value("total_score", total);
        frm.set_value("max_possible_score", maxPossible);

        if (maxPossible > 0 && total > 0) {
            let pct = (total / maxPossible) * 100.0;
            if (pct >= 85.0) frm.set_value("recommendation", "Strongly Recommended");
            else if (pct >= 65.0) frm.set_value("recommendation", "Recommended");
            else if (pct >= 50.0) frm.set_value("recommendation", "Hold");
            else frm.set_value("recommendation", "Not Recommended");
        }
    },

    refresh(frm) {
        if (frm.doc.max_possible_score > 0) {
            let pct = flt((flt(frm.doc.total_score) / flt(frm.doc.max_possible_score)) * 100, 1);
            frm.dashboard.clear_headline();
            frm.dashboard.set_headline_alert(
                `<div style="display:flex; justify-content:space-between; align-items:center; padding:8px 14px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px;">
                    <span style="font-weight:700; color:#0f172a;">📊 Dynamic Evaluation Score: <span style="color:#2563eb;">${frm.doc.total_score} / ${frm.doc.max_possible_score}</span> (${pct}%)</span>
                    <span style="font-weight:700; color:#4f46e5;">${frm.doc.recommendation || "Pending Recommendation"}</span>
                </div>`
            );
        }

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
            frappe.msgprint(__("Score ({0}) cannot exceed Maximum Marks ({1}) for '{2}'.", [row.score_obtained, row.max_marks, row.criterion_name]));
            frappe.model.set_value(cdt, cdn, "score_obtained", flt(row.max_marks));
        }
        if (flt(row.score_obtained) < 0) {
            frappe.model.set_value(cdt, cdn, "score_obtained", 0);
        }
        frm.trigger("recalculate_dynamic_scores");
    },
    max_marks(frm) {
        frm.trigger("recalculate_dynamic_scores");
    },
    scores_add(frm) {
        frm.trigger("recalculate_dynamic_scores");
    },
    scores_remove(frm) {
        frm.trigger("recalculate_dynamic_scores");
    },
});