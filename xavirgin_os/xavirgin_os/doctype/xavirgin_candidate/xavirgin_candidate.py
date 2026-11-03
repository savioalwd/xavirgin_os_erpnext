import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime, time_diff_in_seconds
from xavirgin_os.ai import call_gemini
from xavirgin_os.api import normalize_phone


class XavirginCandidate(Document):
	def before_validate(self):
		self.resolve_intelligent_data_population()
		self.sync_resume_attachment_to_documents()

	def validate(self):
		self.email = (self.email or "").strip().lower()
		self.normalized_phone = normalize_phone(self.phone)
		self.validate_duplicate_application()
		self.record_stage_transition()

	def resolve_intelligent_data_population(self):
		"""Intelligently retrieves and reuses existing data from Job Opening or linked Employee records."""
		# 1. Sync from linked existing Employee record if set and fields are blank
		if self.existing_employee:
			emp = frappe.db.get_value(
				"Employee",
				self.existing_employee,
				[
					"employee_name",
					"company_email",
					"personal_email",
					"cell_number",
					"current_address",
					"custom_github_username",
					"department",
					"designation",
				],
				as_dict=True,
			)
			if emp:
				if not self.full_name:
					self.full_name = emp.employee_name
				if not self.email:
					self.email = emp.personal_email or emp.company_email
				if not self.phone:
					self.phone = emp.cell_number
				if not self.address_line:
					self.address_line = emp.current_address
				if not self.github_url and emp.custom_github_username:
					self.github_url = f"https://github.com/{emp.custom_github_username}"

		# 2. Sync from Job Opening
		if self.job_opening:
			job = frappe.db.get_value(
				"Xavirgin Job Opening",
				self.job_opening,
				[
					"department",
					"designation",
					"engagement_category",
					"skill_area",
					"assigned_recruiter",
				],
				as_dict=True,
			)
			if job:
				self.department = job.department
				self.designation = job.designation
				self.engagement_category = job.engagement_category
				if not self.skill_area and job.skill_area:
					self.skill_area = job.skill_area
				if not self.assigned_recruiter and job.assigned_recruiter:
					self.assigned_recruiter = job.assigned_recruiter

	def sync_resume_attachment_to_documents(self):
		"""Ensures the primary resume attachment is tracked in the documents table."""
		if not self.resume:
			return

		existing_urls = {d.file_url for d in self.documents if d.file_url}
		if self.resume not in existing_urls:
			self.append("documents", {
				"document_type": "Resume / CV",
				"file_url": self.resume,
				"document_name": f"Resume - {self.full_name}",
				"uploaded_via": "Candidate Profile Upload",
				"uploaded_on": now_datetime(),
				"verified_by_hr": 0,
			})

	def validate_duplicate_application(self):
		"""Prevents duplicate applications by email or normalized phone for the same Job Opening."""
		if not self.job_opening:
			return

		if self.email:
			existing_email = frappe.db.get_value(
				"Xavirgin Candidate",
				{"job_opening": self.job_opening, "email": self.email, "name": ["!=", self.name]},
				"name",
			)
			if existing_email:
				frappe.throw(
					_("Duplicate Application: Email {0} is already registered for Job Opening {1} (Candidate Ref: {2}).").format(
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
					_("Duplicate Application: Phone {0} is already registered for Job Opening {1} (Candidate Ref: {2}).").format(
						self.phone, self.job_opening, existing_phone
					)
				)

	def record_stage_transition(self):
		"""Maintains stage history with calculated duration in the previous stage."""
		if self.is_new():
			self.append("stage_history", {
				"from_stage": "Created",
				"to_stage": self.pipeline_stage,
				"changed_by": frappe.session.user,
				"changed_on": now_datetime(),
				"duration_days": 0.0,
				"remarks": f"Application created via {self.source}",
			})
		else:
			old_doc = self.get_doc_before_save()
			if old_doc and old_doc.pipeline_stage != self.pipeline_stage:
				duration_days = 0.0
				if old_doc.stage_history:
					last_transition = old_doc.stage_history[-1].changed_on
					if last_transition:
						seconds = time_diff_in_seconds(now_datetime(), get_datetime(last_transition))
						duration_days = round(seconds / 86400.0, 2)

				self.append("stage_history", {
					"from_stage": old_doc.pipeline_stage,
					"to_stage": self.pipeline_stage,
					"changed_by": frappe.session.user,
					"changed_on": now_datetime(),
					"duration_days": duration_days,
					"remarks": f"Moved to {self.pipeline_stage}",
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
	def run_ai_screening(self):
		"""Evaluates qualifications, projects, and skills against job requirements using centralized Gemini service."""
		job_reqs = frappe.db.get_value(
			"Xavirgin Job Opening",
			self.job_opening,
			["job_title", "required_skills", "required_qualifications", "experience_requirements", "job_description"],
			as_dict=True,
		) or {}

		prompt = f"""
		Evaluate the following candidate application against the Job Opening requirements.

		JOB DETAILS:
		- Title: {job_reqs.get('job_title') or self.designation}
		- Department: {self.department}
		- Required Skills: {job_reqs.get('required_skills')}
		- Qualifications: {job_reqs.get('required_qualifications')}
		- Experience Expectations: {job_reqs.get('experience_requirements')}

		CANDIDATE DETAILS:
		- Name: {self.full_name}
		- Skills Claimed: {self.skills}
		- Education: {self.education}
		- Experience Summary: {self.experience_summary}
		- GitHub: {self.github_url}
		- Portfolio: {self.portfolio_url}
		- LinkedIn: {self.linkedin_url}

		TASK:
		1. Provide a technical suitability summary (3-4 sentences).
		2. Identify 3 Key Strengths.
		3. Identify any Missing or Weak Skills.
		4. Assign a definitive Match Score from 0.0 to 10.0 (where 10.0 is perfect).

		OUTPUT FORMAT:
		Start your output exactly with: SCORE: <number out of 10.0>
		Followed by the summary and bullets.
		"""

		result = call_gemini(
			prompt=prompt,
			system_instruction="You are an expert technical talent evaluator for Xavirgin (OPC) Private Limited.",
			temperature=0.2,
		)

		score = 0.0
		for line in result.splitlines():
			if "SCORE:" in line:
				try:
					cleaned = line.split("SCORE:")[1].strip().split()[0].replace("/10", "")
					score = float(cleaned)
					break
				except Exception:
					pass

		self.ai_match_score = score
		self.ai_screening_summary = result
		self.db_set("ai_match_score", score, update_modified=False)
		self.db_set("ai_screening_summary", result, update_modified=False)
		return {"score": score, "summary": result}

	@frappe.whitelist()
	def record_hr_decision(self, decision: str, reason: str = "", internal_remarks: str = ""):
		"""Records formal HR decision without leaking internal remarks to candidate."""
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


@frappe.whitelist()
def get_candidate_lifecycle_context(candidate_name: str) -> dict:
	"""Centralized resolver that delivers all candidate fields for downstream modules."""
	cand = frappe.get_doc("Xavirgin Candidate", candidate_name)
	return {
		"candidate": cand.name,
		"candidate_name": cand.full_name,
		"candidate_email": cand.email,
		"candidate_phone": cand.phone,
		"candidate_address": cand.address_line,
		"job_opening": cand.job_opening,
		"department": cand.department,
		"designation": cand.designation,
		"engagement_category": cand.engagement_category or "Intern",
		"skill_area": cand.skill_area or cand.designation,
		"assigned_recruiter": cand.assigned_recruiter,
		"github_url": cand.github_url,
		"linkedin_url": cand.linkedin_url,
		"portfolio_url": cand.portfolio_url,
		"resume": cand.resume,
		"existing_employee": cand.employee or cand.existing_employee,
	}