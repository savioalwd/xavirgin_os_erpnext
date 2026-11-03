import frappe
from frappe import _
from frappe.model.document import Document


class XavirginEvaluationScore(Document):
	def validate(self):
		score = float(self.score_obtained or 0)
		max_m = float(self.max_marks or 2.0)
		if score < 0:
			frappe.throw(_("Score for '{0}' cannot be negative.").format(self.criterion_name))
		if score > max_m:
			frappe.throw(
				_("Score for '{0}' cannot exceed Maximum Marks ({1}).").format(self.criterion_name, max_m)
			)