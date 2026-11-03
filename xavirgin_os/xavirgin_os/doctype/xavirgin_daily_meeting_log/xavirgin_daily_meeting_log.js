frappe.ui.form.on("Xavirgin Daily Meeting Log", {
	refresh(frm) {
		frm.add_custom_button(__("⚡ Generate Today's 8 PM Sync Sheet"), () => {
			frappe.call({
				doc: frm.doc,
				method: "populate_active_interns",
				freeze: true,
				freeze_message: __("Loading active interns & checking approved meeting leaves..."),
				callback(r) {
					frm.refresh_field("entries");
					frm.refresh_field("present_count");
					frm.refresh_field("absent_count");
					frm.refresh_field("excused_count");
					frappe.show_alert({
						message: __("Populated {0} active interns into roll call.", [r.message || 0]),
						indicator: "green",
					});
				},
			});
		}).addClass("btn-primary");
	},
});