import frappe
from frappe.utils import get_datetime, today


def auto_close_abandoned_attendance_sessions():
	"""Improvement #12: Nightly job to close abandoned 'Working' sessions without awarding unearned bonus XP."""
	open_sessions = frappe.get_all(
		"Xavirgin Attendance Session",
		filters={"status": "Working"},
		fields=["name", "check_in", "employee"],
	)
	for s in open_sessions:
		doc = frappe.get_doc("Xavirgin Attendance Session", s.name)
		doc.check_out = get_datetime(f"{doc.attendance_date} 23:59:00")
		doc.status = "Auto-Closed"
		doc.correction_remarks = "Auto-closed by nightly scheduler (User forgot to check out)."
		doc.save(ignore_permissions=True)
	frappe.db.commit()


def expire_overdue_offer_letters():
	"""Improvement #17: Expire 'Sent' Offer Letters that have passed their 2-day acceptance_deadline."""
	overdue = frappe.get_all(
		"Xavirgin Offer Letter",
		filters={
			"workflow_state": "Sent",
			"acceptance_deadline": ["<", today()],
			"docstatus": 1,
		},
		pluck="name",
	)
	for offer_name in overdue:
		doc = frappe.get_doc("Xavirgin Offer Letter", offer_name)
		doc.db_set("workflow_state", "Expired", update_modified=False)
		doc.sync_to_candidate()
	frappe.db.commit()