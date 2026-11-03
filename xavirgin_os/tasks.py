import frappe
from frappe.utils import add_days, getdate, now_datetime, time_diff_in_hours


def auto_close_abandoned_attendance_sessions():
	"""Nightly scheduler: Closes active 'Working' sessions older than 14 hours as Auto-Closed."""
	cutoff_time = now_datetime()
	abandoned = frappe.get_all(
		"Xavirgin Attendance Session",
		filters={"status": "Working"},
		fields=["name", "check_in"],
	)

	for s in abandoned:
		hours = time_diff_in_hours(cutoff_time, s.check_in)
		if hours >= 14:
			doc = frappe.get_doc("Xavirgin Attendance Session", s.name)
			doc.status = "Auto-Closed"
			doc.check_out = cutoff_time
			doc.worked_hours = 0.0
			doc.correction_remarks = "System auto-closed unstopped session after 14 hours."
			doc.save(ignore_permissions=True)


def expire_overdue_offer_letters():
	"""Nightly scheduler: Flags offer letters past their acceptance deadline as Expired."""
	today_date = getdate(frappe.utils.today())
	overdue = frappe.get_all(
		"Xavirgin Offer Letter",
		filters={
			"workflow_state": "Sent",
			"acceptance_deadline": ["<", today_date],
			"docstatus": 1,
		},
		pluck="name",
	)

	for name in overdue:
		doc = frappe.get_doc("Xavirgin Offer Letter", name)
		doc.db_set("workflow_state", "Expired", update_modified=False)
		if doc.candidate:
			frappe.db.set_value("Xavirgin Candidate", doc.candidate, "pipeline_stage", "Withdrawn", update_modified=False)