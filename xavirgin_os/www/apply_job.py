import frappe

no_cache = 1


def get_context(context):
	job_id = frappe.form_dict.get("job")
	filters = {"status": "Open", "is_published": 1}
	if job_id:
		filters["name"] = job_id

	context.jobs = frappe.get_all(
		"Xavirgin Job Opening",
		filters=filters,
		fields=[
			"name",
			"job_title",
			"department",
			"designation",
			"engagement_category",
			"employment_type",
			"internship_duration_days",
			"skill_area",
			"required_skills",
			"job_description",
		],
		order_by="creation desc",
	)
	context.selected_job = context.jobs[0] if (job_id and context.jobs) else None