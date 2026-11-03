app_name = "xavirgin_os"
app_title = "Xavirgin OS"
app_publisher = "XAVIRGIN (OPC) PRIVATE LIMITED"
app_description = "Enterprise HR, Recruitment, Offer Letter & Gamified Attendance System for Xavirgin"
app_email = "contact@xavirgin.com"
app_license = "mit"
required_apps = ["frappe", "erpnext"]

after_install = "xavirgin_os.install.after_install"
after_migrate = "xavirgin_os.install.after_migrate"

doc_events = {
	"Communication": {
		"after_insert": "xavirgin_os.api.match_inbound_candidate_attachments"
	},
	"File": {
		"before_insert": "xavirgin_os.api.enforce_private_hr_files"
	},
    "User": {
        "after_insert": "xavirgin_os.api.send_custom_welcome_email"
    }
}

permission_query_conditions = {
	"Xavirgin Interview": "xavirgin_os.xavirgin_os.doctype.xavirgin_interview.xavirgin_interview.get_permission_query_conditions",
	"Xavirgin Interview Evaluation": "xavirgin_os.xavirgin_os.doctype.xavirgin_interview_evaluation.xavirgin_interview_evaluation.get_permission_query_conditions",
}

has_permission = {
	"Xavirgin Interview": "xavirgin_os.xavirgin_os.doctype.xavirgin_interview.xavirgin_interview.has_permission",
	"Xavirgin Interview Evaluation": "xavirgin_os.xavirgin_os.doctype.xavirgin_interview_evaluation.xavirgin_interview_evaluation.has_permission",
}

scheduler_events = {
	"daily": [
		"xavirgin_os.tasks.auto_close_abandoned_attendance_sessions",
		"xavirgin_os.tasks.expire_overdue_offer_letters",
	]
}