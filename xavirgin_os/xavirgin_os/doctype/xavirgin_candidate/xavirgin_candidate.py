import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime
from xavirgin_os.api import normalize_phone


class XavirginCandidate(Document):
	def validate(self):
		self.email = (self.email or "").strip().lower()
		self.normalized_phone = normalize_phone(self.phone)
		self.validate_duplicate_application()
		self.sync_from_job_opening()
		self.record_stage_transition()

	def validate_duplicate_application(self):
		"""Improvement #14: Prevent duplicate applications by email or normalized phone for the same Job Opening."""
		if not self.job_opening:
			return
		existing_email = frappe.db.get_value(
			"Xavirgin Candidate",
			{"job_opening": self.job_opening, "email": self.email, "name": ["!=", self.name]},
			"name",
		)
		if existing_email:
			frappe.throw(
				_("Duplicate Application: Email {0} has already applied for Job Opening {1} (Candidate ID: {2}).").format(
					self.email, self.job_opening, existing_email
				)
			)

		if self.normalized_phone:
			existing_phone = frappe.db.get_value(
				"Xavirgin Candidate",
				{
					"job_opening": self.job_opening,
					"normalized_phone": self.normalized_phone,
					"name": ["!=", self.name],
				},
				"name",
			)
			if existing_phone:
				frappe.throw(
					_("Duplicate Application: Phone {0} has already applied for Job Opening {1} (Candidate ID: {2}).").format(
						self.phone, self.job_opening, existing_phone
					)
				)

	def sync_from_job_opening(self):
		if self.job_opening and not self.assigned_recruiter:
			job_doc = frappe.db.get_value(
				"Xavirgin Job Opening",
				self.job_opening,
				["department", "designation", "engagement_category", "assigned_recruiter"],
				as_dict=True,
			)
			if job_doc:
				self.department = job_doc.department
				self.designation = job_doc.designation
				self.engagement_category = job_doc.engagement_category
				if not self.assigned_recruiter and job_doc.assigned_recruiter:
					self.assigned_recruiter = job_doc.assigned_recruiter

	def record_stage_transition(self):
		"""Improvement #15: Immutable stage audit trail."""
		if self.is_new():
			self.append("stage_history", {
				"from_stage": "Created",
				"to_stage": self.pipeline_stage,
				"changed_by": frappe.session.user,
				"changed_on": now_datetime(),
				"remarks": f"Application created via {self.source}",
			})
		else:
			old_doc = self.get_doc_before_save()
			if old_doc and old_doc.pipeline_stage != self.pipeline_stage:
				self.append("stage_history", {
					"from_stage": old_doc.pipeline_stage,
					"to_stage": self.pipeline_stage,
					"changed_by": frappe.session.user,
					"changed_on": now_datetime(),
					"remarks": f"Stage updated from {old_doc.pipeline_stage} to {self.pipeline_stage}",
				})

	def after_insert(self):
		settings = frappe.get_single("Xavirgin HR Settings")
		if settings.send_candidate_stage_emails and self.email:
			job_title = frappe.db.get_value("Xavirgin Job Opening", self.job_opening, "job_title") or self.job_opening
			frappe.sendmail(
				recipients=[self.email],
				subject=f"Application Received: {job_title} — Xavirgin",
				message=f"""
				<div style="font-family: Arial, sans-serif; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
					<h3 style="color: #0000FF; margin-top: 0;">🧬 XAVIRGIN (OPC) PRIVATE LIMITED</h3>
					<p>Dear <strong>{self.full_name}</strong>,</p>
					<p>Thank you for applying for the <strong>{job_title}</strong> position at Xavirgin.</p>
					<p>Your application Reference ID is <strong>{self.name}</strong>. Our recruitment team is reviewing your profile and will reach out with next steps.</p>
					<p style="margin-top: 20px; font-size: 12px; color: #64748b;">Regards,<br><strong>HR Team — Xavirgin.com</strong></p>
				</div>
				""",
				delayed=False,
			)

	@frappe.whitelist()
	def record_hr_decision(self, decision: str, reason: str = "", internal_remarks: str = ""):
		"""Section 7: Record formal HR decision without leaking internal remarks to candidate."""
		self.final_decision = decision
		self.decision_date = now_datetime()
		self.decision_maker = frappe.session.user
		self.decision_reason = reason
		if internal_remarks:
			self.internal_remarks = internal_remarks

		stage_map = {
			"Reject Candidate": "Rejected",
			"Put On Hold": "Final Review",
			"Request Technical Assessment": "Technical Assessment",
			"Initiate Offer Letter": "Offer Preparation",
			"Schedule Next Interview": "Shortlisted",
		}
		if decision in stage_map:
			self.pipeline_stage = stage_map[decision]

		self.save()

		if decision == "Reject Candidate" and self.email:
			job_title = frappe.db.get_value("Xavirgin Job Opening", self.job_opening, "job_title") or self.job_opening
			frappe.sendmail(
				recipients=[self.email],
				subject=f"Update on your application for {job_title} — Xavirgin",
				message=f"""
				<div style="font-family: Arial, sans-serif; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 20px;">
					<p>Dear <strong>{self.full_name}</strong>,</p>
					<p>Thank you for taking the time to apply and interview for the <strong>{job_title}</strong> role at Xavirgin.</p>
					<p>{reason or 'After careful evaluation of your profile against our current technical requirements, we will not be proceeding with your application at this stage.'}</p>
					<p>We wish you the very best in your future endeavors.</p>
					<p>Regards,<br><strong>HR Team — Xavirgin (OPC) Private Limited</strong></p>
				</div>
				""",
				delayed=False,
			)
		return self.pipeline_stage