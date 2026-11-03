import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_url
from xavirgin_os.ai import call_gemini


class XavirginJobOpening(Document):
	def before_validate(self):
		self.resolve_intelligent_defaults()

	def validate(self):
		if self.name and not self.is_new():
			self.public_application_url = f"{get_url()}/apply-job?job={self.name}"

	def after_insert(self):
		self.db_set("public_application_url", f"{get_url()}/apply-job?job={self.name}", update_modified=False)

	def resolve_intelligent_defaults(self):
		"""Intelligently pulls global HR policies and links matching templates."""
		settings = frappe.get_single("Xavirgin HR Settings")

		# 1. Fallback for duration if left empty
		if not self.internship_duration_days and self.engagement_category == "Intern":
			self.internship_duration_days = settings.internship_required_active_days or 90

		# 2. Fallback for Recruiter and Hiring Manager
		if not self.assigned_recruiter:
			self.assigned_recruiter = frappe.session.user

		if not self.hiring_manager and settings.default_hiring_manager:
			self.hiring_manager = settings.default_hiring_manager

		# 3. Auto-populate Skill Area from Designation if not explicitly typed
		if not self.skill_area and self.designation:
			self.skill_area = self.designation

		# 4. Auto-match Assessment Template by Designation name if unselected
		if not self.assessment_template and self.designation:
			matching_template = frappe.db.get_value(
				"Xavirgin Assessment Template",
				{"template_name": self.designation, "is_active": 1},
				"name",
			)
			if not matching_template:
				matching_template = frappe.db.get_value(
					"Xavirgin Assessment Template",
					{"template_name": ["like", f"%{self.designation}%"], "is_active": 1},
					"name",
				)
			if matching_template:
				self.assessment_template = matching_template

	@frappe.whitelist()
	def generate_ai_job_description(self):
		"""Constructs prompt and calls the centralized Gemini service."""
		prompt = f"""
		Generate a structured job description for:
		Title: {self.job_title}
		Designation: {self.designation}
		Department: {self.department}
		Engagement Category: {self.engagement_category} ({self.employment_type})
		Duration: {self.internship_duration_days} active working days

		Provide 3 clear sections:
		1. Role Overview & Learning Scope
		2. Key Technical Responsibilities
		3. Required Qualifications & Skills
		Keep the tone professional, pragmatic, and startup-focused for Xavirgin (OPC) Private Limited.
		"""
		system_instruction = "You are an expert HR recruiter and technical talent manager."

		generated_markdown = call_gemini(
			prompt=prompt,
			system_instruction=system_instruction,
			temperature=0.4
		)

		self.job_description = frappe.utils.md_to_html(generated_markdown)
		self.save()
		return self.job_description