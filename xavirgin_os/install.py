import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
	create_xavirgin_roles()
	setup_employee_custom_fields()
	seed_default_hr_settings()
	seed_assessment_templates()
	seed_candidate_kanban_board()
	configure_intern_role_security()
	create_intern_role_profile()
	frappe.db.commit()


def after_migrate():
	create_xavirgin_roles()
	setup_employee_custom_fields()
	seed_default_hr_settings()
	seed_assessment_templates()
	seed_candidate_kanban_board()
	configure_intern_role_security()
	create_intern_role_profile()
	frappe.db.commit()


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


def create_intern_role_profile():
	"""Creates a dedicated Role Profile that strictly bundles Xavirgin Intern and Employee."""
	profile_name = "Xavirgin Intern Profile"
	if not frappe.db.exists("Role Profile", profile_name):
		frappe.get_doc({
			"doctype": "Role Profile",
			"role_profile": profile_name,
			"roles": [
				{"role": "Employee"},
				{"role": "Xavirgin Intern"},
			],
		}).insert(ignore_permissions=True)


def configure_intern_role_security():
	"""Enforces that non-admin roles land exclusively on Xavirgin OS and blocks core workspaces."""
	# 1. Enable desk_access on Role DocType (only valid fields on Role table)
	if frappe.db.exists("Role", "Xavirgin Intern"):
		frappe.db.set_value(
			"Role",
			"Xavirgin Intern",
			"desk_access",
			1,
			update_modified=False,
		)

	# 2. Lock down core ERPNext / Frappe Workspaces from standard roles
	core_workspaces = [
		"Home",
		"HR",
		"Accounting",
		"Buying",
		"Selling",
		"Stock",
		"Build",
		"Integrations",
		"Settings",
		"Tools",
		"Users",
		"Support",
		"Projects",
		"CRM",
		"Payroll",
	]
	for ws_name in core_workspaces:
		if frappe.db.exists("Workspace", ws_name):
			try:
				ws = frappe.get_doc("Workspace", ws_name)
				ws.roles = [r for r in ws.roles if r.role in ("System Manager", "Administrator")]
				ws.flags.ignore_permissions = True
				ws.save()
			except Exception:
				pass

	# 3. Ensure the Xavirgin OS workspace allows access to Xavirgin roles and standard employees
	if frappe.db.exists("Workspace", "Xavirgin OS"):
		try:
			xav_ws = frappe.get_doc("Workspace", "Xavirgin OS")
			existing_roles = {r.role for r in xav_ws.roles}
			target_roles = [
				"System Manager",
				"Xavirgin HR Admin",
				"Xavirgin HR Manager",
				"Xavirgin Recruiter",
				"Xavirgin Interviewer",
				"Xavirgin Team Lead",
				"Xavirgin Intern",
				"Employee",
			]
			for tr in target_roles:
				if tr not in existing_roles:
					xav_ws.append("roles", {"role": tr})
			xav_ws.public = 1
			xav_ws.flags.ignore_permissions = True
			xav_ws.save()
		except Exception:
			pass


def seed_candidate_kanban_board():
	if not frappe.db.exists("DocType", "Xavirgin Candidate"):
		return
	board_name = "Xavirgin Recruitment Pipeline"
	if frappe.db.exists("Kanban Board", board_name):
		return
	stages = [
		"New Application",
		"Initial Screening",
		"Shortlisted",
		"Interview Scheduled",
		"Interview Completed",
		"Technical Assessment",
		"Final Review",
		"Offer Preparation",
		"Offer Sent",
		"Offer Accepted",
		"Offer Rejected",
		"Hired",
		"Rejected",
		"Withdrawn",
	]
	frappe.get_doc({
		"doctype": "Kanban Board",
		"kanban_board_name": board_name,
		"reference_doctype": "Xavirgin Candidate",
		"field_name": "pipeline_stage",
		"private": 0,
		"columns": [{"column_name": s, "status": "Active"} for s in stages],
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
			settings.gemini_model = "gemini-2.5-flash"
			settings.enable_ai_candidate_screening = 1
			settings.enable_ai_job_description_helper = 1
			settings.save(ignore_permissions=True)


def seed_assessment_templates():
	if not frappe.db.exists("DocType", "Xavirgin Assessment Template"):
		return

	templates = {
		"UI/UX Designer": [
			("Design Fundamentals", "Technical", 2.0, "Visual balance, typography, accessibility"),
			("UI/UX Knowledge", "Technical", 2.0, "Wireframing, user journeys, design systems"),
			("Creativity", "Problem Solving", 2.0, "Innovative solutions to UX friction points"),
			("Figma / Design Tools", "Architecture & Code Quality", 2.0, "Auto-layout, component variants, prototypes"),
			("Communication & Reasoning", "Communication & Reasoning", 2.0, "Articulation of design choices and trade-offs"),
		],
		"Flutter Developer": [
			("Dart Fundamentals", "Technical", 2.0, "Async/await, streams, null safety, OOP"),
			("Flutter Architecture", "Architecture & Code Quality", 2.0, "Widget tree structure, clean code organization"),
			("State Management", "Technical", 2.0, "Bloc/Provider/Riverpod lifecycle handling"),
			("Problem Solving", "Problem Solving", 2.0, "Debugging layout exceptions and API sync"),
			("Communication & Reasoning", "Communication & Reasoning", 2.0, "Clarity in explaining technical implementations"),
		],
		"Backend Developer": [
			("Programming Fundamentals", "Technical", 2.0, "Python/PHP/Node core syntax and efficiency"),
			("API Development", "Architecture & Code Quality", 2.0, "RESTful design, authentication, JSON schemas"),
			("Database Knowledge", "Technical", 2.0, "PostgreSQL/MySQL queries, relations, indexing"),
			("Architecture & Problem Solving", "Problem Solving", 2.0, "System resilience, error propagation, rollbacks"),
			("Communication & Reasoning", "Communication & Reasoning", 2.0, "System architecture defense and documentation"),
		],
		"Frontend Developer": [
			("HTML/CSS/Tailwind Fundamentals", "Technical", 2.0, "Responsive layout design, flexbox, grid"),
			("JavaScript / TypeScript & React", "Technical", 2.0, "Hooks, TypeScript typing, component lifecycle"),
			("Component Architecture & State", "Architecture & Code Quality", 2.0, "Reusable UI kits, state normalization"),
			("UI Responsiveness & Debugging", "Problem Solving", 2.0, "Cross-device rendering and performance"),
			("Communication & Reasoning", "Communication & Reasoning", 2.0, "Constructive code review and team reasoning"),
		],
		"Software Tester / QA": [
			("Testing Fundamentals & SDLC", "Technical", 2.0, "Test lifecycle, severity vs priority"),
			("Test Case Design & Bug Reporting", "Architecture & Code Quality", 2.0, "Reproduction steps, expected vs actual"),
			("API & Automation Awareness", "Technical", 2.0, "Postman testing, test assertions"),
			("Analytical & Edge-Case Thinking", "Problem Solving", 2.0, "Finding boundary conditions and race issues"),
			("Communication & Reasoning", "Communication & Reasoning", 2.0, "Clear bug reports and technical coordination"),
		],
		"HR Department": [
			("HR Fundamentals", "Technical", 2.0, "Compliance, labor terms, onboarding pipelines"),
			("Communication", "Communication & Reasoning", 2.0, "Professional tone, candidate dispute resolution"),
			("Problem Solving", "Problem Solving", 2.0, "Handling scheduling bottlenecks and attendance queries"),
			("People Management", "Professionalism & Culture", 2.0, "Empathy, confidentiality, and active listening"),
			("Professionalism", "Professionalism & Culture", 2.0, "Compliance with organizational SOPs and data safety"),
		],
	}

	for template_name, criteria_list in templates.items():
		if not frappe.db.exists("Xavirgin Assessment Template", template_name):
			doc = frappe.get_doc({
				"doctype": "Xavirgin Assessment Template",
				"template_name": template_name,
				"is_active": 1,
				"target_total_marks": 10.0,
				"total_max_marks": 10.0,
				"criteria": [
					{
						"criterion_name": c_name,
						"category": cat,
						"max_marks": m_marks,
						"weightage": 1.0,
						"description": desc,
					}
					for c_name, cat, m_marks, desc in criteria_list
				],
			})
			doc.insert(ignore_permissions=True)