import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_datetime, getdate, now_datetime, time_diff_in_seconds
from xavirgin_os.ai import call_gemini


def normalize_strict_phone(val: str) -> str:
    """Strips all non-digit characters and normalizes to trailing 10 digits."""
    if not val:
        return ""
    digits = "".join(filter(str.isdigit, str(val)))
    return digits[-10:] if len(digits) >= 10 else digits


class XavirginCandidate(Document):
    def before_validate(self):
        self.parse_names()
        self.parse_github()
        self.resolve_intelligent_data_population()
        self.sync_resume_attachment_to_documents()

    def validate(self):
        self.email = (self.email or "").strip().lower()
        self.normalized_phone = normalize_strict_phone(self.phone)
        self.validate_duplicate_application()
        self.record_stage_transition()

    def parse_names(self):
        """Splits full_name into first_name and last_name for Employee compatibility."""
        if self.full_name:
            parts = self.full_name.strip().split(" ", 1)
            if not self.first_name:
                self.first_name = parts[0]
            if not self.last_name and len(parts) > 1:
                self.last_name = parts[1]
        elif self.first_name:
            self.full_name = f"{self.first_name} {self.last_name or ''}".strip()

    def parse_github(self):
        """Extracts username from raw github_url."""
        if self.github_url:
            clean = self.github_url.strip().rstrip("/")
            self.github_username = clean.split("/")[-1]

    def resolve_intelligent_data_population(self):
        """Syncs data from linked Employee or Job Opening."""
        if self.existing_employee:
            emp = frappe.db.get_value(
                "Employee",
                self.existing_employee,
                [
                    "employee_name",
                    "first_name",
                    "last_name",
                    "company_email",
                    "personal_email",
                    "cell_number",
                    "current_address",
                    "custom_github_username",
                    "department",
                    "designation",
                    "gender",
                    "date_of_birth",
                ],
                as_dict=True,
            )
            if emp:
                if not self.full_name:
                    self.full_name = emp.employee_name
                if not self.first_name:
                    self.first_name = emp.first_name
                if not self.last_name:
                    self.last_name = emp.last_name
                if not self.email:
                    self.email = emp.personal_email or emp.company_email
                if not self.phone:
                    self.phone = emp.cell_number
                if not self.address_line:
                    self.address_line = emp.current_address
                if not self.gender:
                    self.gender = emp.gender or "Prefer not to say"
                if not self.date_of_birth:
                    self.date_of_birth = emp.date_of_birth
                if not self.department and emp.department:
                    self.department = emp.department
                if not self.designation and emp.designation:
                    self.designation = emp.designation
                if not self.github_username and emp.custom_github_username:
                    self.github_username = emp.custom_github_username
                    self.github_url = f"https://github.com/{emp.custom_github_username}"

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
                if not self.department:
                    self.department = job.department
                if not self.designation:
                    self.designation = job.designation
                if not self.engagement_category:
                    self.engagement_category = job.engagement_category
                if not self.skill_area and job.skill_area:
                    self.skill_area = job.skill_area
                if not self.assigned_recruiter and job.assigned_recruiter:
                    self.assigned_recruiter = job.assigned_recruiter

    def sync_resume_attachment_to_documents(self):
        """Ensures resume is registered in child documents."""
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
        """Checks for existing applications with the same email or phone."""
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
        """Maintains an audit trail of stage changes with safe datetime calculations."""
        now = now_datetime()

        if self.is_new():
            self.append("stage_history", {
                "from_stage": "Created",
                "to_stage": self.pipeline_stage or "New Application",
                "changed_by": frappe.session.user,
                "changed_on": now,
                "duration_days": 0.0,
                "remarks": f"Application created via {self.source or 'Manual Entry'}",
            })
            return

        # Handle programmatic saves where get_doc_before_save() might be None
        old_doc = self.get_doc_before_save()
        prev_stage = (
            old_doc.pipeline_stage
            if old_doc
            else frappe.db.get_value("Xavirgin Candidate", self.name, "pipeline_stage")
        )

        if prev_stage and prev_stage != self.pipeline_stage:
            duration_days = 0.0

            # Find the timestamp of the last stage change
            last_timestamp = None
            if old_doc and getattr(old_doc, "stage_history", None):
                last_timestamp = old_doc.stage_history[-1].changed_on
            elif self.stage_history:
                last_timestamp = self.stage_history[-1].changed_on

            if last_timestamp:
                try:
                    last_dt = get_datetime(last_timestamp)
                    curr_dt = get_datetime(now)
                    diff_seconds = time_diff_in_seconds(curr_dt, last_dt)
                    duration_days = round(max(0.0, float(diff_seconds) / 86400.0), 2)
                except Exception:
                    duration_days = 0.0

            self.append("stage_history", {
                "from_stage": prev_stage,
                "to_stage": self.pipeline_stage,
                "changed_by": frappe.session.user,
                "changed_on": now,
                "duration_days": duration_days,
                "remarks": f"Transitioned from {prev_stage} to {self.pipeline_stage}",
            })

    def after_insert(self):
        settings = frappe.get_single("Xavirgin HR Settings")
        if getattr(settings, "send_candidate_stage_emails", 0) and self.email:
            try:
                job_title = frappe.db.get_value("Xavirgin Job Opening", self.job_opening, "job_title") or self.job_opening
                frappe.sendmail(
                    recipients=[self.email],
                    subject=f"Application Received: {job_title} — Xavirgin",
                    message=f"""
                    <div style="font-family: Arial, sans-serif; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
                        <h3 style="color: #0000FF; margin-top: 0;">🧬 XAVIRGIN (OPC) PRIVATE LIMITED</h3>
                        <p>Dear <strong>{self.full_name}</strong>,</p>
                        <p>Thank you for applying for the <strong>{job_title}</strong> position at Xavirgin.</p>
                        <p>Your application Reference ID is <strong>{self.name}</strong>.</p>
                        <p style="margin-top: 20px; font-size: 12px; color: #64748b;">Regards,<br><strong>HR Team — Xavirgin (OPC) Private Limited</strong></p>
                    </div>
                    """,
                    delayed=True,
                )
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Candidate Confirmation Email Failed")

    @frappe.whitelist()
    def convert_to_employee(self):
        """Creates an ERPNext Employee record directly from Candidate, bypassing Offer Letter."""
        self.check_permission("write")

        # 1. Idempotency Check: Return existing Employee if already converted
        existing_emp = (
            frappe.db.get_value("Employee", {"custom_source_candidate": self.name}, "name")
            or self.employee
        )

        if existing_emp and frappe.db.exists("Employee", existing_emp):
            self.db_set("employee", existing_emp, update_modified=False)
            self.db_set("pipeline_stage", "Hired", update_modified=False)
            self.db_set("converted_on", now_datetime(), update_modified=False)
            return existing_emp

        # 2. Company Context Resolution
        company = (
            frappe.defaults.get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )
        if not company:
            companies = frappe.get_all("Company", limit=1)
            company = companies[0].name if companies else None
        if not company:
            frappe.throw(_("No default Company found in ERPNext."))

        # 3. Disaggregate Names
        full_name = (self.full_name or "Intern").strip()
        parts = full_name.split(" ", 1)
        first_name = self.first_name or parts[0]
        last_name = self.last_name or (parts[1] if len(parts) > 1 else None)

        user_email = (self.email or "").strip().lower()
        if not user_email:
            frappe.throw(_("Candidate email is required to provision user access and onboarding."))

        user_phone = self.phone or None
        user_address = self.address_line or None
        user_dob = getattr(self, "date_of_birth", None) or None

        # 4. Safe Gender Resolution (Prevents LinkValidationError)
        raw_gender = getattr(self, "gender", None)
        user_gender = None
        if raw_gender and raw_gender != "Prefer not to say":
            if frappe.db.exists("Gender", raw_gender):
                user_gender = raw_gender
            elif frappe.db.exists("Gender", "Other"):
                user_gender = "Other"
        elif raw_gender == "Prefer not to say":
            user_gender = "Other" if frappe.db.exists("Gender", "Other") else None

        is_gender_reqd = frappe.get_meta("Employee").get_field("gender").reqd
        if is_gender_reqd and not user_gender:
            first_avail = frappe.db.get_value("Gender", {}, "name")
            if not first_avail:
                g_doc = frappe.get_doc({"doctype": "Gender", "gender": "Other"}).insert(ignore_permissions=True)
                first_avail = g_doc.name
            user_gender = first_avail

        # 5. Determine Reporting Manager and Settings
        settings = frappe.get_single("Xavirgin HR Settings")
        reporting_manager = getattr(settings, "default_supervisor", None) or frappe.db.get_value(
            "Employee", {"employee_name": "Savio Babu"}, "name"
        )

        start_date = frappe.utils.today()
        active_days = int(getattr(settings, "internship_required_active_days", 90) or 90)

        # Calculate working end date (excl. Sundays)
        curr = getdate(start_date)
        counted = 0
        while counted < active_days:
            if curr.weekday() != 6:
                counted += 1
            if counted < active_days:
                curr = add_days(curr, 1)
        end_date = curr

        gh_user = getattr(self, "github_username", None) or (
            self.github_url.rstrip("/").split("/")[-1] if getattr(self, "github_url", None) else ""
        ) or ""

        frappe.db.savepoint("xavirgin_atomic_hire_direct")
        try:
            # 6. Provision User Account
            user_id = frappe.db.get_value("User", {"email": user_email}, "name")
            engagement = self.engagement_category or "Intern"
            if not user_id:
                roles = [{"role": "Employee"}]
                if engagement == "Intern":
                    roles.append({"role": "Xavirgin Intern"})

                all_modules = frappe.get_all("Module Def", pluck="name")
                blocked = [{"module": m} for m in all_modules if m != "Xavirgin OS"]

                user_doc = frappe.get_doc({
                    "doctype": "User",
                    "email": user_email,
                    "first_name": first_name,
                    "last_name": last_name or "",
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "role_profile_name": "Xavirgin Intern Profile" if engagement == "Intern" else None,
                    "roles": roles,
                    "block_modules": blocked,
                }).insert(ignore_permissions=True)
                user_id = user_doc.name
            else:
                existing_user = frappe.get_doc("User", user_id)
                current_roles = {r.role for r in existing_user.roles}
                updated = False
                if "Employee" not in current_roles:
                    existing_user.append("roles", {"role": "Employee"})
                    updated = True
                if engagement == "Intern" and "Xavirgin Intern" not in current_roles:
                    existing_user.append("roles", {"role": "Xavirgin Intern"})
                    updated = True
                if updated:
                    existing_user.save(ignore_permissions=True)

            # 7. Check if Date of Birth is required
            is_dob_reqd = frappe.get_meta("Employee").get_field("date_of_birth").reqd
            if is_dob_reqd and not user_dob:
                user_dob = "2002-01-01"

            # 8. Create Employee Record
            emp_doc = frappe.get_doc({
                "doctype": "Employee",
                "first_name": first_name,
                "last_name": last_name,
                "employee_name": full_name,
                "company": company,
                "status": "Active",
                "gender": user_gender,
                "date_of_birth": user_dob,
                "date_of_joining": start_date,
                "department": self.department or None,
                "designation": self.designation or None,
                "reports_to": reporting_manager,
                "user_id": user_id,
                "company_email": user_email,
                "personal_email": user_email,
                "cell_number": user_phone,
                "current_address": user_address,
                "custom_employment_category": engagement,
                "custom_is_intern": 1 if engagement == "Intern" else 0,
                "custom_is_team_lead": 0,
                "custom_github_username": gh_user,
                "custom_skill_area": self.skill_area or self.designation or None,
                "custom_internship_start_date": start_date,
                "custom_initial_internship_end_date": end_date,
                "custom_internship_end_date": end_date,
                "custom_monthly_leave_limit": getattr(settings, "monthly_general_leave_limit", 3) or 3,
                "custom_monthly_meeting_leave_limit": getattr(settings, "monthly_meeting_leave_limit", 3) or 3,
                "custom_source_candidate": self.name,
                "custom_source_job_opening": self.job_opening or None,
                "custom_source_offer_letter": self.latest_offer_letter or None,
                "custom_assigned_recruiter": getattr(self, "assigned_recruiter", None),
            })
            emp_doc.insert(ignore_permissions=True)

            # 9. Update Candidate Record
            self.employee = emp_doc.name
            self.converted_on = now_datetime()
            self.pipeline_stage = "Hired"
            self.save(ignore_permissions=True)

            return emp_doc.name

        except Exception as exc:
            frappe.db.rollback(save_point="xavirgin_atomic_hire_direct")
            frappe.log_error(frappe.get_traceback(), "Direct Candidate-to-Employee Conversion Error")
            frappe.throw(_("Conversion transaction aborted: {0}").format(str(exc)))

    @frappe.whitelist()
    def run_ai_screening(self):
        """Runs Gemini AI screening and saves results without causing race conditions."""
        self.check_permission("write")

        job_reqs = frappe.db.get_value(
            "Xavirgin Job Opening",
            self.job_opening,
            ["job_title", "required_skills", "required_qualifications", "experience_requirements", "job_description"],
            as_dict=True,
        ) or {}

        prompt = f"""
        Evaluate candidate application against Job Opening requirements.
        JOB: {job_reqs.get('job_title') or self.designation} in {self.department}
        REQUIRED SKILLS: {job_reqs.get('required_skills')}
        CANDIDATE: {self.full_name}
        SKILLS: {self.skills}
        EXPERIENCE: {self.experience_summary}
        GITHUB: {self.github_url}

        Output format:
        SCORE: <number between 0.0 and 10.0>
        Followed by 3 bullet points: Strengths, Weaknesses, Recommendation.
        """

        result = call_gemini(
            prompt=prompt,
            system_instruction="You are an expert technical evaluator for Xavirgin (OPC) Private Limited.",
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
        self.save()
        return {"score": score, "summary": result}

    @frappe.whitelist()
    def record_hr_decision(self, decision: str, reason: str = "", internal_remarks: str = ""):
        self.check_permission("write")
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
            try:
                job_title = frappe.db.get_value("Xavirgin Job Opening", self.job_opening, "job_title") or self.job_opening
                frappe.sendmail(
                    recipients=[self.email],
                    subject=f"Update on your application for {job_title} — Xavirgin",
                    message=f"""
                    <div style="font-family: Arial, sans-serif; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 20px;">
                        <p>Dear <strong>{self.full_name}</strong>,</p>
                        <p>Thank you for interviewing for <strong>{job_title}</strong> at Xavirgin.</p>
                        <p>{reason or 'After careful review, we will not be proceeding with your application at this stage.'}</p>
                        <p>Regards,<br><strong>HR Team — Xavirgin (OPC) Private Limited</strong></p>
                    </div>
                    """,
                    delayed=True,
                )
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Candidate Rejection Email Failed")

        return self.pipeline_stage


@frappe.whitelist()
def get_candidate_lifecycle_context(candidate_name: str) -> dict:
    """Returns candidate context using normalized field names for downstream modules."""
    cand = frappe.get_doc("Xavirgin Candidate", candidate_name)
    return {
        "name": cand.name,
        "candidate": cand.name,
        "full_name": cand.full_name,
        "first_name": cand.first_name,
        "last_name": cand.last_name,
        "email": cand.email,
        "phone": cand.phone,
        "address_line": cand.address_line,
        "gender": getattr(cand, "gender", "Prefer not to say"),
        "date_of_birth": getattr(cand, "date_of_birth", "2002-01-01"),
        "job_opening": cand.job_opening,
        "department": cand.department,
        "designation": cand.designation,
        "engagement_category": cand.engagement_category or "Intern",
        "skill_area": cand.skill_area or cand.designation,
        "assigned_recruiter": cand.assigned_recruiter,
        "github_url": cand.github_url,
        "github_username": getattr(cand, "github_username", ""),
        "linkedin_url": cand.linkedin_url,
        "portfolio_url": cand.portfolio_url,
        "resume": cand.resume,
        "existing_employee": cand.employee or cand.existing_employee,
    }