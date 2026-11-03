import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate


class TestXavirginOSWorkflows(FrappeTestCase):
	def setUp(self):
		from xavirgin_os.install import after_install
		after_install()

		self.dept = frappe.db.get_value("Department", {}, "name")
		if not self.dept:
			self.dept = frappe.get_doc({"doctype": "Department", "department_name": "QA Track"}).insert().name

		self.desig = frappe.db.get_value("Designation", {}, "name")
		if not self.desig:
			self.desig = frappe.get_doc({"doctype": "Designation", "designation_name": "Software Tester Intern"}).insert().name

		self.director = frappe.db.get_value("Employee", {"employee_name": "Savio Babu"}, "name")
		if not self.director:
			company = frappe.db.get_value("Company", {}, "name")
			self.director = frappe.get_doc({
				"doctype": "Employee",
				"first_name": "Savio",
				"last_name": "Babu",
				"company": company,
				"gender": "Prefer not to say",
				"date_of_birth": "1997-05-10",
				"date_of_joining": "2025-11-17",
			}).insert().name

	def test_full_recruitment_to_employee_and_90_day_extension(self):
		# 1. Create Job Opening
		job = frappe.get_doc({
			"doctype": "Xavirgin Job Opening",
			"job_title": "Software Tester Intern Cohort",
			"department": self.dept,
			"designation": self.desig,
			"engagement_category": "Intern",
			"assessment_template": "Software Tester / QA",
			"number_of_vacancies": 5,
		}).insert()

		# 2. Create Candidate
		cand = frappe.get_doc({
			"doctype": "Xavirgin Candidate",
			"full_name": "Joshva Jashper Test",
			"email": "joshva.test@xavirgin.com",
			"phone": "+91 98765 43210",
			"job_opening": job.name,
		}).insert()

		# 3. Verify Duplicate Guard blocks re-application
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Xavirgin Candidate",
				"full_name": "Joshva Duplicate",
				"email": "joshva.test@xavirgin.com",
				"phone": "9876543210",
				"job_opening": job.name,
			}).insert()

		# 4. Create & Submit Offer Letter
		offer = frappe.get_doc({
			"doctype": "Xavirgin Offer Letter",
			"candidate": cand.name,
			"department": self.dept,
			"designation": self.desig,
			"skill_area": "Quality Assurance",
			"start_date": "2026-10-18",
			"reporting_manager": self.director,
		}).insert()
		offer.submit()
		offer.workflow_state = "Accepted"
		offer.documents_verified = 1
		offer.save()

		# 5. Atomic Conversion to Employee
		emp_id = offer.convert_to_employee()
		self.assertTrue(frappe.db.exists("Employee", emp_id))

		# Idempotency check: Calling convert_to_employee() a second time returns the exact same Employee ID
		self.assertEqual(offer.convert_to_employee(), emp_id)

		emp = frappe.get_doc("Employee", emp_id)
		self.assertEqual(emp.custom_source_candidate, cand.name)
		self.assertEqual(emp.custom_source_offer_letter, offer.name)
		initial_end = getdate(emp.custom_initial_internship_end_date)

		# 6. Approve 2 days of Casual Leave -> Verify custom_internship_end_date automatically extends
		leave = frappe.get_doc({
			"doctype": "Xavirgin Leave Request",
			"employee": emp_id,
			"leave_type": "Personal / Casual Leave",
			"from_date": "2026-11-04",
			"to_date": "2026-11-05",
			"reason": "University exam",
		}).insert()
		self.assertEqual(leave.status, "Approved")

		emp.reload()
		self.assertGreater(getdate(emp.custom_internship_end_date), initial_end)