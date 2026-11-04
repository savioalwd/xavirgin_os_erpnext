import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, now_datetime


def calculate_working_end_date(start_date, active_days: int = 90):
    """Calculates exact calendar date after N active working days (excluding Sundays)."""
    current = getdate(start_date)
    counted = 0
    while counted < active_days:
        if current.weekday() != 6:  # 6 = Sunday
            counted += 1
        if counted < active_days:
            current = add_days(current, 1)
    return current


class XavirginOfferLetter(Document):
    def before_validate(self):
        self.resolve_intelligent_offer_defaults()
        self.sync_candidate_documents()

    def resolve_intelligent_offer_defaults(self):
        """Intelligently pulls missing terms from Candidate, Job Opening, and Global HR Settings."""
        settings = frappe.get_single("Xavirgin HR Settings")

        # 1. Dates
        if not self.issue_date:
            self.issue_date = frappe.utils.today()
        if not self.acceptance_deadline:
            acceptance_days = int(settings.offer_acceptance_deadline_days or 2)
            self.acceptance_deadline = add_days(self.issue_date, acceptance_days)

        # 2. Candidate Fallbacks
        if self.candidate:
            cand = frappe.db.get_value(
                "Xavirgin Candidate",
                self.candidate,
                [
                    "full_name",
                    "email",
                    "phone",
                    "address_line",
                    "job_opening",
                    "department",
                    "designation",
                    "skill_area",
                    "engagement_category",
                ],
                as_dict=True,
            )
            if cand:
                if not self.candidate_name:
                    self.candidate_name = cand.full_name
                if not self.candidate_email:
                    self.candidate_email = (cand.email or "").strip().lower()
                if not self.candidate_phone:
                    self.candidate_phone = cand.phone
                if not self.candidate_address:
                    self.candidate_address = cand.address_line
                if not self.job_opening:
                    self.job_opening = cand.job_opening
                if not self.department:
                    self.department = cand.department
                if not self.designation:
                    self.designation = cand.designation
                if not self.skill_area:
                    self.skill_area = cand.skill_area or cand.designation
                if not self.engagement_category and cand.engagement_category:
                    self.engagement_category = cand.engagement_category

        # 3. Job Opening Fallbacks
        if self.job_opening:
            job = frappe.db.get_value(
                "Xavirgin Job Opening",
                self.job_opening,
                ["internship_duration_days", "hiring_manager", "employment_type", "skill_area", "department", "designation"],
                as_dict=True,
            )
            if job:
                if not self.department and job.department:
                    self.department = job.department
                if not self.designation and job.designation:
                    self.designation = job.designation
                if not self.active_working_days_required and job.internship_duration_days:
                    self.active_working_days_required = job.internship_duration_days
                if not self.reporting_manager and job.hiring_manager:
                    self.reporting_manager = job.hiring_manager
                if not self.employment_type and job.employment_type:
                    self.employment_type = job.employment_type
                if not self.skill_area and job.skill_area:
                    self.skill_area = job.skill_area

        # 4. Global Settings Fallbacks
        if not self.active_working_days_required:
            self.active_working_days_required = settings.internship_required_active_days or 90
        if not self.initial_evaluation_days:
            self.initial_evaluation_days = settings.initial_evaluation_days or 15
        if not self.reporting_manager:
            self.reporting_manager = settings.default_supervisor or frappe.db.get_value("Employee", {"employee_name": "Savio Babu"}, "name")

        # 5. Calculate End Date based on active working days
        if not self.start_date:
            self.start_date = frappe.utils.today()

        if self.start_date and not self.end_date:
            days_req = int(self.active_working_days_required or 90)
            self.end_date = calculate_working_end_date(self.start_date, days_req)

        # 6. Version Incrementing
        if self.amended_from and self.is_new():
            prev_ver = frappe.db.get_value("Xavirgin Offer Letter", self.amended_from, "offer_version") or 1
            self.offer_version = int(prev_ver) + 1

    def sync_candidate_documents(self):
        """Pulls all submitted/verified documents from Candidate into Offer Letter verification table."""
        if not self.candidate:
            return

        cand_docs = frappe.get_all(
            "Xavirgin Candidate Document",
            filters={"parent": self.candidate},
            fields=["document_type", "file_url", "document_name", "verified_by_hr", "verified_by", "verification_notes"],
        )
        existing_urls = {d.file_url for d in self.submitted_documents if d.file_url}

        for cd in cand_docs:
            if cd.file_url and cd.file_url not in existing_urls:
                self.append("submitted_documents", {
                    "document_type": cd.document_type,
                    "file_url": cd.file_url,
                    "document_name": cd.document_name,
                    "uploaded_via": "Candidate Master Sync",
                    "uploaded_on": now_datetime(),
                    "verified_by_hr": cd.verified_by_hr,
                    "verified_by": cd.verified_by,
                    "verification_notes": cd.verification_notes,
                })

    def validate(self):
        if self.candidate_email:
            self.candidate_email = self.candidate_email.strip().lower()

        if self.reporting_manager:
            self.reporting_manager_name = (
                frappe.db.get_value("Employee", self.reporting_manager, "employee_name") or "Savio Babu"
            )
        if self.documents_verified and not self.verified_by:
            self.verified_by = frappe.session.user
            self.verified_on = now_datetime()

    def on_submit(self):
        if self.workflow_state in ("Draft", "Pending Approval"):
            self.db_set("workflow_state", "Approved", update_modified=False)
        self.sync_to_candidate()

    def on_update_after_submit(self):
        if self.documents_verified and not self.verified_by:
            self.db_set("verified_by", frappe.session.user, update_modified=False)
            self.db_set("verified_on", now_datetime(), update_modified=False)
        self.sync_to_candidate()

    def sync_to_candidate(self):
        if not self.candidate:
            return
        stage_map = {
            "Draft": "Offer Preparation",
            "Pending Approval": "Offer Preparation",
            "Approved": "Offer Preparation",
            "Sent": "Offer Sent",
            "Accepted": "Offer Accepted",
            "Rejected": "Offer Rejected",
            "Withdrawn": "Withdrawn",
        }
        cand = frappe.get_doc("Xavirgin Candidate", self.candidate)
        cand.latest_offer_letter = self.name
        if self.workflow_state in stage_map and cand.pipeline_stage != "Hired":
            cand.pipeline_stage = stage_map[self.workflow_state]
        cand.save(ignore_permissions=True)

    @frappe.whitelist()
    def send_offer_letter_email(self):
        """Renders 2-page Offer Letter & NDA PDF, saves as private file, and emails candidate."""
        self.check_permission("write")
        if self.docstatus != 1:
            frappe.throw(_("Please Submit (Approve) the Offer Letter before sending it to the candidate."))

        try:
            pdf_bytes = frappe.get_print(
                doctype=self.doctype,
                name=self.name,
                print_format="Xavirgin Offer Letter and NDA",
                as_pdf=True,
            )
        except OSError as e:
            if "wkhtmltopdf" in str(e):
                frappe.throw(
                    _("PDF generation failed: 'wkhtmltopdf' is not installed or configured on the server. Run: sudo apt install -y wkhtmltopdf")
                )
            raise

        safe_name = (self.candidate_name or self.name).replace(" ", "_")
        filename = f"Offer_Letter_NDA_{safe_name}_v{self.offer_version}.pdf"

        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": filename,
            "attached_to_doctype": self.doctype,
            "attached_to_name": self.name,
            "is_private": 1,
            "content": pdf_bytes,
        }).insert(ignore_permissions=True)

        email_body = f"""
        <div style="margin: 0px; padding: 0px; font-family: Arial, sans-serif; font-size: 13px; color: #333333; line-height: 1.5;">
            <p>Dear <strong>{self.candidate_name}</strong>,</p>
            <p>Congratulations! We are pleased to offer you the <strong>{self.designation}</strong> position at <strong>XAVIRGIN (OPC) PRIVATE LIMITED</strong>.</p>
            <p>Please find attached your official <strong>Internship Offer Letter and Non-Disclosure Agreement (NDA)</strong> (Ref: <code>{self.name}</code>).</p>
            <p>Kindly review, sign, and send a scanned copy back to us along with valid proof of identity within <strong>2 days</strong> (by <strong>{frappe.utils.formatdate(self.acceptance_deadline, 'dd MMMM yyyy')}</strong>) to confirm your acceptance.</p>
            <br/>
            <p style="margin-bottom: 5px;">Best regards,</p>
            <p style="margin-top: 0px;">
                <strong>{self.reporting_manager_name or 'Savio Babu'}</strong><br/>
                <span style="color: #666666;">Director — XAVIRGIN (OPC) PRIVATE LIMITED</span>
            </p>
            <hr style="border: none; border-top: 1px solid #cccccc; margin: 20px 0;"/>
            <div style="font-size: 11px; color: #555555; line-height: 1.4;">
                <strong style="color: #0000FF; font-size: 12px;">XAVIRGIN (OPC) PRIVATE LIMITED</strong><br/>
                <strong>CIN:</strong> U62090KL2025OPC098558<br/>
                <strong>Registered Address:</strong> 8/372, Ground Floor, Valiyaparambil, Edathala, Aluva, Ernakulam, Kerala - 683561, India<br/>
                <strong>Website:</strong> <a href="https://xavirgin.com" style="color: #0066cc; text-decoration: none;">xavirgin.com</a> |
                <strong>LinkedIn:</strong> <a href="https://www.linkedin.com/company/xavirgin-com/" style="color: #0066cc; text-decoration: none;">xavirgin-com</a>
            </div>
        </div>
        """

        frappe.sendmail(
            recipients=[self.candidate_email],
            subject=f"Xavirgin Internship Offer Letter & NDA: {self.candidate_name} ({self.name})",
            message=email_body,
            attachments=[{"fname": filename, "fcontent": pdf_bytes}],
            reference_doctype=self.doctype,
            reference_name=self.name,
            delayed=False,
        )

        self.db_set("workflow_state", "Sent", update_modified=False)
        self.sync_to_candidate()
        return _("Offer Letter & NDA v{0} (File: {1}) emailed to {2}.").format(
            self.offer_version, file_doc.file_name, self.candidate_email
        )

    @frappe.whitelist()
    def convert_to_employee(self):
        """Creates an ERPNext Employee record using candidate data with full lineage and safe fallbacks."""
        self.check_permission("write")

        if self.docstatus != 1:
            frappe.throw(_("Offer Letter must be Submitted before converting to an Employee."))
        if self.workflow_state != "Accepted":
            frappe.throw(_("Offer status must be marked as 'Accepted' before onboarding."))
        if not self.documents_verified:
            frappe.throw(_("All Mandatory Documents must be Verified by HR before conversion."))

        # 1. Idempotency check: Return existing Employee if already converted
        existing_emp = (
            frappe.db.get_value("Employee", {"custom_source_candidate": self.candidate}, "name")
            or frappe.db.get_value("Employee", {"custom_source_offer_letter": self.name}, "name")
            or self.employee
        )

        if existing_emp and frappe.db.exists("Employee", existing_emp):
            self.db_set("employee", existing_emp, update_modified=False)
            frappe.db.set_value(
                "Xavirgin Candidate",
                self.candidate,
                {
                    "employee": existing_emp,
                    "pipeline_stage": "Hired",
                    "converted_on": now_datetime(),
                },
                update_modified=False,
            )
            return existing_emp

        # 2. Candidate Context Resolution
        cand = frappe.get_doc("Xavirgin Candidate", self.candidate)
        company = (
            frappe.defaults.get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )
        if not company:
            companies = frappe.get_all("Company", limit=1)
            company = companies[0].name if companies else None
        if not company:
            frappe.throw(_("No default Company found in ERPNext."))

        # Disaggregate names safely
        full_name = (getattr(cand, "full_name", None) or self.candidate_name or "Intern").strip()
        parts = full_name.split(" ", 1)
        first_name = getattr(cand, "first_name", None) or parts[0]
        last_name = getattr(cand, "last_name", None) or (parts[1] if len(parts) > 1 else None)

        user_email = (self.candidate_email or cand.email or "").strip().lower()
        if not user_email:
            frappe.throw(_("Candidate email is required to provision access and onboarding."))

        user_phone = self.candidate_phone or cand.phone or None
        user_address = self.candidate_address or cand.address_line or None
        user_dob = getattr(cand, "date_of_birth", None) or None

        # 4. Safe Gender Resolution (Handles missing/invalid link doctype values)
        raw_gender = getattr(cand, "gender", None)
        user_gender = None
        if raw_gender and raw_gender != "Prefer not to say":
            if frappe.db.exists("Gender", raw_gender):
                user_gender = raw_gender
            else:
                # Create or map to Other if not found
                user_gender = "Other" if frappe.db.exists("Gender", "Other") else None
        elif raw_gender == "Prefer not to say":
            user_gender = "Other" if frappe.db.exists("Gender", "Other") else None

        # Fallback if Gender is mandatory on Employee DocType
        is_gender_reqd = frappe.get_meta("Employee").get_field("gender").reqd
        if is_gender_reqd and not user_gender:
            first_avail = frappe.db.get_value("Gender", {}, "name")
            if not first_avail:
                g_doc = frappe.get_doc({"doctype": "Gender", "gender": "Other"}).insert(ignore_permissions=True)
                first_avail = g_doc.name
            user_gender = first_avail

        gh_user = (
            getattr(cand, "github_username", None)
            or (cand.github_url.rstrip("/").split("/")[-1] if getattr(cand, "github_url", None) else "")
            or ""
        )

        frappe.db.savepoint("xavirgin_atomic_hire")
        try:
            # 5. Provision Frappe User Account
            user_id = frappe.db.get_value("User", {"email": user_email}, "name")
            if not user_id:
                roles = [{"role": "Employee"}]
                if self.engagement_category == "Intern":
                    roles.append({"role": "Xavirgin Intern"})
                if getattr(self, "is_team_lead_role", 0):
                    roles.append({"role": "Xavirgin Team Lead"})

                all_modules = frappe.get_all("Module Def", pluck="name")
                blocked = [{"module": m} for m in all_modules if m != "Xavirgin OS"]

                user_doc = frappe.get_doc({
                    "doctype": "User",
                    "email": user_email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "role_profile_name": "Xavirgin Intern Profile" if self.engagement_category == "Intern" else None,
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
                if self.engagement_category == "Intern" and "Xavirgin Intern" not in current_roles:
                    existing_user.append("roles", {"role": "Xavirgin Intern"})
                    updated = True
                if getattr(self, "is_team_lead_role", 0) and "Xavirgin Team Lead" not in current_roles:
                    existing_user.append("roles", {"role": "Xavirgin Team Lead"})
                    updated = True
                if updated:
                    existing_user.save(ignore_permissions=True)

            # 6. Insert Core Employee Record (Blank fields passed as None)
            settings = frappe.get_single("Xavirgin HR Settings")

            # Check if DOB is mandatory on Employee DocType
            is_dob_reqd = frappe.get_meta("Employee").get_field("date_of_birth").reqd
            if is_dob_reqd and not user_dob:
                user_dob = "2002-01-01"

            emp_doc = frappe.get_doc({
                "doctype": "Employee",
                "first_name": first_name,
                "last_name": last_name or None,
                "employee_name": full_name,
                "company": company,
                "status": "Active",
                "gender": user_gender,
                "date_of_birth": user_dob,
                "date_of_joining": self.start_date or frappe.utils.today(),
                "department": self.department or cand.department or None,
                "designation": self.designation or cand.designation or None,
                "reports_to": self.reporting_manager or None,
                "user_id": user_id,
                "company_email": user_email,
                "personal_email": user_email,
                "cell_number": user_phone,
                "current_address": user_address,
                "custom_employment_category": self.engagement_category or "Intern",
                "custom_is_intern": 1 if self.engagement_category == "Intern" else 0,
                "custom_is_team_lead": 1 if getattr(self, "is_team_lead_role", 0) else 0,
                "custom_team_lead": getattr(self, "team_lead", None),
                "custom_github_username": gh_user,
                "custom_skill_area": self.skill_area or cand.skill_area or None,
                "custom_internship_start_date": self.start_date,
                "custom_initial_internship_end_date": self.end_date,
                "custom_internship_end_date": self.end_date,
                "custom_monthly_leave_limit": settings.monthly_general_leave_limit or 3,
                "custom_monthly_meeting_leave_limit": settings.monthly_meeting_leave_limit or 3,
                "custom_source_candidate": self.candidate,
                "custom_source_job_opening": self.job_opening or cand.job_opening or None,
                "custom_source_offer_letter": self.name,
                "custom_assigned_recruiter": getattr(cand, "assigned_recruiter", None),
            })
            emp_doc.insert(ignore_permissions=True)

            # 7. Two-Way Backlinks and Audit Trail
            self.db_set("employee", emp_doc.name, update_modified=False)
            cand.employee = emp_doc.name
            cand.converted_on = now_datetime()
            cand.pipeline_stage = "Hired"
            cand.append("stage_history", {
                "from_stage": "Offer Accepted",
                "to_stage": "Hired",
                "changed_by": frappe.session.user,
                "changed_on": now_datetime(),
                "duration_days": 0.0,
                "remarks": f"Onboarded to Employee {emp_doc.name} via Offer {self.name}",
            })
            cand.save(ignore_permissions=True)

            return emp_doc.name

        except Exception as exc:
            frappe.db.rollback(save_point="xavirgin_atomic_hire")
            frappe.log_error(frappe.get_traceback(), "Xavirgin Candidate Conversion Failure")
            frappe.throw(_("Conversion transaction aborted: {0}").format(str(exc)))