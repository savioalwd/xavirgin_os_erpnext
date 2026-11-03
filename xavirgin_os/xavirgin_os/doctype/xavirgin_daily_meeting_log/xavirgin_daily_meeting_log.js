frappe.ui.form.on("Xavirgin Daily Meeting Log", {
	setup(frm) {
		frm.add_fetch("department", "department_name", "department");
	},

	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("⚡ Generate Today's 8 PM Sync Sheet"), () => {
				frappe.call({
					doc: frm.doc,
					method: "populate_active_interns",
					freeze: true,
					freeze_message: __("Loading active interns, verifying leaves & fetching work hours..."),
					callback(r) {
						if (r.message) {
							frm.reload_doc();
							frappe.show_alert({
								message: __("Roll call sheet generated for {0} interns.", [r.message]),
								indicator: "green",
							});
						}
					},
				});
			}).addClass("btn-primary");

			if (frm.doc.meeting_url) {
				frm.add_custom_button(__("🔗 Open Google Meet"), () => {
					window.open(frm.doc.meeting_url, "_blank");
				});
			}
		}
	},
});

frappe.ui.form.on("Xavirgin Daily Meeting Entry", {
	status(frm) {
		let present = 0;
		let absent = 0;
		let excused = 0;

		(frm.doc.entries || []).forEach((row) => {
			if (row.status === "Present") present++;
			else if (row.status === "Absent") absent++;
			else if (row.status === "Excused (Approved Meeting Leave)") excused++;
		});

		frm.set_value("present_count", present);
		frm.set_value("absent_count", absent);
		frm.set_value("excused_count", excused);
		frm.set_value("total_participants", (frm.doc.entries || []).length);
	},
});