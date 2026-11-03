frappe.ui.form.on("Xavirgin Leave Request", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.status === "Pending Approval") {
			frm.add_custom_button(__("✅ Approve Leave"), () => {
				frappe.call({
					doc: frm.doc,
					method: "decide_leave",
					args: { new_status: "Approved" },
					freeze: true,
					callback() {
						frappe.show_alert({ message: __("Leave Approved"), indicator: "green" });
						frm.reload_doc();
					},
				});
			}).addClass("btn-primary");

			frm.add_custom_button(__("❌ Reject Leave"), () => {
				frappe.call({
					doc: frm.doc,
					method: "decide_leave",
					args: { new_status: "Rejected" },
					freeze: true,
					callback() {
						frappe.show_alert({ message: __("Leave Rejected"), indicator: "red" });
						frm.reload_doc();
					},
				});
			}).addClass("btn-danger");
		}
	},
});