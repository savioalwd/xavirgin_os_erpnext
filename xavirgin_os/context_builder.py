import json
import frappe
from frappe.utils import getdate, today
from xavirgin_os.company_state import get_current_company_state_dict, get_verified_erpnext_financials


def build_operational_context(start_date: str = None, end_date: str = None, category: str = "Daily Operational Analysis") -> dict:
    """Builds a structured, token-efficient payload representing the requested period."""
    s_date = getdate(start_date or today())
    e_date = getdate(end_date or today())

    # Layer 1: Persistent Company State
    company_state = get_current_company_state_dict()

    # Layer 2: Attendance & Worked Hours
    attendances = frappe.get_all(
        "Xavirgin Attendance Session",
        filters={"attendance_date": ["between", [s_date, e_date]]},
        fields=["employee", "employee_name", "worked_hours", "status", "day_classification", "attendance_date"],
        limit=200
    )

    # Layer 3: Daily POAs & Blockers
    poas = frappe.get_all(
        "Xavirgin Daily POA",
        filters={"poa_date": ["between", [s_date, e_date]]},
        fields=["name", "employee_name", "department", "status", "total_actual_hours", "completed_tasks_count", "blocked_tasks_count", "blockers_summary", "poa_date"],
        limit=200
    )

    poa_tasks = []
    if poas:
        poa_names = [p.name for p in poas]
        poa_tasks = frappe.get_all(
            "Xavirgin POA Task",
            filters={"parent": ["in", poa_names]},
            fields=["parent", "task_title", "task_type", "status", "actual_hours", "blocker_reason"],
            limit=500
        )

    # Layer 4: Engineering Telemetry
    github_logs = frappe.get_all(
        "Xavirgin GitHub Activity",
        filters={"activity_date": ["between", [s_date, e_date]]},
        fields=["employee_name", "github_username", "event_type", "action", "repository", "summary"],
        limit=300
    )

    # Layer 5: Talent & Lineage Pipelines (Fixed field name 'pipeline_stage')
    candidates = frappe.get_all(
        "Xavirgin Candidate",
        filters={"creation": ["between", [f"{s_date} 00:00:00", f"{e_date} 23:59:59"]]},
        fields=["name", "full_name", "job_opening", "pipeline_stage"],
        limit=50
    )

    # Layer 6: Recent Historical Insights
    recent_reports = frappe.get_all(
        "Xavirgin AI Summary Log",
        filters={"summary_date": ["<", s_date], "scope_type": "Organization - Path CEO"},
        fields=["summary_date", "did_company_move_forward", "biggest_risk", "most_important_action"],
        order_by="summary_date desc",
        limit=3
    )

    return {
        "period": {
            "start_date": str(s_date),
            "end_date": str(e_date),
            "is_single_day": s_date == e_date
        },
        "current_company_state": company_state,
        "verified_financials": get_verified_erpnext_financials(),
        "operational_records": {
            "attendances": attendances,
            "poas_summary": poas,
            "poa_task_details": poa_tasks,
            "github_engineering_events": github_logs,
            "candidate_pipeline_movements": candidates
        },
        "recent_historical_reports": recent_reports
    }