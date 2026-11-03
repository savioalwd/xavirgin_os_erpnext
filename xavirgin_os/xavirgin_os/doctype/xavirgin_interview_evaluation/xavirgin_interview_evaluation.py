import frappe
from frappe import _
from frappe.model.document import Document


class XavirginInterviewEvaluation(Document):
	def before_validate(self):
		if not self.interviewer_user:
			self.interviewer_user = frappe.session.user
		if not self.interviewer_email:
			self.interviewer_email = frappe.db.get_value("User", self.interviewer_user, "email") or self.interviewer_user
		if not self.interviewer_name:
			self.interviewer_name = frappe.db.get_value("User", self.interviewer_user, "full_name") or self.interviewer_user

		if self.assessment_template and not self.scores:
			self.populate_criteria_from_template()

	def populate_criteria_from_template(self):
		template = frappe.get_doc("Xavirgin Assessment Template", self.assessment_template)
		self.scores = []
		for row in template.criteria:
			self.append("scores", {
				"criterion_name": row.criterion_name,
				"max_marks": row.max_marks,
				"score_obtained": 0.0,
			})

	def validate(self):
		self.validate_unique_interviewer_submission()
		self.calculate_totals()

	def validate_unique_interviewer_submission(self):
		"""Section 6.2: One interviewer must never overwrite another's evaluation or submit twice for the same interview."""
		existing = frappe.db.get_value(
			"Xavirgin Interview Evaluation",
			{
				"interview": self.interview,
				"interviewer_email": self.interviewer_email,
				"docstatus": ["!=", 2],
				"name": ["!=", self.name],
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("Interviewer {0} already has an evaluation ({1}) for Interview {2}.").format(
					self.interviewer_name, existing, self.interview
				)
			)

	def calculate_totals(self):
		total = 0.0
		max_total = 0.0
		for row in self.scores:
			score = float(row.score_obtained or 0)
			max_m = float(row.max_marks or 2)
			if score < 0 or score > max_m:
				frappe.throw(
					_("Score for '{0}' must be between 0 and {1}.").format(row.criterion_name, max_m)
				)
			total += score
			max_total += max_m
		self.total_score = round(total, 2)
		self.max_possible_score = round(max_total, 2)

	def on_submit(self):
		self.rollup_evaluation_scores()

	def on_cancel(self):
		self.rollup_evaluation_scores()

	def rollup_evaluation_scores(self):
		"""Compute average score across all submitted evaluations and update Interview & Candidate."""
		evals = frappe.get_all(
			"Xavirgin Interview Evaluation",
			filters={"interview": self.interview, "docstatus": 1},
			fields=["interviewer_email", "total_score", "recommendation"],
		)
		interview_doc = frappe.get_doc("Xavirgin Interview", self.interview)
		count = len(evals)
		avg_score = round(sum(e.total_score for e in evals) / count, 2) if count else 0.0

		# Update participant row status
		eval_by_email = {e.interviewer_email.lower(): e.total_score for e in evals if e.interviewer_email}
		for p in interview_doc.interviewers:
			p_email = (p.email or "").lower()
			if p_email in eval_by_email:
				p.evaluation_status = "Submitted"
				p.evaluation_score = eval_by_email[p_email]
				p.participation_status = "Attended"

		# Consensus recommendation based on average score
		consensus = ""
		if count > 0:
			if avg_score >= 8.5:
				consensus = "Strongly Recommended"
			elif avg_score >= 6.5:
				consensus = "Recommended"
			elif avg_score >= 5.0:
				consensus = "Hold"
			else:
				consensus = "Not Recommended"

		interview_doc.submitted_evaluations_count = count
		interview_doc.average_score = avg_score
		interview_doc.consensus_recommendation = consensus
		if count >= len(interview_doc.interviewers) and interview_doc.status == "Scheduled":
			interview_doc.status = "Completed"
		interview_doc.flags.ignore_permissions = True
		interview_doc.save()

		# Rollup across all interviews for the Candidate
		all_cand_evals = frappe.get_all(
			"Xavirgin Interview Evaluation",
			filters={"candidate": self.candidate, "docstatus": 1},
			fields=["total_score"],
		)
		cand_avg = (
			round(sum(e.total_score for e in all_cand_evals) / len(all_cand_evals), 2)
			if all_cand_evals
			else 0.0
		)
		frappe.db.set_value(
			"Xavirgin Candidate",
			self.candidate,
			{
				"average_evaluation_score": cand_avg,
				"overall_recommendation": consensus,
			},
			update_modified=False,
		)


@frappe.whitelist()
def fetch_template_criteria(assessment_template: str):
	if not assessment_template:
		return []
	doc = frappe.get_doc("Xavirgin Assessment Template", assessment_template)
	return [{"criterion_name": r.criterion_name, "max_marks": r.max_marks, "score_obtained": 0} for r in doc.criteria]


def get_permission_query_conditions(user: str) -> str:
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if roles.intersection({"System Manager", "Xavirgin HR Admin", "Xavirgin HR Manager", "Xavirgin Recruiter"}):
		return ""
	escaped = frappe.db.escape(user)
	return f"(`tabXavirgin Interview Evaluation`.interviewer_user = {escaped} OR `tabXavirgin Interview Evaluation`.owner = {escaped})"


def has_permission(doc, ptype="read", user=None) -> bool:
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if roles.intersection({"System Manager", "Xavirgin HR Admin", "Xavirgin HR Manager", "Xavirgin Recruiter"}):
		return True
	return doc.interviewer_user == user or doc.owner == user