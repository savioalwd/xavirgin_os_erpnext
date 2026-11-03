frappe.ui.form.on("Xavirgin AI Summary Log", {
	refresh(frm) {
		frm.add_custom_button(__("⚡ Generate New Path CEO Insight"), () => {
			frappe.call({
				method: "xavirgin_os.xavirgin_os.doctype.xavirgin_ai_summary_log.xavirgin_ai_summary_log.trigger_organization_path_insight",
				args: { target_date: frm.doc.summary_date || frappe.datetime.get_today() },
				freeze: true,
				freeze_message: __("Path (Autonomous CEO) is analyzing Attendance, POAs & GitHub commits..."),
				callback(r) {
					if (r.message) {
						frappe.set_route("Form", "Xavirgin AI Summary Log", r.message);
					}
				},
			});
		}).addClass("btn-primary");
	},
});