import json
import frappe
from frappe import _
from frappe.model.document import Document
from xavirgin_os.ai import call_gemini


class XavirginAssessmentTemplate(Document):
	def before_validate(self):
		self.sync_defaults_from_designation()

	def validate(self):
		self.calculate_and_validate_totals()

	def sync_defaults_from_designation(self):
		"""Intelligently pulls department from designation if not set."""
		if self.designation and not self.department:
			dept = frappe.db.get_value("Designation", self.designation, "description")
			if dept and frappe.db.exists("Department", dept):
				self.department = dept

	def calculate_and_validate_totals(self):
		"""Enforces that total marks equal the sum of child criteria."""
		total = sum(float(row.max_marks or 0) for row in self.criteria)
		self.total_max_marks = round(total, 2)
		if not self.target_total_marks:
			self.target_total_marks = 10.0

		if abs(self.total_max_marks - self.target_total_marks) > 0.01:
			frappe.msgprint(
				_("Warning: Total marks across criteria is {0} (Target benchmark is {1}).").format(
					self.total_max_marks, self.target_total_marks
				),
				indicator="orange",
			)

	@frappe.whitelist()
	def generate_ai_rubric(self):
		"""Uses central Gemini AI helper to generate tailored criteria for this role."""
		role_name = self.designation or self.template_name
		dept_name = self.department or "Engineering & Operations"

		prompt = f"""
		Create a comprehensive interview evaluation rubric for the following role:
		Role / Designation: {role_name}
		Department: {dept_name}

		REQUIREMENTS:
		- Provide exactly 5 distinct assessment criteria.
		- Each criterion must have a max_marks of 2.0 (so the total equals exactly 10.0 marks).
		- Assign one of these categories to each: Technical, Problem Solving, Architecture & Code Quality, Communication & Reasoning, Professionalism & Culture.
		- Include actionable 1-sentence scoring guidelines in description.

		OUTPUT FORMAT (strict JSON array of objects only, no markdown codeblocks):
		[
		  {{"criterion_name": "...", "category": "...", "max_marks": 2.0, "weightage": 1.0, "description": "..."}}
		]
		"""

		system_instruction = "You are a Chief Technology Officer and Technical Interview Architect. Respond ONLY with valid JSON."
		raw_output = call_gemini(prompt=prompt, system_instruction=system_instruction, temperature=0.2)

		clean_json = raw_output.strip()
		if clean_json.startswith("```"):
			clean_json = clean_json.split("\n", 1)[1]
			if clean_json.endswith("```"):
				clean_json = clean_json.rsplit("```", 1)[0]
		clean_json = clean_json.strip()

		try:
			parsed_rows = json.loads(clean_json)
			self.criteria = []
			for r in parsed_rows:
				self.append("criteria", {
					"criterion_name": r.get("criterion_name"),
					"category": r.get("category", "Technical"),
					"max_marks": float(r.get("max_marks", 2.0)),
					"weightage": float(r.get("weightage", 1.0)),
					"description": r.get("description", ""),
				})
			self.calculate_and_validate_totals()
			self.save()
			return {"status": "success", "count": len(self.criteria)}
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Assessment Template AI Rubric Generation Failed")
			frappe.throw(_("Failed to parse AI rubric: {0}").format(str(e)))