import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_url, getdate, today
from xavirgin_os.ai import call_gemini


class XavirginJobOpening(Document):
    def validate(self):
        self.validate_vacancies_and_salary()
        self.resolve_intelligent_defaults()
        self.set_application_url()

    def on_trash(self):
        linked_candidates = frappe.db.count("Xavirgin Candidate", {"job_opening": self.name})
        if linked_candidates > 0:
            frappe.throw(
                _("Cannot delete Job Opening {0} because it is referenced by {1} candidate applications. Consider setting status to 'Closed' instead.").format(
                    self.name, linked_candidates
                )
            )

    def validate_vacancies_and_salary(self):
        if int(self.number_of_vacancies or 0) <= 0:
            frappe.throw(_("Number of Vacancies must be at least 1."))

        if self.min_salary_or_stipend and self.max_salary_or_stipend:
            if float(self.min_salary_or_stipend) > float(self.max_salary_or_stipend):
                frappe.throw(_("Minimum Salary/Stipend cannot exceed Maximum Salary/Stipend."))

        if self.application_deadline and getdate(self.application_deadline) < getdate(today()):
            if self.status == "Open":
                frappe.msgprint(
                    _("Warning: Application deadline {0} is in the past for an active opening.").format(self.application_deadline),
                    indicator="orange"
                )

    def set_application_url(self):
        base = get_url().rstrip("/")
        doc_id = self.name or "new"
        self.public_application_url = f"{base}/careers?job={doc_id}"

    def after_insert(self):
        self.set_application_url()
        self.db_set("public_application_url", self.public_application_url, update_modified=False)

    def resolve_intelligent_defaults(self):
        settings = frappe.get_single("Xavirgin HR Settings")

        if not self.internship_duration_days and self.engagement_category == "Intern":
            self.internship_duration_days = settings.internship_required_active_days or 90

        if not self.assigned_recruiter:
            self.assigned_recruiter = frappe.session.user

        if not self.hiring_manager and settings.default_hiring_manager:
            self.hiring_manager = settings.default_hiring_manager

        if not self.skill_area and self.designation:
            self.skill_area = self.designation

        if not self.assessment_template and self.designation:
            matching = frappe.db.get_value(
                "Xavirgin Assessment Template",
                {"is_active": 1, "template_name": ["like", f"%{self.designation}%"]},
                "name"
            )
            if matching:
                self.assessment_template = matching

    @frappe.whitelist()
    def generate_ai_job_description(self):
        """Constructs prompt and calls the Gemini service via HR Settings credentials."""
        self.check_permission("write")

        settings = frappe.get_single("Xavirgin HR Settings")
        creds = settings.get_gemini_credentials()

        if not creds.get("api_key"):
            frappe.throw(_("Please configure a valid Gemini API Key in Xavirgin HR Settings."))

        prompt = f"""
        Generate an executive, production-grade technical Job Description for XAVIRGIN (OPC) PRIVATE LIMITED.
        Operating under the Zero Energy Protocol (Hands-on execution, zero waste, high-impact systems).

        Role Details:
        - Job Title: {self.job_title}
        - Designation: {self.designation}
        - Department: {self.department}
        - Engagement: {self.engagement_category} ({self.employment_type})
        - Active Working Duration: {self.internship_duration_days or 90} working days (excluding Sundays)
        - Focus Skills: {self.skill_area or self.designation}

        Please structure the response in clean HTML:
        <h3>1. Role Overview & System Objectives</h3>
        <h3>2. Key Engineering Responsibilities</h3>
        <h3>3. Prerequisites, Stack & Technical Qualifications</h3>
        <h3>4. Zero Energy Governance & Milestone Requirements</h3>
        """
        system_instruction = "You are the CTO and Chief Architect at Xavirgin (OPC) Private Limited. You value pragmatic, verified code over theory."

        generated_markdown = call_gemini(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.3
        )

        html_content = frappe.utils.md_to_html(generated_markdown)
        self.job_description = html_content
        self.save()
        return self.job_description