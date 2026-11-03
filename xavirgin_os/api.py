import re
import frappe
from frappe import _
from frappe.utils import now_datetime


def normalize_phone(phone: str) -> str:
	if not phone:
		return ""
	digits = re.sub(r"\D", "", str(phone))
	if len(digits) > 10 and digits.startswith("91"):
		digits = digits[2:]
	return digits[-10:] if len(digits) >= 10 else digits


def enforce_private_hr_files(doc, method=None):
	"""Improvement #16: Force private storage for sensitive HR attachments."""
	sensitive_doctypes = {
		"Xavirgin Candidate",
		"Xavirgin Offer Letter",
		"Xavirgin Leave Request",
		"Xavirgin Interview Evaluation",
	}
	if doc.attached_to_doctype in sensitive_doctypes:
		doc.is_private = 1


def match_inbound_candidate_attachments(doc, method=None):
	"""Improvement #20: Match incoming candidate email attachments to active Sent Offer Letters."""
	if doc.communication_type != "Communication" or doc.sent_or_received != "Received":
		return
	sender_email = (doc.sender or "").strip().lower()
	if not sender_email:
		return

	offers = frappe.get_all(
		"Xavirgin Offer Letter",
		filters={"candidate_email": sender_email, "workflow_state": ["in", ["Sent", "Approved"]]},
		fields=["name", "candidate"],
		order_by="creation desc",
		limit=1,
	)
	if not offers:
		return

	offer_name = offers[0].name
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
			"uploaded_via": "Inbound Email",
			"uploaded_on": now_datetime(),
			"verified_by_hr": 0,
		})
	offer_doc.flags.ignore_permissions = True
	offer_doc.save()


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