import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, now_datetime


def calculate_working_end_date(start_date, active_days: int = 90):
	"""Calculate exact calendar date after N active working days (excluding Sundays)."""
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
		if not self.issue_date:
			self.issue_date = frappe.utils.today()
		if not self.acceptance_deadline:
			self.acceptance_deadline = add_days(self.issue_date, 2)
		if self.start_date and not self.end_date:
			days_req = int(self.active_working_days_required or 90)
			self.end_date = calculate_working_end_date(self.start_date, days_req)
		if self.amended_from and self.is_new():
			prev_ver = frappe.db.get_value("Xavirgin Offer Letter", self.amended_from, "offer_version") or 1
			self.offer_version = int(prev_ver) + 1

	def validate(self):
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
		"""Section 8.1: Render repaired 2-page Offer Letter & NDA PDF, attach to record, and email candidate."""
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
		"""
		Section 9.1 (Improvement #1): Transactional, Idempotent Candidate-to-Employee Conversion.
		Guarantees zero orphan records and full bidirectional foreign-key integrity.
		Locks user down to the Xavirgin OS workspace by applying module blocklists and the dedicated Role Profile.
		"""
		if self.docstatus != 1:
			frappe.throw(_("Offer Letter must be Submitted before converting to an Employee."))
		if self.workflow_state != "Accepted":
			frappe.throw(_("Offer status must be marked as 'Accepted' before onboarding."))
		if not self.documents_verified:
			frappe.throw(_("HR must verify the Signed Offer/NDA and ID Proof ('All Mandatory Documents Verified') before hiring."))

		# 1. Idempotency check: Return existing Employee if already converted
		existing_emp = frappe.db.get_value(
			"Employee",
			{"custom_source_candidate": self.candidate},
			"name",
		) or self.employee
		if existing_emp and frappe.db.exists("Employee", existing_emp):
			self.db_set("employee", existing_emp, update_modified=False)
			frappe.db.set_value("Xavirgin Candidate", self.candidate, {
				"employee": existing_emp,
				"pipeline_stage": "Hired",
			}, update_modified=False)
			return existing_emp

		cand = frappe.get_doc("Xavirgin Candidate", self.candidate)
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
		if not company:
			companies = frappe.get_all("Company", limit=1)
			company = companies[0].name if companies else None
		if not company:
			frappe.throw(_("No default Company found in ERPNext."))

		frappe.db.savepoint("xavirgin_hire_candidate")
		try:
			# 2. Provision or retrieve Frappe User account
			user_id = frappe.db.get_value("User", {"email": self.candidate_email}, "name")
			first_name, *rest = (self.candidate_name or "Intern").strip().split(" ")
			last_name = " ".join(rest) if rest else ""

			if not user_id:
				roles_to_assign = [{"role": "Employee"}]
				if self.engagement_category == "Intern":
					roles_to_assign.append({"role": "Xavirgin Intern"})
				if self.is_team_lead_role:
					roles_to_assign.append({"role": "Xavirgin Team Lead"})

				# Restrict user access: Hide all modules except Xavirgin OS
				all_modules = frappe.get_all("Module Def", pluck="name")
				blocked_modules = [{"module": m} for m in all_modules if m != "Xavirgin OS"]

				# send_welcome_email=0 suppresses generic Frappe template; User.after_insert hook in api.py handles branded notification
				user_doc = frappe.get_doc({
					"doctype": "User",
					"email": self.candidate_email,
					"first_name": first_name,
					"last_name": last_name,
					"enabled": 1,
					"send_welcome_email": 0,
					"role_profile_name": "Xavirgin Intern Profile" if self.engagement_category == "Intern" else None,
					"roles": roles_to_assign,
					"block_modules": blocked_modules,
				}).insert(ignore_permissions=True)
				user_id = user_doc.name

			# 3. Create ERPNext Core Employee Record with complete lineage
			settings = frappe.get_single("Xavirgin HR Settings")

			emp_doc = frappe.get_doc({
				"doctype": "Employee",
				"first_name": first_name,
				"last_name": last_name,
				"employee_name": self.candidate_name,
				"company": company,
				"status": "Active",
				"gender": "Prefer not to say",
				"date_of_birth": "2002-01-01",
				"date_of_joining": self.start_date,
				"department": self.department,
				"designation": self.designation,
				"reports_to": self.reporting_manager,
				"user_id": user_id,
				"company_email": self.candidate_email,
				"personal_email": self.candidate_email,
				"cell_number": self.candidate_phone,
				"current_address": self.candidate_address,
				"custom_employment_category": self.engagement_category,
				"custom_is_intern": 1 if self.engagement_category == "Intern" else 0,
				"custom_is_team_lead": 1 if self.is_team_lead_role else 0,
				"custom_team_lead": self.team_lead,
				"custom_github_username": cand.github_url,
				"custom_skill_area": self.skill_area,
				"custom_internship_start_date": self.start_date,
				"custom_initial_internship_end_date": self.end_date,
				"custom_internship_end_date": self.end_date,
				"custom_monthly_leave_limit": settings.monthly_general_leave_limit or 3,
				"custom_monthly_meeting_leave_limit": settings.monthly_meeting_leave_limit or 3,
				"custom_source_candidate": self.candidate,
				"custom_source_job_opening": self.job_opening,
				"custom_source_offer_letter": self.name,
				"custom_assigned_recruiter": cand.assigned_recruiter,
			})
			emp_doc.insert(ignore_permissions=True)

			# 4. Bidirectional Back-Linking & Immutable Audit Log
			self.db_set("employee", emp_doc.name, update_modified=False)
			cand.employee = emp_doc.name
			cand.converted_on = now_datetime()
			cand.pipeline_stage = "Hired"
			cand.append("stage_history", {
				"from_stage": "Offer Accepted",
				"to_stage": "Hired",
				"changed_by": frappe.session.user,
				"changed_on": now_datetime(),
				"remarks": f"Transactionally converted to Employee {emp_doc.name} via Offer {self.name}",
			})
			cand.save(ignore_permissions=True)

			return emp_doc.name

		except Exception as exc:
			frappe.db.rollback(save_point="xavirgin_hire_candidate")
			frappe.log_error(frappe.get_traceback(), "Xavirgin Candidate-to-Employee Conversion Failed")
			frappe.throw(_("Onboarding transaction rolled back cleanly to prevent partial records: {0}").format(str(exc)))