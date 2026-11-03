import frappe
from frappe.model.document import Document
from frappe import _
from xavirgin_os.ai import generate_organization_path_insight


class XavirginAISummaryLog(Document):
    def before_trash(self):
        # Unlink or handle dependent company state history references if needed
        histories = frappe.get_all("Xavirgin Company State History", filters={"source_summary_log": self.name}, fields=["name"])
        for h in histories:
            frappe.db.set_value("Xavirgin Company State History", h.name, "source_summary_log", None)


@frappe.whitelist()
def trigger_organization_path_insight(target_date: str = None):
    """Manual desk button trigger to generate a new versioned Path CEO Insight record."""
    doc = generate_organization_path_insight(target_date=target_date)
    return doc.name