frappe.ui.form.on("Xavirgin Assessment Template", {
    designation(frm) {
        if (frm.doc.designation && !frm.doc.template_name) {
            frm.set_value("template_name", frm.doc.designation);
        }
    },

    refresh(frm) {
        frm.trigger("recalculate_rubric_totals");

        if (!frm.is_new()) {
            frm.add_custom_button(__("✨ AI Generate Custom Rubric"), () => {
                let d = new frappe.ui.Dialog({
                    title: __("Generate Dynamic Assessment Rubric"),
                    fields: [
                        {
                            fieldname: "target_marks",
                            label: __("Total Assessment Marks (e.g., 10, 50, 100)"),
                            fieldtype: "Float",
                            default: frm.doc.target_total_marks || 100.0,
                            reqd: 1,
                        },
                        {
                            fieldname: "criteria_count",
                            label: __("Number of Criteria"),
                            fieldtype: "Int",
                            default: (frm.doc.criteria && frm.doc.criteria.length) || 5,
                            reqd: 1,
                        },
                    ],
                    primary_action_label: __("Generate Rubric"),
                    primary_action(values) {
                        d.hide();
                        frappe.call({
                            doc: frm.doc,
                            method: "generate_ai_rubric",
                            args: {
                                target_marks: values.target_marks,
                                criteria_count: values.criteria_count,
                            },
                            freeze: true,
                            freeze_message: __("Synthesizing dynamic evaluation rubric..."),
                            callback(r) {
                                if (r.message && r.message.status === "success") {
                                    frm.reload_doc();
                                    frappe.show_alert({
                                        message: __("Rubric generated: {0} criteria ({1} total marks).", [
                                            r.message.count,
                                            r.message.total_max_marks,
                                        ]),
                                        indicator: "green",
                                    });
                                }
                            },
                        });
                    },
                });
                d.show();
            }, __("AI Assistant"));
        }
    },

    recalculate_rubric_totals(frm) {
        let total = 0;
        (frm.doc.criteria || []).forEach((row) => {
            total += flt(row.max_marks || 0);
        });
        total = flt(total, 2);
        if (flt(frm.doc.total_max_marks) !== total) {
            frm.set_value("total_max_marks", total);
        }
        if (total > 0 && flt(frm.doc.target_total_marks) !== total) {
            frm.set_value("target_total_marks", total);
        }
    },
});

frappe.ui.form.on("Xavirgin Assessment Criteria", {
    max_marks(frm) {
        frm.trigger("recalculate_rubric_totals");
    },
    criteria_add(frm) {
        frm.trigger("recalculate_rubric_totals");
    },
    criteria_remove(frm) {
        frm.trigger("recalculate_rubric_totals");
    },
});