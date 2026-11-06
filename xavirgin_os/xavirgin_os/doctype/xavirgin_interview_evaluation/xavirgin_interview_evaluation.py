import json
import frappe
from frappe import _
from frappe.model.document import Document
from xavirgin_os.ai import call_gemini
from xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session import (
    resolve_employee_context,
)


def is_hr_or_admin(user: str = None) -> bool:
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    roles = set(frappe.get_roles(user))
    return bool(roles.intersection({"System Manager", "Xavirgin HR Admin", "Xavirgin HR Manager", "Xavirgin Recruiter"}))


class XavirginInterviewEvaluation(Document):
    def before_validate(self):
        self.resolve_intelligent_evaluation_defaults()

    def validate(self):
        self.validate_interviewer_authorization()
        self.validate_unique_interviewer_submission()
        self.calculate_totals()

    def resolve_intelligent_evaluation_defaults(self):
        """Resolves interviewer details, candidate context, and scorecard rubrics."""
        if not self.interviewer_user:
            self.interviewer_user = frappe.session.user

        # 1. Resolve Evaluator Identity
        ctx = resolve_employee_context(employee=self.interviewer_employee, user_id=self.interviewer_user)
        if ctx and ctx.get("name"):
            self.interviewer_employee = ctx.get("name")
            self.interviewer_name = ctx.get("employee_name") or self.interviewer_name
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

        if self.interviewer_email:
            self.interviewer_email = self.interviewer_email.strip().lower()

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

        # 3. Populate criteria from template ONLY if scores table is empty (preserves historical criteria & custom adjustments)
        if self.assessment_template and not self.scores:
            self.populate_criteria_from_template()

    def populate_criteria_from_template(self):
        if not frappe.db.exists("Xavirgin Assessment Template", self.assessment_template):
            return
        template = frappe.get_doc("Xavirgin Assessment Template", self.assessment_template)
        self.scores = []
        for row in template.criteria:
            self.append("scores", {
                "criterion_name": row.criterion_name,
                "category": row.category or "Technical",
                "max_marks": float(row.max_marks or 0),
                "weightage": float(row.weightage or 1.0),
                "guidelines": row.description or "",
                "score_obtained": 0.0,
            })

    def validate_interviewer_authorization(self):
        """Verifies that non-HR users can only submit/modify evaluations for interviews they are assigned to."""
        if is_hr_or_admin():
            return

        if self.interviewer_user != frappe.session.user:
            frappe.throw(_("You can only submit or update an evaluation under your own user identity."), frappe.PermissionError)

        if self.interview and frappe.db.exists("Xavirgin Interview", self.interview):
            interview_doc = frappe.get_doc("Xavirgin Interview", self.interview)
            user_lower = (frappe.session.user or "").lower()
            email_lower = (self.interviewer_email or "").lower()
            is_panel_member = any(
                (p.interviewer_user and p.interviewer_user.lower() == user_lower)
                or (p.email and p.email.lower() in (user_lower, email_lower))
                or (self.interviewer_employee and p.employee == self.interviewer_employee)
                for p in interview_doc.interviewers
            )
            if not is_panel_member:
                frappe.throw(
                    _("Access Denied: You are not an assigned panel interviewer for Interview {0}.").format(self.interview),
                    frappe.PermissionError,
                )

    def validate_unique_interviewer_submission(self):
        """Ensures each interviewer submits their own independent evaluation without overwriting others."""
        existing = frappe.db.get_value(
            "Xavirgin Interview Evaluation",
            {
                "interview": self.interview,
                "interviewer_user": self.interviewer_user,
                "docstatus": ["!=", 2],
                "name": ["!=", self.name or ""],
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Interviewer {0} already has an active evaluation ({1}) for Interview {2}.").format(
                    self.interviewer_name or self.interviewer_user, existing, self.interview
                )
            )

    def calculate_totals(self):
        """Dynamically validates each criterion score against its configured max_marks and computes total & percentage."""
        total = 0.0
        max_total = 0.0
        for idx, row in enumerate(self.scores, start=1):
            max_m = float(row.max_marks or 0)
            if max_m <= 0:
                frappe.throw(_("Row #{0} ('{1}'): Maximum Marks must be greater than 0.").format(idx, row.criterion_name))
            score = float(row.score_obtained or 0)
            if score < 0 or score > max_m:
                frappe.throw(
                    _("Row #{0}: Score for '{1}' ({2}) must be between 0 and {3}.").format(
                        idx, row.criterion_name, score, max_m
                    )
                )
            total += score
            max_total += max_m

        self.total_score = round(total, 2)
        self.max_possible_score = round(max_total, 2)

        # Dynamic percentage-based recommendation
        if not self.recommendation and self.max_possible_score > 0 and self.total_score > 0:
            pct = (self.total_score / self.max_possible_score) * 100.0
            if pct >= 85.0:
                self.recommendation = "Strongly Recommended"
            elif pct >= 65.0:
                self.recommendation = "Recommended"
            elif pct >= 50.0:
                self.recommendation = "Hold"
            else:
                self.recommendation = "Not Recommended"

    def on_update(self):
        self.rollup_evaluation_scores()

    def on_submit(self):
        self.rollup_evaluation_scores()

    def on_cancel(self):
        self.rollup_evaluation_scores()

    def rollup_evaluation_scores(self):
        """Rolls up all individual interviewer evaluations to the Interview and Candidate records dynamically."""
        if not self.interview or not frappe.db.exists("Xavirgin Interview", self.interview):
            return

        evals = frappe.get_all(
            "Xavirgin Interview Evaluation",
            filters={"interview": self.interview, "docstatus": ["in", [0, 1]]},
            fields=[
                "name",
                "docstatus",
                "interviewer_user",
                "interviewer_employee",
                "interviewer_email",
                "total_score",
                "max_possible_score",
                "recommendation",
            ],
            order_by="docstatus desc, modified desc",
        )

        # Deduplicate per interviewer (prefer submitted over draft)
        eval_by_key = {}
        for ev in evals:
            keys = [
                (ev.interviewer_email or "").strip().lower(),
                (ev.interviewer_user or "").strip().lower(),
                (ev.interviewer_employee or "").strip(),
            ]
            for k in keys:
                if k and k not in eval_by_key:
                    eval_by_key[k] = ev

        # Submitted evaluations for official scoring rollup (or drafts if none submitted yet)
        submitted_evals = [e for e in evals if e.docstatus == 1]
        active_evals = submitted_evals if submitted_evals else evals

        interview_doc = frappe.get_doc("Xavirgin Interview", self.interview)
        count = len(active_evals)

        avg_score = round(sum(float(e.total_score or 0) for e in active_evals) / count, 2) if count else 0.0
        avg_pct = (
            sum(
                (float(e.total_score or 0) / float(e.max_possible_score)) * 100.0
                for e in active_evals
                if float(e.max_possible_score or 0) > 0
            )
            / count
            if count
            else 0.0
        )

        for p in interview_doc.interviewers:
            p_email = (p.email or "").strip().lower()
            p_user = (p.interviewer_user or "").strip().lower()
            p_emp = (p.employee or "").strip()
            matched_ev = eval_by_key.get(p_email) or eval_by_key.get(p_user) or eval_by_key.get(p_emp)
            if matched_ev:
                p.evaluation_status = "Submitted"
                p.evaluation_score = float(matched_ev.total_score or 0)
                p.participation_status = "Attended"

        consensus = ""
        if count > 0:
            if avg_pct >= 85.0:
                consensus = "Strongly Recommended"
            elif avg_pct >= 65.0:
                consensus = "Recommended"
            elif avg_pct >= 50.0:
                consensus = "Hold"
            else:
                consensus = "Not Recommended"

        interview_doc.submitted_evaluations_count = count
        interview_doc.average_score = avg_score
        interview_doc.consensus_recommendation = consensus
        if len(submitted_evals) >= len(interview_doc.interviewers) and len(interview_doc.interviewers) > 0:
            if interview_doc.status in ("Scheduled", "Rescheduled", "In Progress"):
                interview_doc.status = "Completed"

        interview_doc.flags.ignore_permissions = True
        interview_doc.flags.skip_schedule_notifications = True
        interview_doc.save()

        # Rollup across all interviews for Candidate
        if self.candidate and frappe.db.exists("Xavirgin Candidate", self.candidate):
            all_cand_evals = frappe.get_all(
                "Xavirgin Interview Evaluation",
                filters={"candidate": self.candidate, "docstatus": ["in", [0, 1]]},
                fields=["total_score"],
            )
            cand_avg = (
                round(sum(float(e.total_score or 0) for e in all_cand_evals) / len(all_cand_evals), 2)
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
            [
                f"- {s.criterion_name} ({s.category}): {s.score_obtained}/{s.max_marks} (Notes: {getattr(s, 'remarks', '') or 'N/A'})"
                for s in self.scores
            ]
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
    if not assessment_template or not frappe.db.exists("Xavirgin Assessment Template", assessment_template):
        return {"total_max_marks": 0.0, "criteria": []}
    doc = frappe.get_doc("Xavirgin Assessment Template", assessment_template)
    criteria = [
        {
            "criterion_name": r.criterion_name,
            "category": r.category or "Technical",
            "max_marks": float(r.max_marks or 0),
            "weightage": float(r.weightage or 1.0),
            "guidelines": r.description or "",
            "score_obtained": 0.0,
        }
        for r in doc.criteria
    ]
    total_max = round(sum(c["max_marks"] for c in criteria), 2)
    return {
        "total_max_marks": total_max,
        "target_total_marks": float(doc.target_total_marks or total_max),
        "criteria": criteria,
    }


def get_permission_query_conditions(user: str = None) -> str:
    """Allows all authenticated organization members to view evaluations; restricts Guests."""
    user = user or frappe.session.user
    if user == "Guest":
        return "1=0"
    return ""


def has_permission(doc, ptype="read", user=None, debug=False) -> bool:
    """Separates read visibility from write/submit authorization."""
    user = user or frappe.session.user
    if user == "Guest":
        return False

    if is_hr_or_admin(user):
        return True

    if ptype in ("read", "select", "print", "report"):
        return True

    if ptype == "delete":
        return False

    if isinstance(doc, str) or not doc:
        return True

    return getattr(doc, "interviewer_user", None) == user or getattr(doc, "owner", None) == user