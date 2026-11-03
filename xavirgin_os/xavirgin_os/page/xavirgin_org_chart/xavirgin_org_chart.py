import frappe
from frappe import _


@frappe.whitelist()
def get_team_directory_nodes():
	"""Fetches all active employees with high-res photos, organizational hierarchy, and gamification data."""
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=[
			"name",
			"employee_name",
			"image",
			"department",
			"designation",
			"reports_to",
			"company_email",
			"personal_email",
			"cell_number",
			"custom_employment_category",
			"custom_is_intern",
			"custom_is_team_lead",
			"custom_team_lead",
			"custom_skill_area",
			"custom_github_username",
			"custom_xp_points",
			"custom_badge_level",
			"custom_streak_count",
			"custom_active_days_completed",
			"custom_internship_start_date",
			"custom_internship_end_date",
		],
		order_by="custom_is_team_lead desc, custom_xp_points desc, employee_name asc",
	)

	# Fetch linked manager names for clear hierarchy mapping
	manager_ids = {e.reports_to for e in employees if e.reports_to}
	manager_map = {}
	if manager_ids:
		manager_map = {
			m.name: m.employee_name
			for m in frappe.get_all(
				"Employee",
				filters={"name": ["in", list(manager_ids)]},
				fields=["name", "employee_name"],
			)
		}

	for emp in employees:
		emp["manager_name"] = manager_map.get(emp.reports_to, emp.reports_to or "Executive Director")
		emp["clean_github"] = (
			(emp.custom_github_username or "").replace("https://github.com/", "").strip().lstrip("@")
		)
		emp["display_email"] = emp.company_email or emp.personal_email or ""

	departments = frappe.get_all("Department", pluck="name", order_by="name asc")

	return {
		"employees": employees,
		"departments": departments,
		"total_count": len(employees),
	}