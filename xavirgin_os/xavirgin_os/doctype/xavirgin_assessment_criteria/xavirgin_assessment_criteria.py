from frappe.model.document import Document


class XavirginAssessmentCriteria(Document):
	def validate(self):
		if float(self.max_marks or 0) <= 0:
			self.max_marks = 2.0
		if float(self.weightage or 0) <= 0:
			self.weightage = 1.0