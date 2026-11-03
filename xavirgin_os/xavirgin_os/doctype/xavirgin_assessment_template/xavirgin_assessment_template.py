import frappe
from frappe import _
from frappe.model.document import Document


class XavirginAssessmentTemplate(Document):
	def validate(self):
		self.total_max_marks = sum(float(row.max_marks or 0) for row in self.criteria)
		if round(self.total_max_marks, 2) != 10.0:
			frappe.msgprint(
				_("Note: Total marks across criteria is {0} (Standard Xavirgin rubric is 10.0 marks).").format(
					self.total_max_marks
				),
				indicator="orange",
			)