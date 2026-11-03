import re
import frappe
from frappe import _
from frappe.utils import get_url, now_datetime


def normalize_phone(phone: str) -> str:
	if not phone:
		return ""
	digits = re.sub(r"\D", "", str(phone))
	if len(digits) > 10 and digits.startswith("91"):
		digits = digits[2:]
	return digits[-10:] if len(digits) >= 10 else digits

@frappe.whitelist()
def has_app_permission():
    """Allows any logged-in user with System Manager, Employee, or Xavirgin roles to see the app icon."""
    if frappe.session.user in ("Administrator", "Guest"):
        return True
    user_roles = set(frappe.get_roles())
    allowed = {
        "System Manager",
        "Xavirgin HR Admin",
        "Xavirgin HR Manager",
        "Xavirgin Recruiter",
        "Xavirgin Interviewer",
        "Xavirgin Team Lead",
        "Xavirgin Intern",
        "Employee",
    }
    return bool(user_roles.intersection(allowed))

@frappe.whitelist()
def resolve_current_user_employee_context(target_user: str = None) -> dict:
	"""Centralized resolver that delivers active Employee ID & Profile across all modules.

	Order of resolution:
	1. Direct Employee mapping by user_id
	2. Employee company_email or personal_email match
	3. Xavirgin Candidate conversion record match (employee field)
	"""
	user = target_user or frappe.session.user
	if not user or user in ("Administrator", "Guest"):
		# Fallback for local admin or testing
		emp_name = frappe.db.get_value("Employee", {"status": "Active"}, "name")
	else:
		emp_name = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
		if not emp_name:
			user_email = frappe.db.get_value("User", user, "email") or user
			emp_name = frappe.db.get_value(
				"Employee",
				{"company_email": user_email, "status": "Active"},
				"name",
			) or frappe.db.get_value(
				"Employee",
				{"personal_email": user_email, "status": "Active"},
				"name",
			)

		if not emp_name:
			user_email = frappe.db.get_value("User", user, "email") or user
			emp_name = frappe.db.get_value("Xavirgin Candidate", {"email": user_email}, "employee")

	if emp_name and frappe.db.exists("Employee", emp_name):
		emp_data = frappe.db.get_value(
			"Employee",
			emp_name,
			[
				"name",
				"employee_name",
				"department",
				"designation",
				"custom_team_lead",
				"company_email",
				"personal_email",
				"cell_number",
				"custom_employment_category",
				"custom_is_intern",
				"custom_is_team_lead",
			],
			as_dict=True,
		)
		emp_data["has_employee"] = True
		return emp_data

	return {"has_employee": False, "user": user}


def enforce_private_hr_files(doc, method=None):
	"""Forces private storage for sensitive HR attachments across all Xavirgin OS DocTypes."""
	sensitive_doctypes = {
		"Xavirgin Candidate",
		"Xavirgin Candidate Document",
		"Xavirgin Offer Letter",
		"Xavirgin Leave Request",
		"Xavirgin Interview Evaluation",
		"Xavirgin Attendance Session",
	}
	if doc.attached_to_doctype in sensitive_doctypes:
		doc.is_private = 1


def match_inbound_candidate_attachments(doc, method=None):
	"""Matches incoming candidate email attachments to active Sent Offer Letters.

	Matches by sender email OR by offer reference series in subject.
	"""
	if doc.communication_type != "Communication" or doc.sent_or_received != "Received":
		return
	sender_email = (doc.sender or "").strip().lower()
	subject = doc.subject or ""

	offer = None
	# 1. Try finding by sender email
	if sender_email:
		offers = frappe.get_all(
			"Xavirgin Offer Letter",
			filters={"candidate_email": sender_email, "workflow_state": ["in", ["Sent", "Approved"]]},
			fields=["name", "candidate"],
			order_by="creation desc",
			limit=1,
		)
		if offers:
			offer = offers[0]

	# 2. Try regex lookup on Subject line (e.g. XAV-OFFER-2026-00001)
	if not offer and subject:
		match = re.search(r"XAV-OFFER-\d{4}-\d+", subject)
		if match:
			ref_name = match.group(0)
			if frappe.db.exists("Xavirgin Offer Letter", ref_name):
				offer = frappe.get_doc("Xavirgin Offer Letter", ref_name)

	if not offer:
		return

	offer_name = offer.name if hasattr(offer, "name") else offer.get("name")
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Communication", "attached_to_name": doc.name},
		fields=["name", "file_url", "file_name"],
	)
	if not files:
		return

	offer_doc = frappe.get_doc("Xavirgin Offer Letter", offer_name)
	for f in files:
		offer_doc.append("submitted_documents", {
			"document_type": "Signed Offer & NDA",
			"file_url": f.file_url,
			"document_name": f.file_name or "Signed Offer / ID Proof",
			"uploaded_via": "Inbound Email",
			"uploaded_on": now_datetime(),
			"verified_by_hr": 0,
		})
	offer_doc.flags.ignore_permissions = True
	offer_doc.save()


def send_custom_welcome_email(doc, method=None):
	"""Dispatches a branded Xavirgin onboarding email with an activation key on new User creation."""
	if doc.name in ("Administrator", "Guest") or doc.user_type == "Website User":
		return

	reset_key = frappe.generate_hash()
	doc.db_set("reset_password_key", reset_key, update_modified=False)

	setup_url = f"{get_url()}/update-password?key={reset_key}"
	recipient_name = doc.first_name or doc.full_name or "Team Member"

	emp_details = frappe.db.get_value(
		"Employee",
		{"user_id": doc.name},
		["name", "designation", "department"],
		as_dict=True,
	)

	designation_line = ""
	emp_id_block = ""
	if emp_details:
		dept_text = f" in the <strong>{emp_details.department}</strong> department" if emp_details.department else ""
		designation_line = f"<p>Your workspace access has been provisioned for the <strong>{emp_details.designation or 'Team'}</strong> role{dept_text}.</p>"
		emp_id_block = f"<p style='margin: 4px 0 0; font-size: 14px;'><strong>Employee ID:</strong> <code>{emp_details.name}</code></p>"

	message = f"""
	<div style="font-family: Arial, sans-serif; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 8px;">
		<div style="text-align: center; border-bottom: 2px solid #0000FF; padding-bottom: 12px; margin-bottom: 20px;">
			<h2 style="color: #0000FF; margin: 0;">🧬 XAVIRGIN (OPC) PRIVATE LIMITED</h2>
			<p style="margin: 4px 0 0; font-size: 13px; color: #64748b;">Smart Tech Solutions &amp; Software Development</p>
		</div>

		<p>Dear <strong>{recipient_name}</strong>,</p>
		<p>Welcome to Xavirgin! An official internal operations account has been set up for you.</p>
		{designation_line}

		<div style="background: #f8fafc; border-left: 4px solid #0000FF; padding: 14px; margin: 20px 0;">
			<p style="margin: 0; font-size: 14px;"><strong>Portal Login ID:</strong> <code>{doc.email}</code></p>
			{emp_id_block}
		</div>

		<p>Please set your password to activate your access to the attendance tracker, 8:00 PM sync tools, and the Xavirgin OS dashboard:</p>

		<div style="text-align: center; margin: 25px 0;">
			<a href="{setup_url}" style="display: inline-block; background-color: #0000FF; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 14px;">
				Complete Registration &amp; Set Password →
			</a>
		</div>

		<p style="font-size: 12px; color: #64748b; line-height: 1.5;">
			Or copy and paste this verification URL directly into your browser:<br/>
			<a href="{setup_url}" style="color: #0000FF; word-break: break-all;">{setup_url}</a>
		</p>

		<hr style="border: none; border-top: 1px solid #e2e8f0; margin: 25px 0;" />
		<p style="margin: 0; font-size: 11px; color: #94a3b8; text-align: center;">
			© 2026 Xavirgin (OPC) Private Limited | CIN: U62090KL2025OPC098558<br/>
			8/372, Ground Floor, Valiyaparambil, Edathala, Aluva, Ernakulam, Kerala - 683561
		</p>
	</div>
	"""

	frappe.sendmail(
		recipients=[doc.email],
		subject="🧬 Welcome to Xavirgin OS — Complete Your Account Registration",
		message=message,
		delayed=False,
	)


@frappe.whitelist(allow_guest=True)
def apply_for_job(
	job_opening: str,
	full_name: str,
	email: str,
	phone: str,
	location: str = "",
	education: str = "",
	skills: str = "",
	experience_summary: str = "",
	portfolio_url: str = "",
	linkedin_url: str = "",
	github_url: str = "",
	resume_url: str = "",
):
	"""Public portal endpoint for candidates applying directly to a published Job Opening."""
	if not frappe.db.exists("Xavirgin Job Opening", {"name": job_opening, "status": "Open", "is_published": 1}):
		frappe.throw(_("This Job Opening is closed or no longer accepting applications."))

	candidate = frappe.get_doc({
		"doctype": "Xavirgin Candidate",
		"full_name": full_name.strip(),
		"email": email.strip().lower(),
		"phone": phone.strip(),
		"job_opening": job_opening,
		"source": "Public Portal",
		"location": location,
		"education": education,
		"skills": skills,
		"experience_summary": experience_summary,
		"portfolio_url": portfolio_url,
		"linkedin_url": linkedin_url,
		"github_url": github_url,
		"resume": resume_url,
	})
	candidate.insert(ignore_permissions=True)
	frappe.db.commit()
	return {
		"status": "success",
		"candidate_id": candidate.name,
		"message": _("Application submitted successfully. A confirmation email has been sent to {0}.").format(email),
	}