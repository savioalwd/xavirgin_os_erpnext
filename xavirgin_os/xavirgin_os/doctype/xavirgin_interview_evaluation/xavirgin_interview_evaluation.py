import frappe
from frappe import _
from frappe.model.document import Document
from xavirgin_os.ai import call_gemini
from xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session import (
	resolve_employee_context,
)


class XavirginInterviewEvaluation(Document):
	def before_validate(self):
		self.resolve_intelligent_evaluation_defaults()

	def validate(self):
		self.validate_unique_interviewer_submission()
		self.calculate_totals()

	def resolve_intelligent_evaluation_defaults(self):
		"""Resolves interviewer details, candidate context, and scorecard rubrics."""
		if not self.interviewer_user:
			self.interviewer_user = frappe.session.user

		# 1. Resolve Evaluator Identity
		ctx = resolve_employee_context(employee=self.interviewer_employee, user_id=self.interviewer_user)
		if ctx:
			self.interviewer_employee = ctx.get("name")
			self.interviewer_name = ctx.get("employee_name")
			self.interviewer_email = (
				frappe.db.get_value("Employee", self.interviewer_employee, "company_email")
				or frappe.db.get_value("Employee", self.interviewer_employee, "personal_email")
				or frappe.db.get_value("User", self.interviewer_user, "email")
				or self.interviewer_user
			)
		else:
			if not self.interviewer_name:
				self.interviewer_name = frappe.db.get_value("User", self.interviewer_user, "full_name") or self.interviewer_user
			if not self.interviewer_email:
				self.interviewer_email = frappe.db.get_value("User", self.interviewer_user, "email") or self.interviewer_user

		# 2. Sync from Interview parent doc if set
		if self.interview:
			int_doc = frappe.db.get_value(
				"Xavirgin Interview",
				self.interview,
				["candidate", "candidate_name", "job_opening", "assessment_template"],
				as_dict=True,
			)
			if int_doc:
				if not self.candidate:
					self.candidate = int_doc.candidate
				if not self.candidate_name:
					self.candidate_name = int_doc.candidate_name
				if not self.job_opening:
					self.job_opening = int_doc.job_opening
				if not self.assessment_template:
					self.assessment_template = int_doc.assessment_template

		# 3. Populate criteria from template if table is empty
		if self.assessment_template and not self.scores:
			self.populate_criteria_from_template()

	def populate_criteria_from_template(self):
		template = frappe.get_doc("Xavirgin Assessment Template", self.assessment_template)
		self.scores = []
		for row in template.criteria:
			self.append("scores", {
				"criterion_name": row.criterion_name,
				"category": row.category or "Technical",
				"max_marks": row.max_marks or 2.0,
				"weightage": row.weightage or 1.0,
				"guidelines": row.description or "",
				"score_obtained": 0.0,
			})

	def validate_unique_interviewer_submission(self):
		"""Ensures an interviewer submits only one official evaluation per interview session."""
		existing = frappe.db.get_value(
			"Xavirgin Interview Evaluation",
			{
				"interview": self.interview,
				"interviewer_email": self.interviewer_email,
				"docstatus": ["!=", 2],
				"name": ["!=", self.name or ""],
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("Interviewer {0} has already submitted an evaluation ({1}) for Interview {2}.").format(
					self.interviewer_name, existing, self.interview
				)
			)

	def calculate_totals(self):
		total = 0.0
		max_total = 0.0
		for row in self.scores:
			score = float(row.score_obtained or 0)
			max_m = float(row.max_marks or 2.0)
			if score < 0 or score > max_m:
				frappe.throw(
					_("Score for '{0}' must be between 0 and {1}.").format(row.criterion_name, max_m)
				)
			total += score
			max_total += max_m
		self.total_score = round(total, 2)
		self.max_possible_score = round(max_total, 2)

		# Auto-recommendation guidance
		if not self.recommendation and self.total_score > 0:
			pct = (self.total_score / (self.max_possible_score or 10.0)) * 100
			if pct >= 85:
				self.recommendation = "Strongly Recommended"
			elif pct >= 65:
				self.recommendation = "Recommended"
			elif pct >= 50:
				self.recommendation = "Hold"
			else:
				self.recommendation = "Not Recommended"

	def on_submit(self):
		self.rollup_evaluation_scores()

	def on_cancel(self):
		self.rollup_evaluation_scores()

	def rollup_evaluation_scores(self):
		"""Computes average score across all submitted evaluations and rolls up to Interview & Candidate."""
		evals = frappe.get_all(
			"Xavirgin Interview Evaluation",
			filters={"interview": self.interview, "docstatus": 1},
			fields=["interviewer_email", "total_score", "recommendation"],
		)
		interview_doc = frappe.get_doc("Xavirgin Interview", self.interview)
		count = len(evals)
		avg_score = round(sum(e.total_score for e in evals) / count, 2) if count else 0.0

		# Update interview participant table row
		eval_by_email = {e.interviewer_email.lower(): e.total_score for e in evals if e.interviewer_email}
		for p in interview_doc.interviewers:
			p_email = (p.email or "").lower()
			if p_email in eval_by_email:
				p.evaluation_status = "Submitted"
				p.evaluation_score = eval_by_email[p_email]
				p.participation_status = "Attended"

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

		# Rollup across all interviews for Candidate
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
	def generate_ai_evaluation_summary(self):
		"""Uses central Gemini AI helper to generate objective strengths and weaknesses based on criteria scores."""
		scores_summary = "\n".join(
			[f"- {s.criterion_name} ({s.category}): {s.score_obtained}/{s.max_marks} (Notes: {s.remarks or 'N/A'})" for s in self.scores]
		)

		prompt = f"""
		Candidate: {self.candidate_name}
		Job Opening: {self.job_opening}
		Total Score: {self.total_score} / {self.max_possible_score}

		CRITERION SCORES:
		{scores_summary}

		TASK:
		Based on the quantitative marks awarded, generate:
		1. STRENGTHS: 2-3 concise, bulleted technical strengths.
		2. WEAKNESSES: 2-3 constructive areas where the candidate needs improvement.
		3. RECOMMENDED VERDICT: Strongly Recommended, Recommended, Hold, or Not Recommended.

		OUTPUT FORMAT (strict JSON only, no markdown codeblocks):
		{{"strengths": "...", "weaknesses": "...", "verdict": "..."}}
		"""

		result = call_gemini(
			prompt=prompt,
			system_instruction="You are an expert technical interviewer and talent assessor.",
			temperature=0.2,
		)

		clean_json = result.strip()
		if clean_json.startswith("```"):
			clean_json = clean_json.split("\n", 1)[1]
			if clean_json.endswith("```"):
				clean_json = clean_json.rsplit("```", 1)[0]
		clean_json = clean_json.strip()

		try:
			import json
			parsed = json.loads(clean_json)
			self.strengths = parsed.get("strengths", "")
			self.weaknesses = parsed.get("weaknesses", "")
			if not self.recommendation and parsed.get("verdict"):
				self.recommendation = parsed.get("verdict")
			return parsed
		except Exception:
			self.strengths = result
			return {"strengths": result}


@frappe.whitelist()
def fetch_template_criteria(assessment_template: str):
	if not assessment_template:
		return []
	doc = frappe.get_doc("Xavirgin Assessment Template", assessment_template)
	return [
		{
			"criterion_name": r.criterion_name,
			"category": r.category or "Technical",
			"max_marks": r.max_marks or 2.0,
			"weightage": r.weightage or 1.0,
			"guidelines": r.description or "",
			"score_obtained": 0.0,
		}
		for r in doc.criteria
	]


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