import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, format_time, formatdate, now_datetime
from xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session import (
	resolve_employee_context,
)


class XavirginInterview(Document):
	def before_validate(self):
		self.resolve_intelligent_interview_defaults()

	def validate(self):
		self.resolve_and_validate_participants()

	def resolve_intelligent_interview_defaults(self):
		"""Intelligently pulls defaults from Candidate, Job Opening, and Global HR Settings."""
		settings = frappe.get_single("Xavirgin HR Settings")

		# 1. Fallback meeting settings
		if not self.meeting_url:
			self.meeting_url = settings.default_meet_link or "https://meet.google.com/xzx-icxk-uje"
		if not self.meeting_platform:
			self.meeting_platform = settings.default_meeting_platform or "Google Meet"

		# 2. Timing defaults: Default to today, +1 hour if not specified
		if not self.interview_date:
			self.interview_date = frappe.utils.today()
		if not self.start_time:
			now_time = now_datetime()
			self.start_time = now_time.strftime("%H:%M:%S")
		if not self.end_time and self.start_time:
			duration = int(settings.default_meeting_duration_mins or 40)
			# Calculate end_time
			start_dt = frappe.utils.to_timedelta(self.start_time)
			end_dt = start_dt + frappe.utils.to_timedelta(f"00:{duration}:00")
			self.end_time = str(end_dt)

		# 3. Cascade Assessment Template from Candidate -> Job Opening -> Designation
		if not self.assessment_template:
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

			if self.job_opening:
				self.assessment_template = frappe.db.get_value(
					"Xavirgin Job Opening", self.job_opening, "assessment_template"
				)

			if not self.assessment_template and self.designation:
				self.assessment_template = frappe.db.get_value(
					"Xavirgin Assessment Template",
					{"template_name": ["like", f"%{self.designation}%"], "is_active": 1},
					"name",
				)

	def resolve_and_validate_participants(self):
		"""Ensures interviewer details are populated bidirectionally and deduplicated."""
		seen_emails = set()
		for row in self.interviewers:
			# Auto-resolve identity via centralized helper
			if row.employee or row.interviewer_user or row.email:
				ctx = resolve_employee_context(employee=row.employee, user_id=row.interviewer_user)
				if ctx:
					row.employee = ctx.get("name")
					row.full_name = ctx.get("employee_name") or row.full_name
					row.interviewer_user = frappe.db.get_value("Employee", row.employee, "user_id") or row.interviewer_user
					row.email = (
						frappe.db.get_value("Employee", row.employee, "company_email")
						or frappe.db.get_value("Employee", row.employee, "personal_email")
						or row.email
					)
					row.designation = ctx.get("designation") or row.designation
					row.department = ctx.get("department") or row.department

			clean_email = (row.email or "").strip().lower()
			if clean_email:
				if clean_email in seen_emails:
					frappe.throw(_("Duplicate interviewer '{0}' found in the panel.").format(row.email))
				seen_emails.add(clean_email)

	def on_update(self):
		self.sync_candidate_stage()
		self.notify_assigned_interviewers()

	def sync_candidate_stage(self):
		if not self.candidate:
			return
		cand = frappe.get_doc("Xavirgin Candidate", self.candidate)
		cand.latest_interview = self.name
		if self.status == "Scheduled" and cand.pipeline_stage in ("New Application", "Initial Screening", "Shortlisted"):
			cand.pipeline_stage = "Interview Scheduled"
			cand.save(ignore_permissions=True)
		elif self.status == "Completed" and cand.pipeline_stage == "Interview Scheduled":
			cand.pipeline_stage = "Interview Completed"
			cand.save(ignore_permissions=True)
		else:
			cand.db_set("latest_interview", self.name, update_modified=False)

	def notify_assigned_interviewers(self):
		"""Dispatches email & system alerts to panel members upon assignment."""
		settings = frappe.get_single("Xavirgin HR Settings")
		formatted_date = formatdate(self.interview_date, "dd MMMM yyyy")
		formatted_start = format_time(self.start_time)
		formatted_end = format_time(self.end_time)

		for row in self.interviewers:
			if row.notification_sent:
				continue

			if settings.send_interviewer_email_notifications and row.email:
				frappe.sendmail(
					recipients=[row.email],
					subject=f"📋 Interview Panel Assignment: {self.candidate_name} ({self.interview_round})",
					message=f"""
					<div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
						<h3 style="color: #0000FF; margin-top: 0;">🧬 Xavirgin Interview Assignment</h3>
						<p>Hello <strong>{row.full_name}</strong>,</p>
						<p>You have been scheduled as <strong>{row.interview_role}</strong> for the upcoming candidate evaluation:</p>
						<ul>
							<li><strong>Candidate:</strong> {self.candidate_name} ({self.candidate})</li>
							<li><strong>Round:</strong> {self.interview_round}</li>
							<li><strong>Date:</strong> {formatted_date}</li>
							<li><strong>Time:</strong> {formatted_start} – {formatted_end} ({self.timezone})</li>
							<li><strong>Meeting Link:</strong> <a href="{self.meeting_url}">{self.meeting_url}</a></li>
						</ul>
						<p>Please review their profile and prepare to submit your scorecard in Xavirgin OS immediately after the interview.</p>
					</div>
					""",
					delayed=False,
				)

			if settings.send_interviewer_system_notifications and row.interviewer_user:
				frappe.get_doc({
					"doctype": "Notification Log",
					"subject": f"Interview Assigned: {self.candidate_name} on {formatted_date} at {formatted_start}",
					"for_user": row.interviewer_user,
					"type": "Alert",
					"document_type": "Xavirgin Interview",
					"document_name": self.name,
				}).insert(ignore_permissions=True)

			row.db_set("notification_sent", 1, update_modified=False)

	@frappe.whitelist()
	def send_candidate_interview_invitation(self):
		"""Dispatches interview invitation to candidate with explicit scheduling terms."""
		if not self.interview_date or not self.start_time:
			frappe.throw(_("Please specify Interview Date and Start Time."))
		if not self.candidate_email:
			frappe.throw(_("Candidate email is required."))

		job_title = (
			frappe.db.get_value("Xavirgin Job Opening", self.job_opening, "job_title")
			if self.job_opening
			else (self.designation or "Software Engineering Internship")
		)
		formatted_date = formatdate(self.interview_date, "dd MMMM yyyy")
		formatted_start = format_time(self.start_time)
		formatted_end = format_time(self.end_time)

		html_body = f"""
		<div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #2c3e50; background-color: #f4f6f9; padding: 25px;">
			<div style="max-width: 650px; margin: 0 auto; background: #ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08); border: 1px solid #e1e8ed;">
				<div style="background: linear-gradient(135deg, #0000FF 0%, #0033aa 100%); padding: 30px 25px; text-align: center; color: #ffffff;">
					<div style="font-weight: 800; font-size: 24px; letter-spacing: 1.5px; color: #ffffff;">🧬 XAVIRGIN</div>
					<p style="margin: 5px 0 0 0; font-size: 13px; opacity: 0.9; letter-spacing: 0.5px; color: #e2e8f0;">Smart Tech Solutions &amp; Software Development</p>
					<h2 style="font-size: 20px; margin-top: 15px; margin-bottom: 0; font-weight: 600; color: #ffffff;">Technical Interview Invitation</h2>
				</div>
				<div style="padding: 30px; background: #ffffff;">
					<p style="font-size: 16px; margin-top: 0; margin-bottom: 15px;">
						Hello <strong style="color: #0000FF;">{self.candidate_name}</strong>,
					</p>
					<p style="color: #4a5568; line-height: 1.7; font-size: 15px;">
						This is the HR Team from <strong>Xavirgin.com</strong>. We have reviewed your application for the <strong style="color: #0000FF;">{job_title}</strong> track.
					</p>
					<div style="background: #f0f4ff; border-left: 4px solid #0000FF; padding: 18px; margin: 20px 0; border-radius: 6px;">
						<h4 style="margin: 0 0 10px 0; color: #0000FF; font-size: 15px; font-weight: 700;">📅 Scheduled Interview Slot ({self.interview_round})</h4>
						<div style="font-size: 14px; line-height: 1.6; color: #2d3748;">
							<strong>Date:</strong> {formatted_date}<br/>
							<strong>Time:</strong> {formatted_start} – {formatted_end} ({self.timezone})
						</div>
						<div style="margin-top: 12px;">
							<a href="{self.meeting_url}" style="display: inline-block; padding: 10px 22px; background: #0000FF; color: #ffffff; text-decoration: none; border-radius: 5px; font-weight: 600; font-size: 14px;">
								🔗 Join {self.meeting_platform} →
							</a>
						</div>
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
					<p style="margin: 0; font-size: 15px; color: #0000FF; font-weight: 700;">HR Team</p>
					<p style="margin: 0; font-size: 13px; color: #718096; font-weight: 600;">XAVIRGIN (OPC) PRIVATE LIMITED</p>
				</div>
			</div>
		</div>
		"""

		frappe.sendmail(
			recipients=[self.candidate_email],
			subject=f"🧬 Technical Interview Invitation: {job_title} — Xavirgin",
			message=html_body,
			reference_doctype=self.doctype,
			reference_name=self.name,
			delayed=False,
		)
		self.db_set("candidate_invitation_sent", 1, update_modified=False)
		return _("Interview invitation emailed to {0}.").format(self.candidate_email)


def get_permission_query_conditions(user: str) -> str:
	if not user:
		user = frappe.session.user
	roles = set(frappe.get_roles(user))
	if roles.intersection({"System Manager", "Xavirgin HR Admin", "Xavirgin HR Manager", "Xavirgin Recruiter"}):
		return ""
	escaped_user = frappe.db.escape(user)
	return f"""`tabXavirgin Interview`.name IN (
		SELECT parent FROM `tabXavirgin Interview Participant`
		WHERE interviewer_user = {escaped_user} OR email = {escaped_user}
	)"""


def has_permission(doc, ptype="read", user=None) -> bool:
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if roles.intersection({"System Manager", "Xavirgin HR Admin", "Xavirgin HR Manager", "Xavirgin Recruiter"}):
		return True
	for row in doc.interviewers:
		if row.interviewer_user == user or (row.email and row.email.lower() == user.lower()):
			return ptype == "read"
	return False