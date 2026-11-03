import frappe


@frappe.whitelist()
def get_org_chart_nodes(department: str = "", search: str = ""):
	"""Return sanitized Employee hierarchy nodes without exposing confidential PII."""
	filters = {"status": "Active"}
	if department:
		filters["department"] = department

	employees = frappe.get_all(
		"Employee",
		filters=filters,
		fields=[
			"name",
			"employee_name",
			"designation",
			"department",
			"reports_to",
			"image",
			"custom_employment_category",
			"custom_is_team_lead",
			"custom_badge_level",
		],
		order_by="custom_is_team_lead desc, employee_name asc",
	)

	if search:
		q = search.strip().lower()
		employees = [
			e for e in employees
			if q in (e.employee_name or "").lower()
			or q in (e.designation or "").lower()
			or q in (e.department or "").lower()
		]
	return employees