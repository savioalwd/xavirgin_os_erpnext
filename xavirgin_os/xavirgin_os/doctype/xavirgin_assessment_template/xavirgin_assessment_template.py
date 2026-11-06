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
        """Pulls department from designation if not set."""
        if self.designation and not self.department:
            dept = frappe.db.get_value("Designation", self.designation, "description")
            if dept and frappe.db.exists("Department", dept):
                self.department = dept

    def calculate_and_validate_totals(self):
        """Dynamically calculates total_max_marks from the sum of child criteria."""
        total = 0.0
        for idx, row in enumerate(self.criteria, start=1):
            m = float(row.max_marks or 0)
            if m <= 0:
                frappe.throw(_("Row #{0}: Maximum Marks for '{1}' must be greater than 0.").format(idx, row.criterion_name))
            if float(row.weightage or 0) <= 0:
                row.weightage = 1.0
            total += m

        self.total_max_marks = round(total, 2)
        if not self.target_total_marks or float(self.target_total_marks) <= 0:
            self.target_total_marks = self.total_max_marks
        else:
            # Keep target_total_marks synchronized with configured criteria sum
            self.target_total_marks = self.total_max_marks

    @frappe.whitelist()
    def generate_ai_rubric(self, target_marks: float = None, criteria_count: int = 5):
        """Uses Gemini AI helper to generate a dynamic rubric matching the configured target_total_marks."""
        role_name = self.designation or self.template_name
        dept_name = self.department or "Engineering & Operations"
        desired_total = float(target_marks or self.target_total_marks or 100.0)
        count = max(1, int(criteria_count or 5))
        default_per_criterion = round(desired_total / count, 2)

        prompt = f"""Create a comprehensive interview evaluation rubric for the following role:
Role / Designation: {role_name}
Department: {dept_name}

REQUIREMENTS:
- Provide {count} distinct assessment criteria.
- The sum of `max_marks` across all criteria MUST equal {desired_total} (e.g. ~{default_per_criterion} marks per criterion, or weighted appropriately to sum to {desired_total}).
- Assign one of these categories to each: Technical, Problem Solving, Architecture & Code Quality, Communication & Reasoning, Professionalism & Culture.
- Include actionable 1-sentence scoring guidelines in `description`.

OUTPUT FORMAT (strict JSON array of objects only, no markdown codeblocks):
[{{"criterion_name": "...", "category": "...", "max_marks": {default_per_criterion}, "weightage": 1.0, "description": "..."}}]"""

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
                    "max_marks": float(r.get("max_marks", default_per_criterion)),
                    "weightage": float(r.get("weightage", 1.0)),
                    "description": r.get("description", ""),
                })
            self.calculate_and_validate_totals()
            self.save()
            return {"status": "success", "count": len(self.criteria), "total_max_marks": self.total_max_marks}
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Assessment Template AI Rubric Generation Failed")
            frappe.throw(_("Failed to parse AI rubric: {0}").format(str(e)))