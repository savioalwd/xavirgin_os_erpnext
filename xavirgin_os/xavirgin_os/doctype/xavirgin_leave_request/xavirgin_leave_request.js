frappe.ui.form.on("Xavirgin Leave Request", {
	setup(frm) {
		frm.add_fetch("employee", "employee_name", "employee_name");
		frm.add_fetch("employee", "department", "department");
		frm.add_fetch("employee", "designation", "designation");
		frm.add_fetch("employee", "custom_team_lead", "team_lead");
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.employee) {
			// Intelligently resolve the logged-in user's employee ID
			frappe.call({
				method: "xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session.get_today_session_status",
				callback(r) {
					if (r.message && r.message.has_employee) {
						frm.set_value("employee", r.message.employee);
					}
				}
			});
		}
	},

	from_date(frm) {
		frm.trigger("calculate_days");
	},

	to_date(frm) {
		frm.trigger("calculate_days");
	},

	is_half_day(frm) {
		frm.trigger("calculate_days");
	},

	calculate_days(frm) {
		if (frm.doc.is_half_day) {
			frm.set_value("leave_days", 0.5);
			return;
		}
		if (frm.doc.from_date && frm.doc.to_date) {
			let start = moment(frm.doc.from_date);
			let end = moment(frm.doc.to_date);
			if (end.isBefore(start)) return;

			let workingDays = 0;
			let curr = start.clone();
			while (curr.isSameOrBefore(end)) {
				if (curr.day() !== 0) { // Exclude Sunday
					workingDays++;
				}
				curr.add(1, "days");
			}
			frm.set_value("leave_days", workingDays);
		}
	},

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
				frappe.prompt(
					[
						{
							fieldname: "rejection_reason",
							label: __("Reason for Rejection"),
							fieldtype: "Small Text",
							reqd: 1,
						}
					],
					(vals) => {
						frappe.call({
							doc: frm.doc,
							method: "decide_leave",
							args: {
								new_status: "Rejected",
								rejection_reason: vals.rejection_reason
							},
							freeze: true,
							callback() {
								frappe.show_alert({ message: __("Leave Rejected"), indicator: "red" });
								frm.reload_doc();
							},
						});
					},
					__("Reject Leave Request"),
					__("Confirm Rejection")
				);
			}).addClass("btn-danger");
		}
	},
});