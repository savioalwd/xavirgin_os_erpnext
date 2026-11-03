import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
	create_xavirgin_roles()
	setup_employee_custom_fields()
	seed_default_hr_settings()
	seed_assessment_templates()
	frappe.db.commit()


def after_migrate():
	create_xavirgin_roles()
	setup_employee_custom_fields()
	seed_default_hr_settings()
	seed_assessment_templates()


def create_xavirgin_roles():
	roles = [
		"Xavirgin HR Admin",
		"Xavirgin HR Manager",
		"Xavirgin Recruiter",
		"Xavirgin Interviewer",
		"Xavirgin Team Lead",
		"Xavirgin Intern",
	]
	for role_name in roles:
		if not frappe.db.exists("Role", role_name):
			frappe.get_doc({
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 1,
			}).insert(ignore_permissions=True)


def setup_employee_custom_fields():
	custom_fields = {
		"Employee": [
			{
				"fieldname": "custom_xavirgin_section",
				"label": "Xavirgin OS — Internship, Gamification & Lineage",
				"fieldtype": "Section Break",
				"insert_after": "status",
				"collapsible": 0,
			},
			{
				"fieldname": "custom_employment_category",
				"label": "Employment Category",
				"fieldtype": "Select",
				"options": "Intern\nRegular Employee",
				"default": "Intern",
				"insert_after": "custom_xavirgin_section",
				"in_standard_filter": 1,
			},
			{
				"fieldname": "custom_is_intern",
				"label": "Is Active Intern",
				"fieldtype": "Check",
				"default": "1",
				"insert_after": "custom_employment_category",
			},
			{
				"fieldname": "custom_is_team_lead",
				"label": "Is Team Lead",
				"fieldtype": "Check",
				"default": "0",
				"description": "Allows approving attendance and leaves for members in the same department",
				"insert_after": "custom_is_intern",
			},
			{
				"fieldname": "custom_team_lead",
				"label": "Assigned Team Lead",
				"fieldtype": "Link",
				"options": "Employee",
				"insert_after": "custom_is_team_lead",
			},
			{
				"fieldname": "custom_github_username",
				"label": "GitHub Username",
				"fieldtype": "Data",
				"insert_after": "custom_team_lead",
			},
			{
				"fieldname": "custom_skill_area",
				"label": "Primary Skill / Track Area",
				"fieldtype": "Data",
				"insert_after": "custom_github_username",
			},
			{
				"fieldname": "custom_col_break_xav1",
				"fieldtype": "Column Break",
				"insert_after": "custom_skill_area",
			},
			{
				"fieldname": "custom_internship_start_date",
				"label": "Internship Start Date",
				"fieldtype": "Date",
				"insert_after": "custom_col_break_xav1",
			},
			{
				"fieldname": "custom_initial_internship_end_date",
				"label": "Initial Internship End Date (Base 90 Working Days)",
				"fieldtype": "Date",
				"read_only": 1,
				"insert_after": "custom_internship_start_date",
			},
			{
				"fieldname": "custom_internship_end_date",
				"label": "Effective Internship End Date (Extended by Leaves)",
				"fieldtype": "Date",
				"read_only": 1,
				"insert_after": "custom_initial_internship_end_date",
			},
			{
				"fieldname": "custom_active_days_completed",
				"label": "Active Working Days Completed (Target: 90)",
				"fieldtype": "Int",
				"default": "0",
				"read_only": 1,
				"insert_after": "custom_internship_end_date",
			},
			{
				"fieldname": "custom_monthly_leave_limit",
				"label": "Monthly General Leave Limit (Days)",
				"fieldtype": "Int",
				"default": "3",
				"insert_after": "custom_active_days_completed",
			},
			{
				"fieldname": "custom_monthly_meeting_leave_limit",
				"label": "Monthly 8 PM Meeting Leave Limit (Days)",
				"fieldtype": "Int",
				"default": "3",
				"insert_after": "custom_monthly_leave_limit",
			},
			{
				"fieldname": "custom_gamification_section",
				"label": "Xavirgin Gamification & Telemetry",
				"fieldtype": "Section Break",
				"insert_after": "custom_monthly_meeting_leave_limit",
			},
			{
				"fieldname": "custom_xp_points",
				"label": "XP Points",
				"fieldtype": "Int",
				"default": "0",
				"read_only": 1,
				"in_list_view": 1,
				"insert_after": "custom_gamification_section",
			},
			{
				"fieldname": "custom_streak_count",
				"label": "Daily Streak (Days)",
				"fieldtype": "Int",
				"default": "0",
				"read_only": 1,
				"insert_after": "custom_xp_points",
			},
			{
				"fieldname": "custom_badge_level",
				"label": "Gamification Rank",
				"fieldtype": "Select",
				"options": "Bronze Tier\nSilver Tier\nGold Tier\nLegend Tier",
				"default": "Bronze Tier",
				"read_only": 1,
				"in_list_view": 1,
				"insert_after": "custom_streak_count",
			},
			{
				"fieldname": "custom_col_break_xav2",
				"fieldtype": "Column Break",
				"insert_after": "custom_badge_level",
			},
			{
				"fieldname": "custom_total_worked_hours",
				"label": "Total Worked Hours",
				"fieldtype": "Float",
				"default": "0",
				"read_only": 1,
				"insert_after": "custom_col_break_xav2",
			},
			{
				"fieldname": "custom_completed_tasks_count",
				"label": "Completed Daily Logs",
				"fieldtype": "Int",
				"default": "0",
				"read_only": 1,
				"insert_after": "custom_total_worked_hours",
			},
			{
				"fieldname": "custom_approved_leaves_days",
				"label": "Total Approved Leave Days",
				"fieldtype": "Int",
				"default": "0",
				"read_only": 1,
				"insert_after": "custom_completed_tasks_count",
			},
			{
				"fieldname": "custom_lineage_section",
				"label": "Recruitment Lineage & Audit References (Immutable)",
				"fieldtype": "Section Break",
				"insert_after": "custom_approved_leaves_days",
			},
			{
				"fieldname": "custom_source_candidate",
				"label": "Source Candidate Record",
				"fieldtype": "Link",
				"options": "Xavirgin Candidate",
				"read_only": 1,
				"insert_after": "custom_lineage_section",
			},
			{
				"fieldname": "custom_source_job_opening",
				"label": "Source Job Opening",
				"fieldtype": "Link",
				"options": "Xavirgin Job Opening",
				"read_only": 1,
				"insert_after": "custom_source_candidate",
			},
			{
				"fieldname": "custom_source_offer_letter",
				"label": "Source Offer Letter",
				"fieldtype": "Link",
				"options": "Xavirgin Offer Letter",
				"read_only": 1,
				"insert_after": "custom_source_job_opening",
			},
			{
				"fieldname": "custom_assigned_recruiter",
				"label": "Hiring Recruiter",
				"fieldtype": "Link",
				"options": "User",
				"read_only": 1,
				"insert_after": "custom_source_offer_letter",
			},
		]
	}
	create_custom_fields(custom_fields, update=True)


def seed_default_hr_settings():
	if frappe.db.exists("DocType", "Xavirgin HR Settings"):
		settings = frappe.get_single("Xavirgin HR Settings")
		if not settings.default_meet_link:
			settings.default_meet_link = "https://meet.google.com/xzx-icxk-uje"
			settings.default_meeting_platform = "Google Meet"
			settings.default_meeting_duration_mins = 40
			settings.daily_team_sync_time = "20:00:00"
			settings.monthly_general_leave_limit = 3
			settings.monthly_meeting_leave_limit = 3
			settings.internship_required_active_days = 90
			settings.min_daily_hours_for_full_day = 4.0
			settings.checkin_xp = 10
			settings.checkout_full_xp = 20
			settings.checkout_partial_xp = 5
			settings.save(ignore_permissions=True)


def seed_assessment_templates():
	if not frappe.db.exists("DocType", "Xavirgin Assessment Template"):
		return

	templates = {
		"UI/UX Designer": [
			("Design Fundamentals", 2),
			("UI/UX Knowledge", 2),
			("Creativity", 2),
			("Figma / Design Tools", 2),
			("Communication and Reasoning", 2),
		],
		"Flutter Developer": [
			("Dart Fundamentals", 2),
			("Flutter Architecture", 2),
			("State Management", 2),
			("Problem Solving", 2),
			("Communication and Reasoning", 2),
		],
		"Backend Developer": [
			("Programming Fundamentals", 2),
			("API Development", 2),
			("Database Knowledge", 2),
			("Architecture and Problem Solving", 2),
			("Communication and Reasoning", 2),
		],
		"Frontend Developer": [
			("HTML/CSS/Tailwind Fundamentals", 2),
			("JavaScript / TypeScript & React", 2),
			("Component Architecture & State", 2),
			("UI Responsiveness & Debugging", 2),
			("Communication and Reasoning", 2),
		],
		"Software Tester / QA": [
			("Testing Fundamentals & SDLC", 2),
			("Test Case Design & Bug Reporting", 2),
			("API & Automation Awareness", 2),
			("Analytical & Edge-Case Thinking", 2),
			("Communication and Reasoning", 2),
		],
		"HR Department": [
			("HR Fundamentals", 2),
			("Communication", 2),
			("Problem Solving", 2),
			("People Management", 2),
			("Professionalism", 2),
		],
		"Market Research & Digital Marketing": [
			("Market Research & Competitor Analysis", 2),
			("Content Strategy & Copywriting", 2),
			("Social Media & Growth Execution", 2),
			("Analytical Thinking & Metrics", 2),
			("Communication and Reasoning", 2),
		],
	}

	for template_name, criteria_list in templates.items():
		if not frappe.db.exists("Xavirgin Assessment Template", template_name):
			doc = frappe.get_doc({
				"doctype": "Xavirgin Assessment Template",
				"template_name": template_name,
				"is_active": 1,
				"total_max_marks": 10.0,
				"criteria": [
					{
						"criterion_name": c_name,
						"max_marks": c_max,
					}
					for c_name, c_max in criteria_list
				],
			})
			doc.insert(ignore_permissions=True)