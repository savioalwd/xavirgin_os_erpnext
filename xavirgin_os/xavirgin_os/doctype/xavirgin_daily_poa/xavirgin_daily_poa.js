frappe.ui.form.on("Xavirgin Daily POA", {
	setup(frm) {
		frm.add_fetch("employee", "employee_name", "employee_name");
		frm.add_fetch("employee", "department", "department");
		frm.add_fetch("employee", "designation", "designation");
		frm.add_fetch("employee", "reports_to", "reporting_manager");
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.employee) {
			frappe.call({
				method: "xavirgin_os.api.resolve_current_user_employee_context",
				callback(r) {
					if (r.message && r.message.has_employee) {
						frm.set_value("employee", r.message.name);
					}
				},
			});
		}
	},

	refresh(frm) {
		if (!frm.is_new()) {
			if (frm.doc.status !== "Submitted (EOD Report)") {
				frm.add_custom_button(__("🚀 Submit EOD POA Report"), () => {
					frappe.confirm(
						__("Submit your final Daily Plan of Action report for {0}?", [frm.doc.poa_date]),
						() => {
							frappe.call({
								doc: frm.doc,
								method: "submit_eod_report",
								freeze: true,
								freeze_message: __("Submitting Daily POA & Verifying Telemetry..."),
								callback() {
									frm.reload_doc();
									frappe.show_alert({ message: __("Daily POA Submitted!"), indicator: "green" });
								},
							});
						}
					);
				}).addClass("btn-primary");
			}

			frm.add_custom_button(__("🔄 Carry Forward Unfinished Tasks"), () => {
				frappe.call({
					doc: frm.doc,
					method: "carry_forward_unfinished_tasks",
					freeze: true,
					callback(r) {
						if (r.message > 0) {
							frm.reload_doc();
							frappe.show_alert({
								message: __("Carried forward {0} unfinished tasks.", [r.message]),
								indicator: "blue",
							});
						}
					},
				});
			});

			frm.add_custom_button(__("✨ AI Analyze My POA"), () => {
				frappe.call({
					doc: frm.doc,
					method: "generate_individual_ai_summary",
					freeze: true,
					freeze_message: __("Analyzing Planned vs Actual Execution with Gemini..."),
					callback(r) {
						if (r.message) {
							frm.reload_doc();
							frappe.show_alert({ message: __("AI Summary Generated!"), indicator: "green" });
						}
					},
				});
			}, __("AI Assistant"));
		}

		frm.add_custom_button(__("🎮 POA XP Guide"), () => {
			frappe.msgprint({
				title: __("🎮 Daily POA & Engineering Gamification Rules"),
				message: `
					<div style="line-height: 1.6;">
						<p><b>⚡ Completed Task (With Active Attendance):</b> +15 Base XP</p>
						<p><b>🚀 Deep Work Task (>= 2.0 Hours):</b> +10 Bonus XP (25 XP total)</p>
						<p><b>🛑 Unverified Shift Task:</b> +2 XP (Always Check In before completing tasks!)</p>
						<hr/>
						<p><b>💻 GitHub Webhook Auto-Rewards:</b></p>
						<ul>
							<li><b>Push / Commit Batch:</b> +5 XP</li>
							<li><b>Pull Request Opened:</b> +15 XP</li>
							<li><b>Pull Request Merged:</b> +50 XP</li>
							<li><b>Actionable Bug Issue / PR Code Review:</b> +10 XP</li>
						</ul>
					</div>
				`,
				indicator: "purple",
			});
		});
	},
});