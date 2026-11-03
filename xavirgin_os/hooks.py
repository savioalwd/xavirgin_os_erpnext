app_name = "xavirgin_os"
app_title = "Xavirgin OS"
app_publisher = "XAVIRGIN (OPC) PRIVATE LIMITED"
app_description = "Enterprise HR, Recruitment, Offer Letter, Daily POA & Financial Intelligence System for Xavirgin"
app_email = "contact@xavirgin.com"
app_license = "mit"
required_apps = ["frappe", "erpnext"]

# App Switcher configuration
app_icon = "octicon octicon-cpu"
app_color = "purple"
default_route = "/desk/xavirgin-os"

after_install = "xavirgin_os.install.after_install"
after_migrate = "xavirgin_os.install.after_migrate"

# Include both JS files, keep only clean self-contained cash_meter.css
app_include_js = [
    "/assets/xavirgin_os/js/cash_meter.js",
    "/assets/xavirgin_os/js/xavirgin_ui.js"
]
app_include_css = [
    "/assets/xavirgin_os/css/cash_meter.css"
]
add_to_apps_screen = [
    {
        "name": "xavirgin_os",
        "title": "Xavirgin OS",
        "logo": "/assets/xavirgin_os/images/xavirgin_logo.jpeg",  # or standard icon below
        "icon": "octicon octicon-cpu",
        "route": "/desk/xavirgin-os",
        "has_permission": "xavirgin_os.api.has_app_permission"
    }
]

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
    "Xavirgin Daily POA": "xavirgin_os.xavirgin_os.doctype.xavirgin_daily_poa.xavirgin_daily_poa.get_permission_query_conditions",
}

has_permission = {
    "Xavirgin Interview": "xavirgin_os.xavirgin_os.doctype.xavirgin_interview.xavirgin_interview.has_permission",
    "Xavirgin Interview Evaluation": "xavirgin_os.xavirgin_os.doctype.xavirgin_interview_evaluation.xavirgin_interview_evaluation.has_permission",
}

scheduler_events = {
    "daily": [
        "xavirgin_os.tasks.auto_close_abandoned_attendance_sessions",
        "xavirgin_os.tasks.expire_overdue_offer_letters",
    ],
    "cron": {
        "30 19 * * *": [
            "xavirgin_os.tasks.scheduled_daily_path_ceo_insight"
        ]
    }
}