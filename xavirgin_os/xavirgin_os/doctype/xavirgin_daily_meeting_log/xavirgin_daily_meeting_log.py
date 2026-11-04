import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate
from xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session import (
    resolve_employee_context,
)


class XavirginDailyMeetingLog(Document):
    def before_validate(self):
        self.resolve_intelligent_conductor_and_defaults()
        self.validate_unique_entries()

    def validate(self):
        self.validate_duplicate_meeting_log()
        self.calculate_aggregate_tallies()

    def resolve_intelligent_conductor_and_defaults(self):
        """Pulls conductor details from the logged-in session user and global HR settings."""
        if not self.conducted_by:
            self.conducted_by = frappe.session.user

        ctx = resolve_employee_context(user_id=self.conducted_by)
        if ctx:
            self.conductor_employee = ctx.get("name")
            self.conductor_name = ctx.get("employee_name")

        settings = frappe.get_single("Xavirgin HR Settings")
        if not self.sync_time:
            self.sync_time = settings.daily_team_sync_time or "20:00:00"
        if not self.meeting_url:
            self.meeting_url = settings.default_meet_link

    def validate_unique_entries(self):
        """Validates that no employee is added multiple times in the participant table."""
        seen_employees = set()
        for idx, row in enumerate(self.entries, start=1):
            if not row.employee:
                continue
            if row.employee in seen_employees:
                emp_name = row.employee_name or row.employee
                frappe.throw(
                    _("Row #{0}: Employee <b>{1} ({2})</b> is added multiple times. Each member can only appear once.").format(
                        idx, emp_name, row.employee
                    )
                )
            seen_employees.add(row.employee)

    def validate_duplicate_meeting_log(self):
        """Prevents duplicate sync logs for the same date and department."""
        filters = {
            "meeting_date": getdate(self.meeting_date),
            "name": ["!=", self.name or ""],
        }
        if self.department:
            filters["department"] = self.department
        else:
            filters["department"] = ["in", ["", None]]

        existing = frappe.db.get_value("Xavirgin Daily Meeting Log", filters, "name")
        if existing:
            dept_label = self.department or "All Departments"
            frappe.throw(
                _("A Daily Meeting Log ({0}) already exists for {1} on {2}.").format(
                    existing, dept_label, self.meeting_date
                )
            )

    def calculate_aggregate_tallies(self):
        """Recalculates roll call statistics."""
        self.total_participants = len(self.entries)
        self.present_count = sum(1 for r in self.entries if r.status == "Present")
        self.absent_count = sum(1 for r in self.entries if r.status == "Absent")
        self.excused_count = sum(1 for r in self.entries if r.status == "Excused (Approved Meeting Leave)")

    @frappe.whitelist()
    def populate_active_interns(self):
        """Populates all active members, checks approved meeting leaves, and defaults all to Present."""
        # Include all active employees/interns
        filters = {"status": "Active"}
        if self.department:
            filters["department"] = self.department

        employees = frappe.get_all(
            "Employee",
            filters=filters,
            fields=["name", "employee_name", "department", "designation"],
            order_by="department asc, employee_name asc",
        )

        if not employees:
            frappe.throw(_("No active team members found matching the selected criteria."))

        m_date = getdate(self.meeting_date or frappe.utils.today())

        # Check for approved mandatory meeting leaves on this date
        excused_employees = set(
            frappe.get_all(
                "Xavirgin Leave Request",
                filters={
                    "leave_type": "Mandatory Meeting Leave",
                    "status": "Approved",
                    "from_date": ["<=", m_date],
                    "to_date": [">=", m_date],
                },
                pluck="employee",
            )
        )

        # Pull completed/working attendance session hours logged today
        today_sessions = frappe.get_all(
            "Xavirgin Attendance Session",
            filters={
                "attendance_date": m_date,
                "status": ["in", ["Completed", "Corrected", "Working"]],
            },
            fields=["employee", "worked_hours"],
        )

        hours_by_emp = {}
        for sess in today_sessions:
            hours_by_emp[sess.employee] = hours_by_emp.get(sess.employee, 0.0) + float(sess.worked_hours or 0)

        self.entries = []
        for emp in employees:
            is_excused = emp.name in excused_employees
            logged_hours = round(hours_by_emp.get(emp.name, 0.0), 2)

            status = "Excused (Approved Meeting Leave)" if is_excused else "Present"
            remarks = "Approved Mandatory Meeting Leave" if is_excused else ""
            if not is_excused and logged_hours > 0:
                remarks = f"Logged {logged_hours}h prior to sync"

            self.append("entries", {
                "employee": emp.name,
                "employee_name": emp.employee_name,
                "department": emp.department,
                "designation": emp.designation,
                "status": status,
                "today_worked_hours": logged_hours,
                "remarks": remarks,
            })

        self.calculate_aggregate_tallies()
        if not self.is_new():
            self.save()
            
        return len(self.entries)