frappe.ui.form.on("Xavirgin AI Summary Log", {
    refresh(frm) {
        frm.add_custom_button(__("⚡ Today's Path CEO Insight"), () => {
            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_ai_summary_log.xavirgin_ai_summary_log.trigger_organization_path_insight",
                args: { target_date: frm.doc.summary_date || frappe.datetime.get_today() },
                freeze: true,
                freeze_message: __("Analyzing POAs, Attendance, and Ledger..."),
                callback(r) {
                    if (r.message) frappe.set_route("Form", "Xavirgin AI Summary Log", r.message);
                }
            });
        }).addClass("btn-primary");

        frm.add_custom_button(__("📅 Run Historical Analysis"), () => {
            let d = new frappe.ui.Dialog({
                title: __("Historical Operational Analysis"),
                fields: [
                    { label: __("Start Date"), fieldname: "start_date", fieldtype: "Date", reqd: 1, default: frappe.datetime.add_days(frappe.datetime.get_today(), -7) },
                    { label: __("End Date"), fieldname: "end_date", fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
                    { label: __("Prompt Template"), fieldname: "prompt_name", fieldtype: "Link", options: "Xavirgin Prompt" }
                ],
                primary_action_label: __("Generate"),
                primary_action(values) {
                    d.hide();
                    frappe.call({
                        method: "xavirgin_os.ai.generate_historical_period_analysis",
                        args: values,
                        freeze: true,
                        freeze_message: __("Path is compiling multi-day historical telemetry..."),
                        callback(r) {
                            if (r.message && r.message.report_id) {
                                frappe.set_route("Form", "Xavirgin AI Summary Log", r.message.report_id);
                            }
                        }
                    });
                }
            });
            d.show();
        });
    }
});