import json
import re
import requests
import frappe
from frappe import _
from frappe.utils import getdate, today, now_datetime, generate_hash
from xavirgin_os.company_state import (
    get_current_company_state_dict,
    get_verified_erpnext_financials,
    apply_proposed_state_updates
)
from xavirgin_os.context_builder import build_operational_context
from xavirgin_os.prompt_manager import get_active_prompt


def call_gemini(prompt: str, system_instruction: str = None, temperature: float = 0.7, timeout: int = 60, model_override: str = None) -> str:
    """Centralized caller for Gemini API with support for model overrides and robust response decoding."""
    settings = frappe.get_single("Xavirgin HR Settings")
    creds = settings.get_gemini_credentials()

    api_key = creds.get("api_key")
    if not api_key:
        frappe.throw(_("Gemini API Key is not configured in Xavirgin HR Settings."))

    model = model_override or creds.get("model") or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }

    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        res_data = response.json()

        if response.status_code != 200:
            error_msg = res_data.get("error", {}).get("message", response.text)
            frappe.throw(_("Gemini API Error ({0}): {1}").format(response.status_code, error_msg))

        candidates = res_data.get("candidates")
        if not candidates:
            frappe.throw(_("Gemini returned an empty response or content was filtered by safety policies."))

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts or "text" not in parts[0]:
            finish_reason = candidates[0].get("finishReason", "UNKNOWN")
            frappe.throw(_("Gemini content generation ended unexpectedly with reason: {0}").format(finish_reason))

        return parts[0]["text"]

    except requests.exceptions.Timeout:
        frappe.throw(_("Gemini API request timed out after {0} seconds.").format(timeout))
    except requests.exceptions.RequestException as e:
        frappe.log_error(frappe.get_traceback(), "Gemini Network Exception")
        frappe.throw(_("Network error connecting to Gemini API: {0}").format(str(e)))


def call_gemini_structured_json(prompt: str, system_instruction: str = None, model_override: str = None, timeout: int = 60) -> dict:
    """Invokes Gemini and guarantees a clean, validated JSON dictionary."""
    sys_instruction = (system_instruction or "") + "\n\nRespond strictly with valid JSON. Never enclose response in markdown backticks or extra commentary."
    raw = call_gemini(prompt=prompt, system_instruction=sys_instruction, temperature=0.1, timeout=timeout, model_override=model_override)

    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1]
        if clean.endswith("```"):
            clean = clean.rsplit("```", 1)[0]
    clean = clean.strip()

    try:
        return json.loads(clean)
    except Exception as exc:
        frappe.log_error(f"Malformed AI Response:\n{raw}\nError: {str(exc)}", "Gemini JSON Parse Error")
        frappe.throw(_("Failed to parse Gemini output as structured JSON: {0}").format(str(exc)))


def generate_employee_poa_summary(poa_name: str) -> str:
    """Generates an evidence-based AI summary for an individual employee's Daily POA."""
    poa = frappe.get_doc("Xavirgin Daily POA", poa_name)
    tasks_data = [
        {
            "title": t.task_title,
            "type": t.task_type,
            "status": t.status,
            "expected_hours": t.expected_hours,
            "actual_hours": t.actual_hours,
            "github_ref": t.github_ref,
            "blocker": t.blocker_reason,
        }
        for t in poa.tasks
    ]

    prompt = f"""
    Analyze this employee's Daily Plan of Action (POA) using ONLY the factual records below:
    - Employee: {poa.employee_name} ({poa.designation} - {poa.department})
    - Date: {poa.poa_date}
    - Attendance Status: {poa.attendance_status} ({poa.attendance_hours_logged}h logged)
    - GitHub Contributions Today: {poa.github_contributions_summary or 'None'}
    - Tasks: {json.dumps(tasks_data, indent=2)}

    Provide a concise HTML summary with:
    1. Planned vs. Actual Execution Assessment
    2. Unresolved Blockers & Risks
    3. Recommended Priority for Next Working Day
    """
    raw_html = call_gemini(
        prompt=prompt,
        system_instruction="You are Path, operational AI analyst for Xavirgin. Use only supplied facts. Output clean HTML.",
        temperature=0.3,
    )
    clean_html = raw_html.replace("```html", "").replace("```", "").strip()

    prev_count = frappe.db.count("Xavirgin AI Summary Log", {"source_poa": poa.name, "scope_type": "Individual Employee"})
    frappe.get_doc({
        "doctype": "Xavirgin AI Summary Log",
        "summary_date": poa.poa_date,
        "scope_type": "Individual Employee",
        "employee": poa.employee,
        "department": poa.department,
        "source_poa": poa.name,
        "version": prev_count + 1,
        "summary_metrics": f"{poa.completed_tasks_count}/{len(poa.tasks)} tasks done | {poa.attendance_hours_logged}h attendance | {poa.github_events_count} GitHub events",
        "ai_html_report": clean_html,
        "raw_input_payload": json.dumps(tasks_data, indent=2),
    }).insert(ignore_permissions=True)

    frappe.db.commit()
    return clean_html


def generate_organization_path_insight(target_date: str = None, auto_apply_updates: bool = True):
    """Executes the daily organizational intelligence analysis and persists evolving Company State."""
    t_date = getdate(target_date or today())
    execution_id = f"EXEC-{t_date}-{generate_hash(length=8)}"

    prompt_cfg = get_active_prompt("Daily Operational Analysis")
    context_data = build_operational_context(start_date=t_date, end_date=t_date)
    context_json = json.dumps(context_data, indent=2, default=str)

    user_query = f"Execute Path CEO analysis for operational date {t_date}.\n\nOPERATIONAL TELEMETRY & PERSISTENT STATE:\n{context_json}"

    ai_output = {}
    status = "Generated"
    error_msg = ""
    try:
        ai_output = call_gemini_structured_json(
            prompt=user_query,
            system_instruction=prompt_cfg["system_instruction"],
            model_override=prompt_cfg["model_override"],
            timeout=75
        )
    except Exception as e:
        status = "Failed"
        error_msg = str(e)
        ai_output = {
            "did_company_move_forward": "PARTIALLY",
            "biggest_risk": f"Analysis execution failed: {str(e)}",
            "most_important_action": "Check system logs and retry analysis",
            "html_report": f"<p style='color:#ef4444;'>AI Execution Error: {str(e)}</p>",
            "proposed_state_updates": {}
        }

    prev_versions = frappe.db.count("Xavirgin AI Summary Log", {"summary_date": t_date, "scope_type": "Organization - Path CEO"})
    summary_doc = frappe.get_doc({
        "doctype": "Xavirgin AI Summary Log",
        "summary_date": t_date,
        "scope_type": "Organization - Path CEO",
        "status": status,
        "version": prev_versions + 1,
        "did_company_move_forward": ai_output.get("did_company_move_forward", "PARTIALLY"),
        "biggest_risk": ai_output.get("biggest_risk", ""),
        "most_important_action": ai_output.get("most_important_action", ""),
        "summary_metrics": (
            f"Active Squad: {len(context_data['operational_records']['attendances'])} present | "
            f"POAs: {len(context_data['operational_records']['poas_summary'])} | "
            f"GitHub Events: {len(context_data['operational_records']['github_engineering_events'])} | "
            f"Prompt: {prompt_cfg.get('prompt_doc_name') or 'Standard'} v{prompt_cfg.get('version', 1)}"
        ),
        "ai_html_report": ai_output.get("html_report") or f"<p>{ai_output.get('executive_summary', '')}</p>",
        "raw_input_payload": context_json,
        "error_log": error_msg
    }).insert(ignore_permissions=True)

    proposed_updates = ai_output.get("proposed_state_updates", {})
    history_doc = frappe.get_doc({
        "doctype": "Xavirgin Company State History",
        "version": int(frappe.db.get_single_value("Xavirgin Company State", "active_version") or 1),
        "approval_status": "Pending Approval",
        "snapshot_date": t_date,
        "ai_execution_id": execution_id,
        "prompt_used": prompt_cfg.get("prompt_doc_name"),
        "source_summary_log": summary_doc.name,
        "change_summary": f"Insights from {t_date}: {ai_output.get('most_important_action', 'Daily sync')}",
        "proposed_updates_json": json.dumps(proposed_updates, indent=2),
        "previous_state_json": json.dumps(context_data["current_company_state"], indent=2),
    }).insert(ignore_permissions=True)

    if status == "Generated" and auto_apply_updates and proposed_updates:
        apply_proposed_state_updates(history_doc.name, reviewer_user="Administrator")

    frappe.db.commit()
    return summary_doc


def generate_historical_period_analysis(start_date: str, end_date: str, prompt_name: str = None) -> dict:
    """Performs an ad-hoc historical analysis across any arbitrary date range without corrupting current state."""
    s_date = getdate(start_date)
    e_date = getdate(end_date)

    if s_date > e_date:
        frappe.throw(_("Start Date cannot be greater than End Date."))

    if prompt_name and frappe.db.exists("Xavirgin Prompt", prompt_name):
        p_doc = frappe.get_doc("Xavirgin Prompt", prompt_name)
        prompt_cfg = {
            "prompt_doc_name": p_doc.name,
            "version": p_doc.version,
            "system_instruction": p_doc.system_instruction,
            "model_override": p_doc.model_override,
            "temperature": p_doc.temperature or 0.2
        }
    else:
        prompt_cfg = get_active_prompt("Historical Company Analysis")

    context_data = build_operational_context(start_date=s_date, end_date=e_date, category="Historical Company Analysis")
    context_json = json.dumps(context_data, indent=2, default=str)

    user_query = f"Execute historical company analysis for the period {s_date} to {e_date}.\n\nHISTORICAL CONTEXT:\n{context_json}"

    ai_output = call_gemini_structured_json(
        prompt=user_query,
        system_instruction=prompt_cfg["system_instruction"],
        model_override=prompt_cfg["model_override"],
        timeout=90
    )

    prev_count = frappe.db.count("Xavirgin AI Summary Log", {"summary_date": e_date, "scope_type": "Organization - Path CEO"})
    report_doc = frappe.get_doc({
        "doctype": "Xavirgin AI Summary Log",
        "summary_date": e_date,
        "scope_type": "Organization - Path CEO",
        "status": "Generated",
        "version": prev_count + 1,
        "did_company_move_forward": ai_output.get("did_company_move_forward", "PARTIALLY"),
        "biggest_risk": ai_output.get("biggest_risk", ""),
        "most_important_action": ai_output.get("most_important_action", ""),
        "summary_metrics": f"Historical Period: {s_date} to {e_date} | Generated via {prompt_cfg.get('prompt_doc_name') or 'Default'}",
        "ai_html_report": ai_output.get("html_report") or f"<p>{ai_output.get('executive_summary', '')}</p>",
        "raw_input_payload": context_json
    }).insert(ignore_permissions=True)

    frappe.db.commit()
    return {
        "report_id": report_doc.name,
        "analysis": ai_output
    }