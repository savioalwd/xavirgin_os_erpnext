import frappe

no_cache = 1


def get_context(context):
    # If the user is logged in (not a Guest), redirect them straight into the ERP desk workspace
    if frappe.session.user and frappe.session.user != "Guest":
        frappe.local.flags.redirect_location = "/desk/xavirgin-os"
        raise frappe.Redirect

    context.no_cache = 1
    context.title = "Xavirgin OS — Autonomous Enterprise Systems & Engineering Residency"
    context.company_legal_name = "XAVIRGIN (OPC) PRIVATE LIMITED"
    context.cin = "U62090KL2025OPC098558"

    # Fetch count of open roles for live badge
    context.open_jobs_count = frappe.db.count(
        "Xavirgin Job Opening", {"status": "Open", "is_published": 1}
    )
    return context