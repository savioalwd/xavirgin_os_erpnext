import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import format_time, formatdate, getdate, now_datetime, today


def is_hr_or_admin_user(user: str = None) -> bool:
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    roles = set(frappe.get_roles(user))
    return bool(roles.intersection({"System Manager", "Xavirgin HR Admin", "Xavirgin HR Manager", "Xavirgin Recruiter"}))


def format_12h(time_val) -> str:
    if not time_val:
        return "-"
    try:
        return format_time(time_val, "hh:mm a")
    except Exception:
        return str(time_val)


class XavirginInterview(Document):
    def before_validate(self):
        self.resolve_intelligent_interview_defaults()
        self.resolve_and_validate_participants()

    def validate(self):
        self.validate_crud_permissions()
        self.validate_interview_schedule()
        self.detect_schedule_changes()

    def validate_crud_permissions(self):
        """Enforces server-side authorization so non-HR users cannot create or modify interview records."""
        if getattr(self.flags, "ignore_permissions", False):
            return
        if not is_hr_or_admin_user(frappe.session.user):
            frappe.throw(
                _("Access Denied: Only authorized HR and Administrative users can create or modify Interview records."),
                frappe.PermissionError,
            )

    def validate_interview_schedule(self):
        """Validates chronological ordering of interview times."""
        if self.start_time and self.end_time:
            start_td = frappe.utils.to_timedelta(self.start_time)
            end_td = frappe.utils.to_timedelta(self.end_time)
            if end_td <= start_td:
                frappe.throw(_("End Time must be strictly after Start Time."))

    def detect_schedule_changes(self):
        """Detects if core scheduling fields changed on an existing interview (ignoring internal notes/scores)."""
        self.flags.schedule_fields_changed = False
        if self.is_new() or getattr(self.flags, "skip_schedule_notifications", False):
            return

        old_doc = self.get_doc_before_save()
        if not old_doc:
            return

        watched_fields = ("interview_date", "start_time", "end_time", "meeting_url", "meeting_platform", "interview_round")
        for f in watched_fields:
            old_val = str(getattr(old_doc, f, "") or "").strip()
            new_val = str(getattr(self, f, "") or "").strip()
            if old_val != new_val:
                self.flags.schedule_fields_changed = True
                break

        if self.flags.schedule_fields_changed and self.status == "Scheduled":
            self.status = "Rescheduled"

    def resolve_intelligent_interview_defaults(self):
        """Pulls defaults from Candidate, Job Opening, and Global HR Settings."""
        settings = frappe.get_single("Xavirgin HR Settings")

        # 1. Fallback meeting configuration from HR settings
        if not self.meeting_url:
            self.meeting_url = settings.default_meet_link or "https://meet.google.com/xzx-icxk-uje"
        if not self.meeting_platform:
            self.meeting_platform = settings.default_meeting_platform or "Google Meet"

        # 2. Timing defaults
        if not self.interview_date:
            self.interview_date = frappe.utils.today()
        if not self.start_time:
            now_time = now_datetime()
            self.start_time = now_time.strftime("%H:%M:00")
        if not self.end_time and self.start_time:
            duration = int(settings.default_meeting_duration_mins or 40)
            start_dt = frappe.utils.to_timedelta(self.start_time)
            end_dt = start_dt + frappe.utils.to_timedelta(f"00:{duration}:00")
            self.end_time = str(end_dt)

        # 3. Candidate metadata cascade
        if self.candidate:
            cand = frappe.db.get_value(
                "Xavirgin Candidate",
                self.candidate,
                ["job_opening", "designation", "full_name", "email", "phone", "department"],
                as_dict=True,
            )
            if cand:
                if not self.candidate_name:
                    self.candidate_name = cand.full_name
                if not self.candidate_email:
                    self.candidate_email = cand.email
                if not self.candidate_phone:
                    self.candidate_phone = cand.phone
                if not self.job_opening:
                    self.job_opening = cand.job_opening
                if not self.department:
                    self.department = cand.department
                if not self.designation:
                    self.designation = cand.designation

        # 4. Assessment template resolution
        if not self.assessment_template and self.job_opening:
            self.assessment_template = frappe.db.get_value(
                "Xavirgin Job Opening", self.job_opening, "assessment_template"
            )

        if not self.assessment_template and self.designation:
            self.assessment_template = frappe.db.get_value(
                "Xavirgin Assessment Template",
                {"template_name": ["like", f"%{self.designation}%"], "is_active": 1},
                "name",
            )

        if not self.assessment_template:
            self.assessment_template = frappe.db.get_value(
                "Xavirgin Assessment Template", {"is_active": 1}, "name"
            )

        # 5. Fallback Instructions
        if not self.interview_instructions:
            self.interview_instructions = (
                "<div style=\"font-family: Arial, sans-serif; font-size: 13px; line-height: 1.6; color: #2d3748;\">"
                "<h4 style=\"color: #0000FF; margin-bottom: 8px;\">📌 Mandatory Online Interview Instructions</h4>"
                "<ol style=\"margin-top: 0; padding-left: 20px;\">"
                "<li><strong>Early Arrival:</strong> Join the meeting at least <strong>5 minutes prior</strong> to the scheduled start time to test audio and camera readiness.</li>"
                "<li><strong>Hardware & Platform:</strong> Join <strong>exclusively via Laptop or Desktop</strong> with a working webcam and microphone. Mobile logins are strictly disallowed unless explicitly pre-approved by HR.</li>"
                "<li><strong>Connectivity:</strong> Ensure a stable broadband/high-speed internet connection in a quiet, well-lit, distraction-free environment.</li>"
                "<li><strong>Screen Sharing & IDE:</strong> Be ready to share your entire desktop screen and demonstrate live problem-solving using your primary local development environment / IDE.</li>"
                "<li><strong>Verification:</strong> Keep a valid government identity card accessible for visual identity verification at the start of the round.</li>"
                "</ol>"
                "</div>"
            )

    def resolve_and_validate_participants(self):
        """Ensures interviewer details are resolved bidirectionally and emails validated."""
        seen_emails = set()
        for row in self.interviewers:
            if row.employee:
                emp = frappe.db.get_value(
                    "Employee",
                    row.employee,
                    ["employee_name", "company_email", "personal_email", "user_id", "designation", "department"],
                    as_dict=True,
                )
                if emp:
                    row.full_name = row.full_name or emp.employee_name
                    row.interviewer_user = row.interviewer_user or emp.user_id
                    row.designation = row.designation or emp.designation
                    row.department = row.department or emp.department
                    if not row.email:
                        row.email = emp.company_email or emp.personal_email

            if not row.email and row.interviewer_user:
                row.email = frappe.db.get_value("User", row.interviewer_user, "email")

            clean_email = (row.email or "").strip().lower()
            row.email = clean_email
            if clean_email:
                if clean_email in seen_emails:
                    frappe.throw(_("Duplicate interviewer '{0}' found in the panel.").format(row.email))
                seen_emails.add(clean_email)

    def on_update(self):
        if getattr(self.flags, "skip_schedule_notifications", False):
            return

        self.sync_candidate_stage()

        # 1. Automatic Email Notifications on initial creation (Candidate + Panel)
        if not self.candidate_invitation_sent and self.status in ("Scheduled", "Rescheduled") and self.candidate_email:
            try:
                self.send_candidate_interview_invitation(is_rescheduled=False)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Auto Candidate Interview Email Error")

        # 2. Notify any newly added panel members (or all if schedule changed)
        try:
            self.notify_assigned_interviewers(
                force_reschedule=bool(getattr(self.flags, "schedule_fields_changed", False))
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Auto Panel Interview Email Error")

        # 3. If core schedule changed on an already-invited candidate, send rescheduling update automatically
        if getattr(self.flags, "schedule_fields_changed", False) and self.candidate_invitation_sent and self.candidate_email:
            try:
                self.send_candidate_interview_invitation(is_rescheduled=True)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Auto Reschedule Candidate Email Error")

    def sync_candidate_stage(self):
        if not self.candidate or not frappe.db.exists("Xavirgin Candidate", self.candidate):
            return
        cand = frappe.get_doc("Xavirgin Candidate", self.candidate)
        cand.latest_interview = self.name
        if self.status in ("Scheduled", "Rescheduled") and cand.pipeline_stage in ("New Application", "Initial Screening", "Shortlisted"):
            cand.pipeline_stage = "Interview Scheduled"
            cand.save(ignore_permissions=True)
        elif self.status == "Completed" and cand.pipeline_stage == "Interview Scheduled":
            cand.pipeline_stage = "Interview Completed"
            cand.save(ignore_permissions=True)
        else:
            cand.db_set("latest_interview", self.name, update_modified=False)

    def notify_assigned_interviewers(self, force_reschedule: bool = False):
        """Dispatches email & system notifications to panel members upon assignment or rescheduling."""
        settings = frappe.get_single("Xavirgin HR Settings")
        formatted_date = formatdate(self.interview_date, "dd MMMM yyyy")
        formatted_start = format_12h(self.start_time)
        formatted_end = format_12h(self.end_time)

        badge_title = "🔄 Updated / Rescheduled Interview Assignment" if force_reschedule else "🧬 Xavirgin Interview Assignment"
        subject_prefix = "🔄 [RESCHEDULED] Interview Panel" if force_reschedule else "📋 Interview Panel Assignment"

        for row in self.interviewers:
            if row.notification_sent and not force_reschedule:
                continue

            if settings.send_interviewer_email_notifications and row.email:
                frappe.sendmail(
                    recipients=[row.email],
                    subject=f"{subject_prefix}: {self.candidate_name} ({self.interview_round})",
                    message=f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
                        <h3 style="color: #0000FF; margin-top: 0;">{badge_title}</h3>
                        <p>Hello <strong>{row.full_name}</strong>,</p>
                        <p>You are assigned as <strong>{row.interview_role}</strong> for the upcoming candidate evaluation:</p>
                        <ul>
                            <li><strong>Candidate:</strong> {self.candidate_name} ({self.candidate})</li>
                            <li><strong>Position / Department:</strong> {self.designation or "-"} ({self.department or "-"})</li>
                            <li><strong>Round:</strong> {self.interview_round}</li>
                            <li><strong>Date:</strong> {formatted_date}</li>
                            <li><strong>Time (12-Hr):</strong> {formatted_start} – {formatted_end} ({self.timezone})</li>
                            <li><strong>Platform:</strong> {self.meeting_platform}</li>
                            <li><strong>Meeting Link:</strong> <a href="{self.meeting_url}">{self.meeting_url}</a></li>
                        </ul>
                        <div style="margin-top: 15px; padding: 12px; background: #f8fafc; border-left: 3px solid #0000FF;">
                            {self.interview_instructions or "No specific instructions provided."}
                        </div>
                    </div>
                    """,
                    delayed=False,
                )

            if settings.send_interviewer_system_notifications and row.interviewer_user:
                frappe.get_doc({
                    "doctype": "Notification Log",
                    "subject": f"{'Rescheduled' if force_reschedule else 'Interview Assigned'}: {self.candidate_name} on {formatted_date} at {formatted_start}",
                    "for_user": row.interviewer_user,
                    "type": "Alert",
                    "document_type": "Xavirgin Interview",
                    "document_name": self.name,
                }).insert(ignore_permissions=True)

            row.db_set("notification_sent", 1, update_modified=False)

    @frappe.whitelist()
    def send_candidate_interview_invitation(self, is_rescheduled: bool = False):
        """Dispatches interview invitation (or rescheduling notice) to candidate with 12-hour AM/PM slots."""
        self.validate_crud_permissions()
        if not self.interview_date or not self.start_time:
            frappe.throw(_("Please specify Interview Date and Start Time."))
        if not self.candidate_email:
            frappe.throw(_("Candidate email is required."))

        is_rescheduled = bool(int(is_rescheduled)) if isinstance(is_rescheduled, (str, int)) else bool(is_rescheduled)

        job_title = (
            frappe.db.get_value("Xavirgin Job Opening", self.job_opening, "job_title")
            if self.job_opening
            else (self.designation or "Software Engineering Internship")
        )
        formatted_date = formatdate(self.interview_date, "dd MMMM yyyy")
        formatted_start = format_12h(self.start_time)
        formatted_end = format_12h(self.end_time)

        instructions_html = self.interview_instructions or ""
        header_title = "🔄 Updated Technical Interview Schedule" if is_rescheduled else "Technical Interview Invitation"
        slot_heading = "🔄 Rescheduled Interview Slot" if is_rescheduled else "📅 Scheduled Interview Slot"
        email_subject = (
            f"🔄 [RESCHEDULED] Technical Interview: {job_title} — Xavirgin"
            if is_rescheduled
            else f"🧬 Technical Interview Invitation: {job_title} — Xavirgin"
        )
        intro_line = (
            f"Please note that your interview schedule for the <strong style=\"color: #0000FF;\">{job_title}</strong> track at <strong>Xavirgin.com</strong> has been updated. Please find your revised slot details below:"
            if is_rescheduled
            else f"This is the HR Team from <strong>Xavirgin.com</strong>. We have reviewed your application for the <strong style=\"color: #0000FF;\">{job_title}</strong> track."
        )

        html_body = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #2c3e50; background-color: #f4f6f9; padding: 25px;">
            <div style="max-width: 650px; margin: 0 auto; background: #ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08); border: 1px solid #e1e8ed;">
                <div style="background: linear-gradient(135deg, #0000FF 0%, #0033aa 100%); padding: 30px 25px; text-align: center; color: #ffffff;">
                    <div style="font-weight: 800; font-size: 24px; letter-spacing: 1.5px; color: #ffffff;">🧬 XAVIRGIN</div>
                    <p style="margin: 5px 0 0 0; font-size: 13px; opacity: 0.9; letter-spacing: 0.5px; color: #e2e8f0;">Smart Tech Solutions &amp; Software Development</p>
                    <h2 style="font-size: 20px; margin-top: 15px; margin-bottom: 0; font-weight: 600; color: #ffffff;">{header_title}</h2>
                </div>
                <div style="padding: 30px; background: #ffffff;">
                    <p style="font-size: 16px; margin-top: 0; margin-bottom: 15px;">
                        Hello <strong style="color: #0000FF;">{self.candidate_name}</strong>,
                    </p>
                    <p style="color: #4a5568; line-height: 1.7; font-size: 15px;">
                        {intro_line}
                    </p>
                    <div style="background: #f0f4ff; border-left: 4px solid #0000FF; padding: 18px; margin: 20px 0; border-radius: 6px;">
                        <h4 style="margin: 0 0 10px 0; color: #0000FF; font-size: 15px; font-weight: 700;">{slot_heading} ({self.interview_round})</h4>
                        <div style="font-size: 14px; line-height: 1.6; color: #2d3748;">
                            <strong>Date:</strong> {formatted_date}<br/>
                            <strong>Time:</strong> {formatted_start} – {formatted_end} ({self.timezone})<br/>
                            <strong>Platform:</strong> {self.meeting_platform}
                        </div>
                        <div style="margin-top: 12px;">
                            <a href="{self.meeting_url}" style="display: inline-block; padding: 10px 22px; background: #0000FF; color: #ffffff; text-decoration: none; border-radius: 5px; font-weight: 600; font-size: 14px;">
                                🔗 Join {self.meeting_platform} →
                            </a>
                        </div>
                    </div>

                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 20px; margin: 20px 0; border-radius: 8px;">
                        {instructions_html}
                    </div>

                    <div style="background: #ffffff; border: 1px solid #e2e8f0; padding: 20px; margin: 25px 0; border-radius: 8px;">
                        <h3 style="margin-top: 0; margin-bottom: 15px; color: #0000FF; font-size: 16px; font-weight: 700; border-bottom: 2px solid #edf2f7; padding-bottom: 8px;">
                            📌 Internship Details &amp; Guidelines
                        </h3>
                        <ul style="margin: 0; padding-left: 20px; color: #2d3748; font-size: 14px; line-height: 1.8;">
                            <li><strong>Internship Type:</strong> Unpaid Remote Internship</li>
                            <li><strong>Duration:</strong> 90 Active Working Days</li>
                            <li><strong>Daily Work Requirement:</strong> Minimum 4 Hours</li>
                            <li><strong>Daily Team Meeting:</strong> 8:00 PM IST (approx. 40 minutes)</li>
                            <li><strong>Weekly Off:</strong> Sunday</li>
                            <li><strong>Certification:</strong> Internship Completion Certificate &amp; LOR awarded upon successful completion.</li>
                        </ul>
                    </div>
                    <p style="margin-top: 25px; margin-bottom: 5px; font-size: 14px; color: #4a5568;">Regards,</p>
                    <p style="margin: 0; font-size: 15px; color: #0000FF; font-weight: 700;">HR Team (contact@xavirgin.com)</p>
                    <p style="margin: 0; font-size: 13px; color: #718096; font-weight: 600;">XAVIRGIN (OPC) PRIVATE LIMITED</p>
                </div>
            </div>
        </div>
        """

        frappe.sendmail(
            recipients=[self.candidate_email],
            subject=email_subject,
            message=html_body,
            reference_doctype=self.doctype,
            reference_name=self.name,
            delayed=False,
        )
        self.db_set("candidate_invitation_sent", 1, update_modified=False)
        return _("Interview invitation emailed to {0}.").format(self.candidate_email)

    @frappe.whitelist()
    def reschedule_interview_and_notify(
        self,
        interview_date: str = None,
        start_time: str = None,
        end_time: str = None,
        meeting_platform: str = None,
        meeting_url: str = None,
    ):
        """Updates scheduling parameters, marks status as Rescheduled, and sends updated notifications to candidate & panel."""
        self.validate_crud_permissions()

        if interview_date:
            self.interview_date = interview_date
        if start_time:
            self.start_time = start_time
        if end_time:
            self.end_time = end_time
        if meeting_platform:
            self.meeting_platform = meeting_platform
        if meeting_url:
            self.meeting_url = meeting_url

        self.status = "Rescheduled"
        self.flags.skip_schedule_notifications = True
        self.save()

        self.send_candidate_interview_invitation(is_rescheduled=True)
        self.notify_assigned_interviewers(force_reschedule=True)

        return _("Interview rescheduled for {0} ({1} – {2}) and updated notifications sent to candidate and {3} panel member(s).").format(
            formatdate(self.interview_date, "dd MMM yyyy"),
            format_12h(self.start_time),
            format_12h(self.end_time),
            len(self.interviewers),
        )


# ==============================================================================
# Whitelisted APIs for Single Interview Overview & Kanban Dashboard
# ==============================================================================

@frappe.whitelist()
def get_interview_comprehensive_overview(interview_name: str):
    """Fetches complete Candidate profile, resume/attachments, stage history, other interviews,
    Offer Letter/Employee lineage, and each panel interviewer's separate Evaluation breakdown.
    """
    if not interview_name or not frappe.db.exists("Xavirgin Interview", interview_name):
        return {}

    int_doc = frappe.get_doc("Xavirgin Interview", interview_name)
    user = frappe.session.user
    can_manage = is_hr_or_admin_user(user)

    user_lower = (user or "").lower()
    is_panel_member = any(
        (p.interviewer_user and p.interviewer_user.lower() == user_lower)
        or (p.email and p.email.lower() == user_lower)
        for p in int_doc.interviewers
    )

    # 1. Candidate Details & Attachments
    cand_data = {}
    cand_docs = []
    cand_history = []
    other_interviews = []
    offer_letters = []

    if int_doc.candidate and frappe.db.exists("Xavirgin Candidate", int_doc.candidate):
        cand_doc = frappe.get_doc("Xavirgin Candidate", int_doc.candidate)
        cand_data = {
            "name": cand_doc.name,
            "full_name": getattr(cand_doc, "full_name", "") or int_doc.candidate_name,
            "email": getattr(cand_doc, "email", "") or int_doc.candidate_email,
            "phone": getattr(cand_doc, "phone", "") or int_doc.candidate_phone,
            "pipeline_stage": getattr(cand_doc, "pipeline_stage", "Applied"),
            "status": getattr(cand_doc, "status", "") or getattr(cand_doc, "pipeline_stage", "Active"),
            "job_opening": getattr(cand_doc, "job_opening", "") or int_doc.job_opening,
            "department": getattr(cand_doc, "department", "") or int_doc.department,
            "designation": getattr(cand_doc, "designation", "") or int_doc.designation,
            "skill_area": getattr(cand_doc, "skill_area", ""),
            "application_date": formatdate(cand_doc.creation, "dd MMM yyyy") if cand_doc.creation else "-",
            "resume_attachment": getattr(cand_doc, "resume", None) or getattr(cand_doc, "resume_attachment", None) or getattr(cand_doc, "cv_attachment", None),
            "github_url": getattr(cand_doc, "github_url", None),
            "portfolio_url": getattr(cand_doc, "portfolio_url", None) or getattr(cand_doc, "linkedin_url", None),
            "average_evaluation_score": float(getattr(cand_doc, "average_evaluation_score", 0) or 0),
            "overall_recommendation": getattr(cand_doc, "overall_recommendation", ""),
            "employee": getattr(cand_doc, "employee", None),
            "latest_offer_letter": getattr(cand_doc, "latest_offer_letter", None),
        }

        # Check attached files in File doctype if resume field was empty
        attached_files = frappe.get_all(
            "File",
            filters={"attached_to_doctype": "Xavirgin Candidate", "attached_to_name": cand_doc.name},
            fields=["file_name", "file_url"],
        )
        for af in attached_files:
            cand_docs.append({"title": af.file_name, "url": af.file_url})

        for d in getattr(cand_doc, "submitted_documents", []) or getattr(cand_doc, "documents", []) or []:
            if getattr(d, "file_url", None):
                cand_docs.append({"title": getattr(d, "document_type", None) or getattr(d, "document_name", "Document"), "url": d.file_url})

        for h in getattr(cand_doc, "stage_history", []) or []:
            cand_history.append({
                "from_stage": getattr(h, "from_stage", ""),
                "to_stage": getattr(h, "to_stage", ""),
                "changed_on": formatdate(getattr(h, "changed_on", None), "dd MMM yyyy"),
                "remarks": getattr(h, "remarks", ""),
            })

        other_interviews = frappe.get_all(
            "Xavirgin Interview",
            filters={"candidate": int_doc.candidate},
            fields=["name", "interview_round", "status", "interview_date", "start_time", "end_time", "average_score", "consensus_recommendation"],
            order_by="interview_date desc, start_time desc",
        )
        for oi in other_interviews:
            oi["formatted_date"] = formatdate(oi.interview_date, "dd MMM yyyy") if oi.interview_date else "-"
            oi["formatted_time"] = f"{format_12h(oi.start_time)} – {format_12h(oi.end_time)}"

        if frappe.db.exists("DocType", "Xavirgin Offer Letter"):
            offer_letters = frappe.get_all(
                "Xavirgin Offer Letter",
                filters={"candidate": int_doc.candidate},
                fields=["name", "workflow_state", "issue_date", "employee"],
                order_by="creation desc",
            )

    # 2. Separate Panel Evaluations (with criterion-by-criterion breakdown)
    eval_docs = frappe.get_all(
        "Xavirgin Interview Evaluation",
        filters={"interview": interview_name, "docstatus": ["!=", 2]},
        fields=[
            "name",
            "docstatus",
            "interviewer_user",
            "interviewer_employee",
            "interviewer_name",
            "interviewer_email",
            "evaluation_date",
            "total_score",
            "max_possible_score",
            "recommendation",
            "strengths",
            "weaknesses",
            "internal_comments",
        ],
        order_by="creation asc",
    )

    detailed_evaluations = []
    my_existing_evaluation = None

    for ev in eval_docs:
        if (ev.interviewer_user or "").lower() == user_lower or (ev.interviewer_email or "").lower() == user_lower:
            my_existing_evaluation = ev.name

        criteria_rows = frappe.get_all(
            "Xavirgin Evaluation Score",
            filters={"parent": ev.name},
            fields=["criterion_name", "category", "score_obtained", "max_marks", "weightage", "guidelines"],
            order_by="idx asc",
        )
        max_m = float(ev.max_possible_score or sum(float(c.max_marks or 0) for c in criteria_rows) or 10.0)
        tot_s = float(ev.total_score or 0)
        pct = round((tot_s / max_m) * 100.0, 1) if max_m > 0 else 0.0

        detailed_evaluations.append({
            "name": ev.name,
            "status": "Submitted" if ev.docstatus == 1 else "Draft",
            "interviewer_name": ev.interviewer_name or ev.interviewer_user,
            "interviewer_email": ev.interviewer_email,
            "evaluation_date": formatdate(ev.evaluation_date, "dd MMM yyyy") if ev.evaluation_date else "-",
            "total_score": tot_s,
            "max_possible_score": max_m,
            "percentage": pct,
            "recommendation": ev.recommendation or "Pending",
            "strengths": ev.strengths or "",
            "weaknesses": ev.weaknesses or "",
            "internal_comments": ev.internal_comments if (can_manage or is_panel_member) else "",
            "criteria": criteria_rows,
        })

    # Template max marks
    template_max_marks = 10.0
    if int_doc.assessment_template and frappe.db.exists("Xavirgin Assessment Template", int_doc.assessment_template):
        template_max_marks = float(
            frappe.db.get_value("Xavirgin Assessment Template", int_doc.assessment_template, "total_max_marks") or 10.0
        )

    return {
        "can_manage": can_manage,
        "is_panel_member": is_panel_member,
        "my_existing_evaluation": my_existing_evaluation,
        "formatted_date": formatdate(int_doc.interview_date, "dd MMMM yyyy") if int_doc.interview_date else "-",
        "formatted_start_12h": format_12h(int_doc.start_time),
        "formatted_end_12h": format_12h(int_doc.end_time),
        "template_max_marks": template_max_marks,
        "candidate": cand_data,
        "candidate_documents": cand_docs,
        "candidate_history": cand_history,
        "other_interviews": other_interviews,
        "offer_letters": offer_letters,
        "evaluations": detailed_evaluations,
    }


@frappe.whitelist()
def get_interview_kanban_dashboard(department: str = None, status_filter: str = None, search_text: str = None):
    """Returns structured data for the Interview & Recruitment Kanban/Card Dashboard:
    - Today's Interviews (In Progress, Upcoming Today, Completed Today)
    - Upcoming Future Interviews (chronological)
    - Pipeline Candidates (active recruitment stages)
    - Completed Recruitment Outcomes (strictly Hired & Rejected)
    - Department-Wise Recruitment Summary
    """
    today_date = getdate(today())
    can_manage = is_hr_or_admin_user(frappe.session.user)

    int_filters = {}
    if department:
        int_filters["department"] = department
    if status_filter:
        int_filters["status"] = status_filter

    interviews = frappe.get_all(
        "Xavirgin Interview",
        filters=int_filters,
        fields=[
            "name",
            "candidate",
            "candidate_name",
            "candidate_email",
            "candidate_phone",
            "job_opening",
            "department",
            "designation",
            "assessment_template",
            "interview_round",
            "status",
            "interview_date",
            "start_time",
            "end_time",
            "timezone",
            "meeting_platform",
            "meeting_url",
            "submitted_evaluations_count",
            "average_score",
            "consensus_recommendation",
        ],
        order_by="interview_date asc, start_time asc",
    )

    # Fetch all participant rows in a single batch query
    int_names = [i.name for i in interviews]
    participants_by_int = {}
    if int_names:
        part_rows = frappe.get_all(
            "Xavirgin Interview Participant",
            filters={"parent": ["in", int_names]},
            fields=["parent", "full_name", "email", "interview_role", "evaluation_status", "evaluation_score"],
            order_by="idx asc",
        )
        for pr in part_rows:
            participants_by_int.setdefault(pr.parent, []).append(pr)

    # Fetch template max marks in batch
    templates = {i.assessment_template for i in interviews if i.assessment_template}
    template_max_map = {}
    if templates:
        for t in frappe.get_all(
            "Xavirgin Assessment Template",
            filters={"name": ["in", list(templates)]},
            fields=["name", "total_max_marks"],
        ):
            template_max_map[t.name] = float(t.total_max_marks or 10.0)

    # Fetch Candidates for Pipeline vs Completed (Hired / Rejected)
    cand_filters = {}
    if department:
        cand_filters["department"] = department

    candidates = frappe.get_all(
        "Xavirgin Candidate",
        filters=cand_filters,
        fields=[
            "name",
            "full_name",
            "email",
            "phone",
            "job_opening",
            "department",
            "designation",
            "pipeline_stage",
            "latest_interview",
            "average_evaluation_score",
            "overall_recommendation",
            "employee",
            "creation",
        ],
        order_by="modified desc",
    )
    cand_map = {c.name: c for c in candidates}

    todays_interviews = []
    upcoming_interviews = []
    past_interviews = []

    search_q = (search_text or "").strip().lower()

    for iv in interviews:
        if search_q:
            haystack = f"{iv.name} {iv.candidate_name or ''} {iv.candidate or ''} {iv.department or ''} {iv.designation or ''} {iv.interview_round or ''}".lower()
            if search_q not in haystack:
                continue

        panel = participants_by_int.get(iv.name, [])
        cand_obj = cand_map.get(iv.candidate, {})
        max_marks = template_max_map.get(iv.assessment_template, 10.0)
        iv_date = getdate(iv.interview_date) if iv.interview_date else today_date

        card = {
            "name": iv.name,
            "candidate": iv.candidate,
            "candidate_name": iv.candidate_name or cand_obj.get("full_name") or iv.candidate,
            "candidate_stage": cand_obj.get("pipeline_stage") or "Interview Scheduled",
            "department": iv.department or cand_obj.get("department") or "Unassigned Department",
            "designation": iv.designation or cand_obj.get("designation") or "Intern / Candidate",
            "job_opening": iv.job_opening,
            "interview_round": iv.interview_round,
            "status": iv.status,
            "interview_date": str(iv_date),
            "formatted_date": formatdate(iv_date, "dd MMM yyyy"),
            "start_time_24h": str(iv.start_time or ""),
            "end_time_24h": str(iv.end_time or ""),
            "formatted_time_12h": f"{format_12h(iv.start_time)} – {format_12h(iv.end_time)}",
            "meeting_platform": iv.meeting_platform or "Google Meet",
            "meeting_url": iv.meeting_url or "",
            "panel": [
                {
                    "full_name": p.full_name,
                    "role": p.interview_role,
                    "eval_status": p.evaluation_status,
                    "score": p.evaluation_score,
                }
                for p in panel
            ],
            "panel_count": len(panel),
            "submitted_evals": int(iv.submitted_evaluations_count or 0),
            "average_score": float(iv.average_score or 0),
            "max_marks": max_marks,
            "consensus": iv.consensus_recommendation or "",
        }

        if iv_date == today_date:
            todays_interviews.append(card)
        elif iv_date > today_date and iv.status in ("Scheduled", "Rescheduled", "In Progress"):
            upcoming_interviews.append(card)
        else:
            past_interviews.append(card)

    # Sort Today's interviews: In Progress first, then Scheduled/Rescheduled, then Completed
    status_priority = {"In Progress": 0, "Scheduled": 1, "Rescheduled": 1, "Completed": 2, "No Show": 3, "Cancelled": 4}
    todays_interviews.sort(key=lambda x: (status_priority.get(x["status"], 5), x["start_time_24h"]))
    upcoming_interviews.sort(key=lambda x: (x["interview_date"], x["start_time_24h"]))

    # Separate Pipeline vs Completed Candidates (Completed = strictly Hired or Rejected)
    COMPLETED_OUTCOMES = {"Hired", "Rejected", "Offer Rejected", "Withdrawn"}
    pipeline_candidates = []
    completed_candidates = []
    dept_summary = {}

    for c in candidates:
        if search_q:
            chay = f"{c.name} {c.full_name or ''} {c.department or ''} {c.designation or ''} {c.pipeline_stage or ''}".lower()
            if search_q not in chay:
                continue

        stage = c.pipeline_stage or "New Application"
        dept_name = c.department or "Unassigned Department"
        d_bucket = dept_summary.setdefault(dept_name, {
            "department": dept_name,
            "today_interviews": 0,
            "upcoming_interviews": 0,
            "pipeline_count": 0,
            "completed_count": 0,
            "hired_count": 0,
            "rejected_count": 0,
            "candidates": [],
        })

        c_card = {
            "candidate": c.name,
            "full_name": c.full_name,
            "email": c.email,
            "department": dept_name,
            "designation": c.designation or "Applicant",
            "pipeline_stage": stage,
            "latest_interview": c.latest_interview,
            "average_score": float(c.average_evaluation_score or 0),
            "recommendation": c.overall_recommendation or "",
            "employee": c.employee,
            "applied_on": formatdate(c.creation, "dd MMM yyyy") if c.creation else "-",
        }

        if stage in ("Hired", "Rejected"):
            completed_candidates.append(c_card)
            d_bucket["completed_count"] += 1
            if stage == "Hired":
                d_bucket["hired_count"] += 1
            else:
                d_bucket["rejected_count"] += 1
        elif stage not in COMPLETED_OUTCOMES:
            pipeline_candidates.append(c_card)
            d_bucket["pipeline_count"] += 1

        d_bucket["candidates"].append(c_card)

    for ti in todays_interviews:
        d_b = dept_summary.setdefault(ti["department"], {
            "department": ti["department"],
            "today_interviews": 0,
            "upcoming_interviews": 0,
            "pipeline_count": 0,
            "completed_count": 0,
            "hired_count": 0,
            "rejected_count": 0,
            "candidates": [],
        })
        d_b["today_interviews"] += 1

    for ui in upcoming_interviews:
        d_b = dept_summary.setdefault(ui["department"], {
            "department": ui["department"],
            "today_interviews": 0,
            "upcoming_interviews": 0,
            "pipeline_count": 0,
            "completed_count": 0,
            "hired_count": 0,
            "rejected_count": 0,
            "candidates": [],
        })
        d_b["upcoming_interviews"] += 1

    all_depts = frappe.get_all("Department", pluck="name")

    return {
        "today_date": formatdate(today_date, "dd MMM yyyy"),
        "can_manage": can_manage,
        "all_departments": sorted(all_depts),
        "counts": {
            "today_total": len(todays_interviews),
            "today_in_progress": sum(1 for x in todays_interviews if x["status"] == "In Progress"),
            "upcoming_total": len(upcoming_interviews),
            "pipeline_total": len(pipeline_candidates),
            "completed_total": len(completed_candidates),
            "hired_total": sum(1 for x in completed_candidates if x["pipeline_stage"] == "Hired"),
            "rejected_total": sum(1 for x in completed_candidates if x["pipeline_stage"] == "Rejected"),
        },
        "todays_interviews": todays_interviews,
        "upcoming_interviews": upcoming_interviews,
        "pipeline_candidates": pipeline_candidates,
        "completed_candidates": completed_candidates,
        "departments": sorted(dept_summary.values(), key=lambda d: d["department"]),
    }


# ==============================================================================
# Module-Level Permission Hooks (Organization-Wide Visibility + Strict CRUD)
# ==============================================================================

def get_permission_query_conditions(user: str = None) -> str:
    """Allows all authenticated organizational users to view the Interview dashboard and schedules."""
    user = user or frappe.session.user
    if user == "Guest":
        return "1=0"
    return ""


def has_permission(doc, ptype="read", user=None, debug=False) -> bool:
    """Separates organization-wide read visibility from write/create/delete permissions:
    - Read / Select / Print: Allowed for all authenticated internal users.
    - Write / Create / Delete: Restricted strictly to System Manager, HR Admin, HR Manager, and Recruiter.
    """
    user = user or frappe.session.user
    if user == "Guest":
        return False

    if is_hr_or_admin_user(user):
        return True

    if ptype in ("read", "select", "print", "report"):
        return True

    return False