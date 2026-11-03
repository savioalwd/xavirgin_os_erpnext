frappe.ui.form.on("Xavirgin Job Opening", {
	onload(frm) {
		if (frm.is_new()) {
			// Pull intelligent defaults from Global HR Settings
			frappe.call({
				method: "xavirgin_os.xavirgin_os.doctype.xavirgin_hr_settings.xavirgin_hr_settings.get_global_hr_defaults",
				callback(r) {
					if (r.message) {
						if (!frm.doc.internship_duration_days) {
							frm.set_value("internship_duration_days", r.message.internship_required_active_days);
						}
						if (!frm.doc.hiring_manager && r.message.default_hiring_manager) {
							frm.set_value("hiring_manager", r.message.default_hiring_manager);
						}
						if (!frm.doc.assigned_recruiter) {
							frm.set_value("assigned_recruiter", frappe.session.user);
						}
					}
				}
			});
		}
	},

	designation(frm) {
		if (frm.doc.designation) {
			// Auto-set skill_area to match designation if currently blank
			if (!frm.doc.skill_area) {
				frm.set_value("skill_area", frm.doc.designation);
			}
			// Attempt to find matching Assessment Template
			frappe.db.get_value(
				"Xavirgin Assessment Template",
				{ template_name: frm.doc.designation, is_active: 1 },
				"name",
				(r) => {
					if (r && r.name) {
						frm.set_value("assessment_template", r.name);
					}
				}
			);
		}
	},

	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("✨ AI Generate Description"), () => {
				frappe.confirm(
					__("Use configured Gemini Model to generate/refine this Job Description?"),
					() => {
						frappe.call({
							doc: frm.doc,
							method: "generate_ai_job_description",
							freeze: true,
							freeze_message: __("Consulting Gemini AI..."),
							callback(r) {
								if (r.message) {
									frm.reload_doc();
									frappe.show_alert({
										message: __("Job Description updated with Gemini AI!"),
										indicator: "green"
									});
								}
							}
						});
					}
				);
			}, __("AI Assistant"));

			if (frm.doc.public_application_url) {
				frm.add_custom_button(__("🔗 Copy Public Apply URL"), () => {
					frappe.utils.copy_to_clipboard(frm.doc.public_application_url);
				});
			}
		}
	}
});