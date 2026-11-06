import frappe
from frappe import _
from frappe.model.document import Document


class XavirginEvaluationScore(Document):
    def validate(self):
        score = float(self.score_obtained or 0)
        max_m = float(self.max_marks or 0)

        # Fallback to parent template criterion if max_marks is unset
        if max_m <= 0:
            max_m = 10.0
            self.max_marks = max_m

        if score < 0:
            frappe.throw(_("Score for '{0}' cannot be negative.").format(self.criterion_name))
        if score > max_m:
            frappe.throw(
                _("Score for '{0}' ({1}) cannot exceed Maximum Marks ({2}).").format(
                    self.criterion_name, score, max_m
                )
            )