import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    add_days,
    date_diff,
    format_datetime,
    format_time,
    formatdate,
    get_datetime,
    getdate,
    now_datetime,
    time_diff_in_seconds,
    today,
)
from xavirgin_os.ai import call_gemini


PIPELINE_STAGES_ORDER = [
    "New Application",
    "Initial Screening",
    "Shortlisted",
    "Interview Scheduled",
    "Interview Completed",
    "Technical Assessment",
    "Final Review",
    "Offer Preparation",
    "Offer Sent",
    "Offer Accepted",
    "Hired",
]

COMPLETED_STAGES = {"Hired", "Rejected"}
INACTIVE_STAGES = {"Hired", "Rejected", "Offer Rejected", "Withdrawn"}


def is_hr_or_admin_user(user: str = None) -> bool:
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    roles = set(frappe.get_roles(user))
    return bool(roles.intersection({"System Manager", "Xavirgin HR Admin", "Xavirgin HR Manager", "Xavirgin Recruiter"}))


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

        old_doc = self.get_doc_before_save()
        prev_stage = (
            old_doc.pipeline_stage
            if old_doc
            else frappe.db.get_value("Xavirgin Candidate", self.name, "pipeline_stage")
        )

        if prev_stage and prev_stage != self.pipeline_stage:
            duration_days = 0.0
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

        existing_emp = (
            frappe.db.get_value("Employee", {"custom_source_candidate": self.name}, "name")
            or self.employee
        )

        if existing_emp and frappe.db.exists("Employee", existing_emp):
            self.db_set("employee", existing_emp, update_modified=False)
            self.db_set("pipeline_stage", "Hired", update_modified=False)
            self.db_set("converted_on", now_datetime(), update_modified=False)
            return existing_emp

        company = (
            frappe.defaults.get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )
        if not company:
            companies = frappe.get_all("Company", limit=1)
            company = companies[0].name if companies else None
        if not company:
            frappe.throw(_("No default Company found in ERPNext."))

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

        settings = frappe.get_single("Xavirgin HR Settings")
        reporting_manager = getattr(settings, "default_supervisor", None) or frappe.db.get_value(
            "Employee", {"employee_name": "Savio Babu"}, "name"
        )

        start_date = frappe.utils.today()
        active_days = int(getattr(settings, "internship_required_active_days", 90) or 90)

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

            is_dob_reqd = frappe.get_meta("Employee").get_field("date_of_birth").reqd
            if is_dob_reqd and not user_dob:
                user_dob = "2002-01-01"

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


# ==============================================================================
# Whitelisted Recruitment Pipeline, Funnel & Candidate Workspace APIs
# ==============================================================================

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


@frappe.whitelist()
def update_candidate_stage(candidate_name: str, new_stage: str, remarks: str = ""):
    """Allows authorized HR/Admin users to transition candidate stages from the Kanban board."""
    if not is_hr_or_admin_user():
        frappe.throw(_("Access Denied: Only authorized HR and Administrative users can change candidate stages."), frappe.PermissionError)

    doc = frappe.get_doc("Xavirgin Candidate", candidate_name)
    if doc.pipeline_stage == new_stage:
        return {"status": "unchanged", "stage": doc.pipeline_stage}

    doc.pipeline_stage = new_stage
    if remarks:
        doc.decision_reason = remarks
    doc.save()
    return {"status": "updated", "stage": doc.pipeline_stage}


@frappe.whitelist()
def get_candidate_workspace_overview(candidate_name: str) -> dict:
    """Fetches complete lifecycle timeline, related records (Interviews, Evaluations, Offer Letters,
    Employee record, Attendance sessions if hired), and outcome status for a single Candidate record.
    """
    if not candidate_name or not frappe.db.exists("Xavirgin Candidate", candidate_name):
        return {}

    cand = frappe.get_doc("Xavirgin Candidate", candidate_name)
    can_manage = is_hr_or_admin_user()

    # 1. Stage Timeline Computation
    current_stage = cand.pipeline_stage or "New Application"
    history_map = {}
    for h in cand.stage_history or []:
        if h.to_stage:
            history_map[h.to_stage] = {
                "date": formatdate(h.changed_on, "dd MMM yyyy") if h.changed_on else "",
                "by": h.changed_by,
                "duration_days": float(h.duration_days or 0),
                "remarks": h.remarks or "",
            }

    timeline_steps = []
    curr_idx = PIPELINE_STAGES_ORDER.index(current_stage) if current_stage in PIPELINE_STAGES_ORDER else -1
    is_terminal_negative = current_stage in ("Rejected", "Offer Rejected", "Withdrawn")

    for idx, st in enumerate(PIPELINE_STAGES_ORDER):
        hist = history_map.get(st)
        if st == current_stage:
            state = "current"
        elif hist or (curr_idx > idx and not is_terminal_negative):
            state = "completed"
        else:
            state = "pending"

        timeline_steps.append({
            "stage": st,
            "state": state,
            "date": hist["date"] if hist else (formatdate(cand.creation, "dd MMM") if idx == 0 else ""),
            "duration_days": hist["duration_days"] if hist else 0,
        })

    if is_terminal_negative:
        neg_hist = history_map.get(current_stage, {})
        timeline_steps.append({
            "stage": current_stage,
            "state": "rejected",
            "date": neg_hist.get("date") or formatdate(cand.modified, "dd MMM yyyy"),
            "duration_days": neg_hist.get("duration_days", 0),
        })

    # Calculate completion progress %
    if current_stage == "Hired":
        progress_pct = 100
    elif is_terminal_negative:
        progress_pct = 100
    elif curr_idx >= 0:
        progress_pct = round(((curr_idx + 1) / len(PIPELINE_STAGES_ORDER)) * 100)
    else:
        progress_pct = 10

    # 2. Interviews & Panel Members
    interviews = frappe.get_all(
        "Xavirgin Interview",
        filters={"candidate": cand.name},
        fields=[
            "name",
            "interview_round",
            "status",
            "interview_date",
            "start_time",
            "end_time",
            "meeting_platform",
            "meeting_url",
            "submitted_evaluations_count",
            "average_score",
            "consensus_recommendation",
        ],
        order_by="interview_date desc, start_time desc",
    )
    for iv in interviews:
        iv["formatted_date"] = formatdate(iv.interview_date, "dd MMM yyyy") if iv.interview_date else "-"
        try:
            iv["formatted_time"] = f"{format_time(iv.start_time, 'hh:mm a')} – {format_time(iv.end_time, 'hh:mm a')}"
        except Exception:
            iv["formatted_time"] = f"{iv.start_time or ''} – {iv.end_time or ''}"

    # 3. Individual Interviewer Evaluations
    evaluations = frappe.get_all(
        "Xavirgin Interview Evaluation",
        filters={"candidate": cand.name, "docstatus": ["!=", 2]},
        fields=[
            "name",
            "interview",
            "interviewer_name",
            "evaluation_date",
            "total_score",
            "max_possible_score",
            "recommendation",
            "docstatus",
        ],
        order_by="creation desc",
    )
    for ev in evaluations:
        ev["formatted_date"] = formatdate(ev.evaluation_date, "dd MMM yyyy") if ev.evaluation_date else "-"

    # 4. Offer Letters
    offers = []
    if frappe.db.exists("DocType", "Xavirgin Offer Letter"):
        offers = frappe.get_all(
            "Xavirgin Offer Letter",
            filters={"candidate": cand.name},
            fields=["name", "workflow_state", "issue_date", "joining_date"],
            order_by="creation desc",
        )

    # 5. Employee & Attendance Telemetry (if converted/hired)
    emp_id = cand.employee or frappe.db.get_value("Employee", {"custom_source_candidate": cand.name}, "name")
    emp_info = {}
    attendance_count = 0
    if emp_id and frappe.db.exists("Employee", emp_id):
        emp_info = frappe.db.get_value(
            "Employee",
            emp_id,
            ["name", "employee_name", "status", "date_of_joining", "custom_xp_points", "custom_badge_level", "custom_active_days_completed"],
            as_dict=True,
        ) or {}
        if emp_info.get("date_of_joining"):
            emp_info["formatted_joining"] = formatdate(emp_info["date_of_joining"], "dd MMM yyyy")
        attendance_count = frappe.db.count("Xavirgin Attendance Session", {"employee": emp_id})

    # 6. Documents & Attachments
    doc_items = []
    if cand.resume:
        doc_items.append({"type": "Resume / CV", "name": "Primary Resume", "url": cand.resume, "verified": 1})
    for d in cand.documents or []:
        if d.file_url and d.file_url != cand.resume:
            doc_items.append({
                "type": d.document_type,
                "name": d.document_name or d.document_type,
                "url": d.file_url,
                "verified": d.verified_by_hr,
            })

    job_title = frappe.db.get_value("Xavirgin Job Opening", cand.job_opening, "job_title") if cand.job_opening else cand.designation

    return {
        "can_manage": can_manage,
        "candidate_name": cand.full_name,
        "job_title": job_title or cand.designation or "Applicant",
        "applied_date": formatdate(cand.creation, "dd MMM yyyy") if cand.creation else "-",
        "days_in_pipeline": date_diff(today(), getdate(cand.creation)) if cand.creation else 0,
        "current_stage": current_stage,
        "progress_pct": progress_pct,
        "is_hired": current_stage == "Hired" or bool(emp_id),
        "is_rejected": current_stage in ("Rejected", "Offer Rejected"),
        "timeline": timeline_steps,
        "interviews": interviews,
        "evaluations": evaluations,
        "offers": offers,
        "employee_info": emp_info,
        "attendance_count": attendance_count,
        "documents": doc_items,
    }


@frappe.whitelist()
def get_candidate_pipeline_dashboard(
    department: str = None,
    job_opening: str = None,
    source: str = None,
    recruiter: str = None,
    search_text: str = None,
    date_from: str = None,
    date_to: str = None,
) -> dict:
    """Returns comprehensive data for the Candidate Recruitment Pipeline Kanban, Funnel & Source Analytics Dashboard."""
    can_manage = is_hr_or_admin_user()
    today_date = getdate(today())

    filters = {}
    if department:
        filters["department"] = department
    if job_opening:
        filters["job_opening"] = job_opening
    if source:
        filters["source"] = source
    if recruiter:
        filters["assigned_recruiter"] = recruiter

    candidates = frappe.get_all(
        "Xavirgin Candidate",
        filters=filters,
        fields=[
            "name",
            "full_name",
            "email",
            "phone",
            "job_opening",
            "department",
            "designation",
            "engagement_category",
            "skill_area",
            "pipeline_stage",
            "source",
            "assigned_recruiter",
            "ai_match_score",
            "latest_interview",
            "average_evaluation_score",
            "overall_recommendation",
            "final_decision",
            "decision_date",
            "decision_reason",
            "employee",
            "converted_on",
            "resume",
            "creation",
            "modified",
        ],
        order_by="modified desc",
    )

    # Batch lookup interview statuses
    interview_names = [c.latest_interview for c in candidates if c.latest_interview]
    interview_map = {}
    if interview_names:
        for iv in frappe.get_all(
            "Xavirgin Interview",
            filters={"name": ["in", interview_names]},
            fields=["name", "status", "interview_date", "start_time", "interview_round", "submitted_evaluations_count"],
        ):
            interview_map[iv.name] = iv

    search_q = (search_text or "").strip().lower()
    d_from = getdate(date_from) if date_from else None
    d_to = getdate(date_to) if date_to else None

    filtered_candidates = []
    for c in candidates:
        c_date = getdate(c.creation) if c.creation else today_date
        if d_from and c_date < d_from:
            continue
        if d_to and c_date > d_to:
            continue
        if search_q:
            hay = f"{c.name} {c.full_name or ''} {c.email or ''} {c.phone or ''} {c.department or ''} {c.designation or ''} {c.skill_area or ''} {c.source or ''}".lower()
            if search_q not in hay:
                continue
        filtered_candidates.append(c)

    # Metrics & Aggregations
    kpis = {
        "total_applications": len(filtered_candidates),
        "today_applications": 0,
        "active_pipeline": 0,
        "awaiting_interview": 0,
        "interviews_scheduled": 0,
        "assessments_completed": 0,
        "awaiting_hr_decision": 0,
        "offers_processing": 0,
        "hired_count": 0,
        "rejected_count": 0,
        "needs_attention_count": 0,
        "conversion_rate_pct": 0.0,
        "rejection_rate_pct": 0.0,
    }

    source_distribution = {}
    dept_distribution = {}
    stage_columns = {st: [] for st in PIPELINE_STAGES_ORDER if st != "Hired"}
    completed_outcomes = []
    needs_attention_list = []

    for c in filtered_candidates:
        stage = c.pipeline_stage or "New Application"
        src = c.source or "Direct / Unspecified"
        dept = c.department or "Unassigned Department"
        c_date = getdate(c.creation) if c.creation else today_date
        last_mod_days = date_diff(today_date, getdate(c.modified)) if c.modified else 0

        if c_date == today_date:
            kpis["today_applications"] += 1

        # Source Breakdown
        s_bucket = source_distribution.setdefault(src, {"source": src, "total": 0, "shortlisted": 0, "hired": 0, "rejected": 0})
        s_bucket["total"] += 1

        # Department Breakdown
        d_bucket = dept_distribution.setdefault(dept, {"department": dept, "total": 0, "active": 0, "hired": 0, "rejected": 0})
        d_bucket["total"] += 1

        if stage not in ("New Application", "Initial Screening", "Rejected", "Withdrawn"):
            s_bucket["shortlisted"] += 1

        iv_info = interview_map.get(c.latest_interview, {})
        has_eval = float(c.average_evaluation_score or 0) > 0 or int(iv_info.get("submitted_evaluations_count") or 0) > 0

        if has_eval:
            kpis["assessments_completed"] += 1

        # Needs Attention: Active candidate sitting idle > 3 days or Interview Completed awaiting HR decision
        attention_reason = ""
        if stage not in INACTIVE_STAGES:
            if stage in ("Interview Completed", "Final Review") and not c.final_decision:
                attention_reason = "Awaiting HR Decision"
            elif stage in ("New Application", "Initial Screening") and float(c.ai_match_score or 0) == 0:
                attention_reason = "Needs AI / Initial Screening"
            elif stage == "Shortlisted" and not c.latest_interview:
                attention_reason = "Needs Interview Slot"
            elif last_mod_days >= 4:
                attention_reason = f"Idle for {last_mod_days}d"

        card = {
            "name": c.name,
            "full_name": c.full_name,
            "email": c.email,
            "phone": c.phone,
            "job_opening": c.job_opening,
            "department": dept,
            "designation": c.designation or c.skill_area or "Applicant",
            "pipeline_stage": stage,
            "source": src,
            "assigned_recruiter": c.assigned_recruiter or "",
            "applied_date": formatdate(c.creation, "dd MMM yyyy") if c.creation else "-",
            "last_activity_days": last_mod_days,
            "ai_score": float(c.ai_match_score or 0),
            "eval_score": float(c.average_evaluation_score or 0),
            "recommendation": c.overall_recommendation or "",
            "interview_name": c.latest_interview,
            "interview_status": iv_info.get("status") or ("Scheduled" if c.latest_interview else "None"),
            "interview_date": formatdate(iv_info.get("interview_date"), "dd MMM") if iv_info.get("interview_date") else "",
            "has_resume": bool(c.resume),
            "employee": c.employee,
            "decision_reason": c.decision_reason or "",
            "attention_reason": attention_reason,
        }

        if stage == "Hired":
            kpis["hired_count"] += 1
            s_bucket["hired"] += 1
            d_bucket["hired"] += 1
            completed_outcomes.append(card)
        elif stage in ("Rejected", "Offer Rejected", "Withdrawn"):
            kpis["rejected_count"] += 1
            s_bucket["rejected"] += 1
            d_bucket["rejected"] += 1
            completed_outcomes.append(card)
        else:
            kpis["active_pipeline"] += 1
            d_bucket["active"] += 1
            if stage in ("New Application", "Initial Screening", "Shortlisted"):
                kpis["awaiting_interview"] += 1
            elif stage == "Interview Scheduled":
                kpis["interviews_scheduled"] += 1
            elif stage in ("Interview Completed", "Technical Assessment", "Final Review"):
                kpis["awaiting_hr_decision"] += 1
            elif stage in ("Offer Preparation", "Offer Sent", "Offer Accepted"):
                kpis["offers_processing"] += 1

            stage_columns.setdefault(stage, []).append(card)
            if attention_reason:
                kpis["needs_attention_count"] += 1
                needs_attention_list.append(card)

    total_apps = kpis["total_applications"]
    if total_apps > 0:
        kpis["conversion_rate_pct"] = round((kpis["hired_count"] / total_apps) * 100.0, 1)
        kpis["rejection_rate_pct"] = round((kpis["rejected_count"] / total_apps) * 100.0, 1)

    # Funnel Steps
    shortlisted_plus = sum(
        1 for c in filtered_candidates if (c.pipeline_stage or "") not in ("New Application", "Initial Screening", "Withdrawn")
    )
    interviewed_plus = sum(
        1
        for c in filtered_candidates
        if (c.pipeline_stage or "")
        in ("Interview Scheduled", "Interview Completed", "Technical Assessment", "Final Review", "Offer Preparation", "Offer Sent", "Offer Accepted", "Hired")
        or c.latest_interview
    )
    offer_plus = sum(
        1 for c in filtered_candidates if (c.pipeline_stage or "") in ("Offer Preparation", "Offer Sent", "Offer Accepted", "Hired")
    )

    funnel_steps = [
        {"label": "Total Applications", "count": total_apps, "pct": 100.0, "color": "#2563eb"},
        {"label": "Shortlisted / Screened", "count": shortlisted_plus, "pct": round((shortlisted_plus / total_apps) * 100, 1) if total_apps else 0, "color": "#4f46e5"},
        {"label": "Interview Stage", "count": interviewed_plus, "pct": round((interviewed_plus / total_apps) * 100, 1) if total_apps else 0, "color": "#7c3aed"},
        {"label": "Assessments Scored", "count": kpis["assessments_completed"], "pct": round((kpis["assessments_completed"] / total_apps) * 100, 1) if total_apps else 0, "color": "#d97706"},
        {"label": "Offer Processing", "count": offer_plus, "pct": round((offer_plus / total_apps) * 100, 1) if total_apps else 0, "color": "#0d9488"},
        {"label": "Hired / Onboarded", "count": kpis["hired_count"], "pct": kpis["conversion_rate_pct"], "color": "#16a34a"},
    ]

    all_depts = frappe.get_all("Department", pluck="name")
    all_jobs = frappe.get_all("Xavirgin Job Opening", fields=["name", "job_title"])
    source_meta = frappe.get_meta("Xavirgin Candidate").get_field("source")
    configured_sources = [s.strip() for s in (source_meta.options or "").split("\n") if s.strip()] if source_meta else []
    for s_key in source_distribution.keys():
        if s_key not in configured_sources:
            configured_sources.append(s_key)

    return {
        "can_manage": can_manage,
        "kpis": kpis,
        "funnel": funnel_steps,
        "sources": sorted(source_distribution.values(), key=lambda x: x["total"], reverse=True),
        "departments": sorted(dept_distribution.values(), key=lambda x: x["total"], reverse=True),
        "stage_columns": [
            {"stage": st, "count": len(stage_columns.get(st, [])), "candidates": stage_columns.get(st, [])}
            for st in PIPELINE_STAGES_ORDER
            if st != "Hired"
        ],
        "needs_attention": needs_attention_list,
        "completed_outcomes": completed_outcomes,
        "filter_options": {
            "departments": sorted(all_depts),
            "job_openings": all_jobs,
            "sources": configured_sources,
            "stages": PIPELINE_STAGES_ORDER + ["Rejected", "Offer Rejected", "Withdrawn"],
        },
    }


# ==============================================================================
# Module-Level Permission Hooks for Xavirgin Candidate
# ==============================================================================

def get_permission_query_conditions(user: str = None) -> str:
    """Allows all authenticated internal staff to view recruitment pipeline & candidate status."""
    user = user or frappe.session.user
    if user == "Guest":
        return "1=0"
    return ""


def has_permission(doc, ptype="read", user=None, debug=False) -> bool:
    """Separates read visibility from write/create/delete permissions."""
    user = user or frappe.session.user
    if user == "Guest":
        return False

    if is_hr_or_admin_user(user):
        return True

    if ptype in ("read", "select", "print", "report"):
        return True

    return False