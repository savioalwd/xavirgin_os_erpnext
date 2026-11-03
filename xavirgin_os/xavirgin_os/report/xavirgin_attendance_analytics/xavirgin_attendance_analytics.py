import frappe
from frappe import _
from frappe.utils import get_first_day, get_last_day, today


def execute(filters=None):
	filters = filters or {}
	month_date = filters.get("month_date") or today()
	first_day = get_first_day(month_date)
	last_day = get_last_day(month_date)

	emp_filters = {"status": "Active"}
	if filters.get("department"):
		emp_filters["department"] = filters["department"]
	if filters.get("employment_category"):
		emp_filters["custom_employment_category"] = filters["employment_category"]

	order_by = "custom_xp_points desc, custom_total_worked_hours desc"
	limit = None
	view_mode = filters.get("leaderboard_mode")
	if view_mode == "Top 5 Performers":
		order_by = "custom_xp_points desc, custom_total_worked_hours desc"
		limit = 5
	elif view_mode == "Needs Improvement (Bottom 5)":
		order_by = "custom_xp_points asc, custom_total_worked_hours asc"
		limit = 5

	employees = frappe.get_all(
		"Employee",
		filters=emp_filters,
		fields=[
			"name",
			"employee_name",
			"department",
			"designation",
			"custom_employment_category",
			"custom_xp_points",
			"custom_streak_count",
			"custom_badge_level",
			"custom_active_days_completed",
			"custom_internship_end_date",
		],
		order_by=order_by,
		limit_page_length=limit,
	)

	columns = [
		{"fieldname": "employee", "label": _("Employee ID"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 150},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department", "width": 130},
		{"fieldname": "total_checkins", "label": _("Total Check-Ins"), "fieldtype": "Int", "width": 120},
		{"fieldname": "full_days", "label": _("Full Days (>=4h)"), "fieldtype": "Int", "width": 120},
		{"fieldname": "half_days", "label": _("Half Days (2-4h)"), "fieldtype": "Int", "width": 120},
		{"fieldname": "worked_hours", "label": _("Month Hours"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "meeting_present", "label": _("8PM Sync Present"), "fieldtype": "Int", "width": 130},
		{"fieldname": "meeting_leaves", "label": _("8PM Meeting Leaves"), "fieldtype": "Float", "width": 140},
		{"fieldname": "general_leaves", "label": _("Sick/Casual Leaves"), "fieldtype": "Float", "width": 140},
		{"fieldname": "active_days_90", "label": _("Active Days (/90)"), "fieldtype": "Int", "width": 130},
		{"fieldname": "extended_end_date", "label": _("Effective End Date"), "fieldtype": "Date", "width": 130},
		{"fieldname": "xp_points", "label": _("XP"), "fieldtype": "Int", "width": 90},
		{"fieldname": "badge_level", "label": _("Rank Tier"), "fieldtype": "Data", "width": 110},
	]

	data = []
	for emp in employees:
		att_rows = frappe.get_all(
			"Xavirgin Attendance Session",
			filters={
				"employee": emp.name,
				"attendance_date": ["between", [first_day, last_day]],
				"status": ["in", ["Completed", "Corrected"]],
			},
			fields=["attendance_date", "worked_hours"],
		)
		total_checkins = len(att_rows)
		month_hours = round(sum(float(r.worked_hours or 0) for r in att_rows), 2)

		hours_by_date = {}
		for r in att_rows:
			d_key = str(r.attendance_date)
			hours_by_date[d_key] = hours_by_date.get(d_key, 0.0) + float(r.worked_hours or 0)

		full_days = sum(1 for h in hours_by_date.values() if h >= 4.0)
		half_days = sum(1 for h in hours_by_date.values() if 2.0 <= h < 4.0)

		leave_rows = frappe.get_all(
			"Xavirgin Leave Request",
			filters={
				"employee": emp.name,
				"status": "Approved",
				"from_date": ["between", [first_day, last_day]],
			},
			fields=["leave_type", "leave_days"],
		)
		meeting_leaves = sum(float(l.leave_days or 0) for l in leave_rows if l.leave_type == "Mandatory Meeting Leave")
		general_leaves = sum(float(l.leave_days or 0) for l in leave_rows if l.leave_type != "Mandatory Meeting Leave")

		meeting_present = frappe.db.sql(
			"""
			SELECT COUNT(e.name)
			FROM `tabXavirgin Daily Meeting Entry` e
			INNER JOIN `tabXavirgin Daily Meeting Log` m ON m.name = e.parent
			WHERE e.employee = %s AND e.status = 'Present' AND m.meeting_date BETWEEN %s AND %s
			""",
			(emp.name, first_day, last_day),
		)[0][0] or 0

		data.append({
			"employee": emp.name,
			"employee_name": emp.employee_name,
			"department": emp.department,
			"total_checkins": total_checkins,
			"full_days": full_days,
			"half_days": half_days,
			"worked_hours": month_hours,
			"meeting_present": int(meeting_present),
			"meeting_leaves": meeting_leaves,
			"general_leaves": general_leaves,
			"active_days_90": emp.custom_active_days_completed or 0,
			"extended_end_date": emp.custom_internship_end_date,
			"xp_points": emp.custom_xp_points or 0,
			"badge_level": emp.custom_badge_level or "Bronze Tier",
		})

	return columns, data