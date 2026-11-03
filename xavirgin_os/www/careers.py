import json
from typing import Optional
import frappe
from frappe import _
from frappe.utils.file_manager import save_file

no_cache = 1


def get_context(context):
	job_id = frappe.form_dict.get("job")
	filters = {"status": "Open", "is_published": 1}
	if job_id:
		filters["name"] = job_id

	jobs = frappe.get_all(
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

	context.jobs = jobs
	context.jobs_json = json.dumps(jobs)
	context.selected_job = jobs[0] if (job_id and jobs) else None
	return context


@frappe.whitelist(allow_guest=True)
def submit_job_application(
	job_opening: str,
	full_name: str,
	email: str,
	phone: str,
	github_profile: Optional[str] = None,
	portfolio_url: Optional[str] = None,
	cover_letter: Optional[str] = None,
):
	"""Public endpoint allowing candidates and interns to apply for published openings."""
	try:
		if not job_opening or not full_name or not email or not phone:
			return {
				"status": "error",
				"message": _("Please fill in all required fields: Job, Full Name, Email, and Phone."),
			}

		clean_name = full_name.strip()
		clean_email = email.strip().lower()
		clean_phone = "".join(filter(str.isdigit, str(phone)))

		# Verify the job opening exists and is accepting applications
		job = frappe.db.get_value(
			"Xavirgin Job Opening",
			job_opening,
			["name", "job_title", "skill_area", "status", "is_published"],
			as_dict=True,
		)
		if not job or job.status != "Open" or not job.is_published:
			return {
				"status": "error",
				"message": _("This position is currently closed or not accepting applications."),
			}

		# Pre-check duplicates before document insertion
		existing = frappe.db.sql(
			"""
			SELECT name FROM `tabXavirgin Candidate`
			WHERE job_opening = %s AND (email = %s OR REPLACE(REPLACE(phone, ' ', ''), '+', '') LIKE %s)
			LIMIT 1
			""",
			(job.name, clean_email, f"%{clean_phone[-10:]}%"),
			as_dict=True,
		)

		if existing:
			return {
				"status": "error",
				"message": _("You have already submitted an application for this position ({0}).").format(existing[0].name),
			}

		# Create candidate record with both full_name and candidate_name mapped
		candidate_payload = {
			"doctype": "Xavirgin Candidate",
			"full_name": clean_name,
			"candidate_name": clean_name,
			"email": clean_email,
			"phone": phone.strip(),
			"job_opening": job.name,
			"skill_area": job.skill_area,
			"github_profile": github_profile.strip() if github_profile else None,
			"portfolio_url": portfolio_url.strip() if portfolio_url else None,
			"cover_letter": cover_letter.strip() if cover_letter else None,
			"application_source": "Career Portal",
			"status": "Applied",
		}

		candidate = frappe.get_doc(candidate_payload)
		candidate.flags.ignore_permissions = True
		candidate.insert(ignore_permissions=True)

		# Attach uploaded resume file
		if hasattr(frappe, "request") and frappe.request.files and "resume_file" in frappe.request.files:
			file = frappe.request.files["resume_file"]
			if getattr(file, "filename", None):
				saved_file = save_file(
					fname=file.filename,
					content=file.read(),
					dt="Xavirgin Candidate",
					dn=candidate.name,
					is_private=1,
				)
				candidate.resume_attachment = saved_file.file_url
				candidate.save(ignore_permissions=True)

		frappe.db.commit()

		return {
			"status": "success",
			"candidate_id": candidate.name,
			"message": _("Application submitted successfully! Your application reference is {0}.").format(candidate.name),
		}

	except Exception as e:
		frappe.db.rollback()
		err_msg = str(e).replace("frappe.exceptions.ValidationError: ", "").strip()
		return {
			"status": "error",
			"message": err_msg or _("An error occurred while saving your application. Please check your details."),
		}