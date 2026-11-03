import frappe
from frappe.model.document import Document
from xavirgin_os.ai import generate_organization_path_insight


class XavirginAISummaryLog(Document):
	pass


@frappe.whitelist()
def trigger_organization_path_insight(target_date: str = None):
	"""Manual desk button trigger to generate a new versioned Path CEO Insight record."""
	doc = generate_organization_path_insight(target_date=target_date)
	return doc.name