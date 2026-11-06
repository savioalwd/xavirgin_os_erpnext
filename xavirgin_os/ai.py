import json
import time
import urllib.error
import urllib.request
import frappe
from frappe import _
from frappe.utils import format_datetime, formatdate, getdate, now_datetime, today
from xavirgin_os.context_builder import build_operational_context
from xavirgin_os.prompt_manager import get_active_prompt


class XavirginAIError(Exception):
    def __init__(self, category: str, user_message: str, admin_hint: str = "", model: str = "", http_code: int = 0):
        super().__init__(user_message)
        self.category = category
        self.user_message = user_message
        self.admin_hint = admin_hint
        self.model = model
        self.http_code = http_code

    def to_dict(self) -> dict:
        return {
            "status": "error",
            "error_category": self.category,
            "user_message": self.user_message,
            "admin_hint": self.admin_hint,
            "configured_model": self.model,
            "http_code": self.http_code,
        }


def classify_ai_exception(exc: Exception, model_name: str, http_code: int = 0, raw_body: str = "") -> XavirginAIError:
    """Maps low-level HTTP/network exceptions to the 9 required user-safe error categories."""
    msg_lower = f"{str(exc)} {raw_body}".lower()

    if http_code == 429 or "resource_exhausted" in msg_lower or "rate limit" in msg_lower or "quota" in msg_lower:
        return XavirginAIError(
            category="rate_limit",
            user_message=_("AI provider is receiving too many requests right now. Please retry after a short wait."),
            admin_hint=_("Model '{0}' hit rate/quota limits. Wait 30–60s or switch to another model in Xavirgin HR Settings.").format(model_name),
            model=model_name,
            http_code=429,
        )

    if http_code in (502, 503, 529) or "overloaded" in msg_lower or "unavailable" in msg_lower or "busy" in msg_lower:
        return XavirginAIError(
            category="server_overload",
            user_message=_("The configured AI model ({0}) is currently busy due to high traffic. Please retry shortly.").format(model_name),
            admin_hint=_("Temporary model overload on '{0}'. If persistent, switch Gemini Model Name in Xavirgin HR Settings (e.g. gemini-2.5-flash).").format(model_name),
            model=model_name,
            http_code=http_code or 503,
        )

    if "timed out" in msg_lower or "timeout" in msg_lower or http_code == 504:
        return XavirginAIError(
            category="timeout",
            user_message=_("The AI model took too long to respond. Your Daily POA data is safe — please retry."),
            admin_hint=_("Request timed out against model '{0}'. Consider using a faster flash model in Xavirgin HR Settings.").format(model_name),
            model=model_name,
            http_code=504,
        )

    if http_code in (401, 403) or "api_key_invalid" in msg_lower or "permission_denied" in msg_lower or "unauthenticated" in msg_lower:
        return XavirginAIError(
            category="invalid_api_key",
            user_message=_("AI provider credentials require administrator attention."),
            admin_hint=_("Verify the Gemini API Key in Xavirgin HR Settings."),
            model=model_name,
            http_code=http_code or 401,
        )

    if http_code == 404 or ("model" in msg_lower and ("not found" in msg_lower or "not supported" in msg_lower)):
        return XavirginAIError(
            category="invalid_model",
            user_message=_("The configured AI model name is invalid or unavailable."),
            admin_hint=_("Check the configured model name ('{0}') in Xavirgin HR Settings -> Gemini Model Name (e.g. gemini-2.5-flash).").format(model_name),
            model=model_name,
            http_code=404,
        )

    if "token" in msg_lower or "context" in msg_lower or "too large" in msg_lower or http_code == 413:
        return XavirginAIError(
            category="context_limit",
            user_message=_("Input context is too large for the current model."),
            admin_hint=_("Reduce requested date range or switch to a larger context model in Xavirgin HR Settings."),
            model=model_name,
            http_code=http_code or 400,
        )

    if isinstance(exc, urllib.error.URLError) or "name or service not known" in msg_lower or "connection" in msg_lower:
        return XavirginAIError(
            category="network_error",
            user_message=_("Unable to connect to the AI provider due to a network issue. Please retry."),
            admin_hint=_("Check outbound HTTPS connectivity from the server to generativelanguage.googleapis.com."),
            model=model_name,
            http_code=0,
        )

    if http_code >= 500:
        return XavirginAIError(
            category="provider_unavailable",
            user_message=_("AI service is temporarily unavailable. Please retry in a few moments."),
            admin_hint=_("Upstream HTTP {0} from AI provider for model '{1}'.").format(http_code, model_name),
            model=model_name,
            http_code=http_code,
        )

    return XavirginAIError(
        category="invalid_response",
        user_message=_("The AI model returned an unexpected response. Please retry."),
        admin_hint=_("Inspect Error Log in Desk for model '{0}'.").format(model_name),
        model=model_name,
        http_code=http_code,
    )


def call_gemini_resilient(
    prompt: str,
    system_instruction: str = None,
    temperature: float = 0.2,
    model_override: str = None,
    timeout_sec: int = 35,
    max_retries: int = 2,
) -> dict:
    """Executes a resilient Gemini API call with automatic backoff on 429/503 and structured error classification."""
    settings = frappe.get_single("Xavirgin HR Settings")
    creds = settings.get_gemini_credentials()
    api_key = (creds.get("api_key") or "").strip()
    model_name = (model_override or creds.get("model") or "gemini-2.5-flash").strip()

    if not api_key:
        err = XavirginAIError(
            category="invalid_api_key",
            user_message=_("AI provider credentials are not configured yet."),
            admin_hint=_("Open Xavirgin HR Settings and set a valid Gemini API Key."),
            model=model_name,
            http_code=401,
        )
        return err.to_dict()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": float(temperature or 0.2)},
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    encoded_data = json.dumps(payload).encode("utf-8")
    last_error = None

    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, data=encoded_data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                raw_resp = resp.read().decode("utf-8")
                parsed = json.loads(raw_resp)
                candidates = parsed.get("candidates") or []
                if not candidates:
                    raise ValueError("Empty candidates array in Gemini response")
                parts = (candidates[0].get("content") or {}).get("parts") or []
                text_out = "".join(p.get("text", "") for p in parts).strip()
                if not text_out:
                    raise ValueError("Empty text content in Gemini response")
                return {
                    "status": "success",
                    "text": text_out,
                    "configured_model": model_name,
                }
        except urllib.error.HTTPError as http_err:
            raw_err_body = ""
            try:
                raw_err_body = http_err.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            last_error = classify_ai_exception(http_err, model_name, http_code=http_err.code, raw_body=raw_err_body)
            if last_error.category in ("rate_limit", "server_overload", "provider_unavailable") and attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            break
        except Exception as exc:
            last_error = classify_ai_exception(exc, model_name)
            if last_error.category in ("timeout", "network_error") and attempt < max_retries:
                time.sleep(1.0 * (attempt + 1))
                continue
            break

    frappe.log_error(
        title=f"Xavirgin AI Error [{last_error.category if last_error else 'unknown'}] ({model_name})",
        message=f"Category: {last_error.category if last_error else 'unknown'}\nModel: {model_name}\nUser Msg: {last_error.user_message if last_error else ''}",
    )
    return last_error.to_dict() if last_error else {
        "status": "error",
        "error_category": "invalid_response",
        "user_message": _("AI generation failed unexpectedly. Please retry."),
        "admin_hint": _("Check Xavirgin HR Settings."),
        "configured_model": model_name,
    }


def call_gemini(prompt: str, system_instruction: str = None, temperature: float = 0.2, model_override: str = None) -> str:
    """Backward-compatible string helper used by Candidate, Evaluation, and Template modules."""
    res = call_gemini_resilient(
        prompt=prompt,
        system_instruction=system_instruction,
        temperature=temperature,
        model_override=model_override,
    )
    if res.get("status") == "success":
        return res.get("text", "")
    frappe.throw(_("{0} {1}").format(res.get("user_message", ""), res.get("admin_hint", "")).strip())


def generate_employee_poa_summary_structured(poa_name: str) -> dict:
    """Generates a structured, section-organized AI Daily Review for any employee's Daily POA.
    - Works seamlessly whether or not the employee has a GitHub account.
    - Never overwrites an existing summary on failure.
    - Safe against missing attributes on task child rows.
    """
    if not poa_name or not frappe.db.exists("Xavirgin Daily POA", poa_name):
        return {"status": "error", "user_message": _("Daily POA record not found.")}

    poa = frappe.get_doc("Xavirgin Daily POA", poa_name)
    emp_info = frappe.db.get_value(
        "Employee",
        poa.employee,
        ["employee_name", "department", "designation", "custom_github_username"],
        as_dict=True,
    ) or {}

    gh_username = (emp_info.get("custom_github_username") or "").strip()

    # 1. Attendance Sessions
    sessions = frappe.get_all(
        "Xavirgin Attendance Session",
        filters={"employee": poa.employee, "attendance_date": getdate(poa.poa_date)},
        fields=["name", "status", "worked_hours", "day_classification", "work_log"],
        order_by="check_in asc",
    )

    # 2. Optional GitHub Activity
    from xavirgin_os.xavirgin_os.doctype.xavirgin_daily_poa.xavirgin_daily_poa import (
        resolve_and_fetch_employee_github_events,
    )
    gh_events = resolve_and_fetch_employee_github_events(poa.employee, poa.poa_date, gh_username=gh_username)

    has_github_account = bool(gh_username)
    has_github_events = len(gh_events) > 0

    task_lines = []
    completed_count = 0
    blocked_count = 0
    in_progress_count = 0
    pending_count = 0

    for t in poa.tasks:
        st = getattr(t, "status", "Planned")
        title = getattr(t, "task_title", "Untitled Task")
        cat = getattr(t, "task_type", "General")
        exp_h = getattr(t, "expected_hours", 0) or 0
        act_h = getattr(t, "actual_hours", 0) or 0
        desc = getattr(t, "description", "") or ""
        blocker = getattr(t, "blocker_reason", "") or ""
        ref_source = getattr(t, "carried_from_poa", None) or ""

        if st == "Completed":
            completed_count += 1
        elif st in ("Blocked", "Stuck / Blocked"):
            blocked_count += 1
        elif st in ("In Progress", "InProgress", "Working"):
            in_progress_count += 1
        else:
            pending_count += 1

        ref_str = f" [Carried from: {ref_source}]" if ref_source else ""
        task_lines.append(
            f"- [{st}] {title} (Category: {cat}, Est: {exp_h}h, Actual: {act_h}h{ref_str})"
            + (f" | Notes: {desc}" if desc else "")
            + (f" | Blocker: {blocker}" if blocker else "")
        )

    if not task_lines:
        task_lines.append("- No tasks listed.")

    att_lines = [
        f"- Session #{idx} ({s.status}): {s.worked_hours}h clocked" + (f" — Log: {s.work_log}" if s.work_log else "")
        for idx, s in enumerate(sessions, start=1)
    ] or ["- No attendance check-in recorded for this date."]

    if has_github_events:
        gh_lines = [
            f"- [{g.get('event_type')}] Repo: {g.get('repository')} | {g.get('summary')} (Ref: {g.get('reference_id') or 'N/A'})"
            for g in gh_events
        ]
        gh_context_note = f"GitHub Linked (@{gh_username}) — {len(gh_events)} event(s) recorded on {poa.poa_date}."
    elif has_github_account:
        gh_lines = ["- No GitHub webhook events received for this date."]
        gh_context_note = f"GitHub Linked (@{gh_username}) — 0 events today."
    else:
        gh_lines = ["- Not Applicable (Employee role does not require a linked GitHub account)."]
        gh_context_note = "Non-GitHub / Non-Code Role — Evaluate strictly on POA deliverables and attendance logs."

    prompt = f"""Analyze the following verified Daily POA record for {poa.employee_name} ({poa.designation or 'Team Member'} in {poa.department or 'General'}) on {poa.poa_date}:

EMPLOYEE & TELEMETRY CONTEXT:
- Employee: {poa.employee_name} ({poa.employee})
- Department / Role: {poa.department} / {poa.designation}
- Work Status: {poa.status}
- Attendance Status: {poa.attendance_status} ({poa.attendance_hours_logged}h clocked across {len(sessions)} session(s))
- Planned Hours: {poa.total_planned_hours}h | Actual Task Hours: {poa.total_actual_hours}h
- Tasks Completed: {completed_count} | In Progress: {in_progress_count} | Pending: {pending_count} | Blocked: {blocked_count}
- GitHub Telemetry Status: {gh_context_note}

RECORDED TASKS & DELIVERABLES:
{chr(10).join(task_lines)}

RECORDED ATTENDANCE SESSIONS:
{chr(10).join(att_lines)}

RECORDED GITHUB ACTIVITY (OPTIONAL):
{chr(10).join(gh_lines)}

INSTRUCTIONS:
1. Distinguish clearly between ACTUAL RECORDED FACTS and your AI RECOMMENDATIONS.
2. Do NOT penalize non-developer roles (HR, UI/UX, Marketing, Operations) for not having GitHub commits.
3. Never fabricate tasks, commits, or hours.
4. Return a clean JSON object with these exact keys:
{{
  "daily_work_overview": "2-3 sentence summary of today's execution",
  "achievements": ["Bullet 1", "Bullet 2"],
  "blockers_analysis": "Analysis of any blockers or 'No active blockers reported.'",
  "recommendations": ["Actionable recommendation 1", "Actionable recommendation 2"],
  "overall_productivity_verdict": "High Execution | Steady Progress | Needs Attention | Blocked"
}}"""

    system_instruction = (
        "You are an objective engineering and operations performance reviewer for Xavirgin OS. "
        "Respond ONLY with valid JSON matching the requested schema."
    )

    ai_res = call_gemini_resilient(prompt=prompt, system_instruction=system_instruction, temperature=0.2)
    if ai_res.get("status") != "success":
        return ai_res

    raw_text = ai_res.get("text", "").strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]
        if raw_text.endswith("```"):
            raw_text = raw_text.rsplit("```", 1)[0]
    raw_text = raw_text.strip()

    try:
        parsed = json.loads(raw_text)
    except Exception:
        parsed = {
            "daily_work_overview": raw_text,
            "achievements": [],
            "blockers_analysis": poa.blockers_summary or "None",
            "recommendations": [],
            "overall_productivity_verdict": "Reviewed",
        }

    generated_ts = format_datetime(now_datetime(), "dd MMM yyyy hh:mm a")
    model_used = ai_res.get("configured_model", "gemini-2.5-flash")
    verdict = parsed.get("overall_productivity_verdict") or "Reviewed"

    gh_badge_html = (
        f"<span style='background:#dcfce7; color:#166534; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700;'>💻 GitHub Data Used ({len(gh_events)} Events)</span>"
        if has_github_events
        else (
            "<span style='background:#f1f5f9; color:#475569; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:600;'>💻 GitHub Linked (0 Events Today)</span>"
            if has_github_account
            else "<span style='background:#e0f2fe; color:#0369a1; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:600;'>ℹ️ GitHub Optional (Role Based on POA & Attendance)</span>"
        )
    )

    achievements_html = "".join(f"<li>{frappe.utils.escape_html(a)}</li>" for a in (parsed.get("achievements") or [])) or "<li>Logged daily task plan.</li>"
    recs_html = "".join(f"<li>{frappe.utils.escape_html(r)}</li>" for r in (parsed.get("recommendations") or [])) or "<li>Continue tracking deliverables and session logs.</li>"

    html_report = f"""
    <div class="xav-ai-structured-report" data-generated-at="{generated_ts}" data-model="{frappe.utils.escape_html(model_used)}" style="font-family: Arial, sans-serif; color: #1e293b; line-height: 1.6;">
        <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px; padding:10px 14px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; margin-bottom:12px;">
            <div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px;">
                <span style="background:#dbeafe; color:#1e40af; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:800;">
                    ✨ Verdict: {frappe.utils.escape_html(verdict)}
                </span>
                <span style="background:#f3e8ff; color:#6b21a8; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700;">
                    🤖 Model: {frappe.utils.escape_html(model_used)}
                </span>
                {gh_badge_html}
            </div>
            <div style="font-size:11px; color:#64748b; font-weight:600;">
                🕒 Generated: {generated_ts}
            </div>
        </div>

        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:10px; margin-bottom:12px;">
            <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:10px 12px;">
                <div style="font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase;">📋 Recorded Tasks Summary</div>
                <div style="font-size:12px; margin-top:4px;">
                    <b>✅ Completed:</b> {completed_count} &nbsp;|&nbsp;
                    <b>⚡ Working:</b> {in_progress_count} &nbsp;|&nbsp;
                    <b>⏳ Pending:</b> {pending_count} &nbsp;|&nbsp;
                    <b>🛑 Blocked:</b> {blocked_count}
                </div>
            </div>
            <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:10px 12px;">
                <div style="font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase;">⏱️ Recorded Attendance Summary</div>
                <div style="font-size:12px; margin-top:4px;">
                    <b>{frappe.utils.escape_html(poa.attendance_status or 'Not Checked In')}</b>
                    ({poa.attendance_hours_logged or 0}h clocked / {poa.total_actual_hours or 0}h task actuals)
                </div>
            </div>
        </div>

        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:12px 14px; margin-bottom:10px;">
            <div style="font-size:11px; font-weight:800; color:#0f172a; text-transform:uppercase; margin-bottom:4px;">🔍 Daily Work Overview (AI Analysis)</div>
            <p style="margin:0; font-size:13px; color:#334155;">{frappe.utils.escape_html(parsed.get("daily_work_overview") or "")}</p>
        </div>

        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(250px, 1fr)); gap:10px; margin-bottom:10px;">
            <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:10px 12px;">
                <div style="font-size:11px; font-weight:800; color:#166534; text-transform:uppercase; margin-bottom:4px;">🏆 Key Achievements & Deliverables</div>
                <ul style="margin:0; padding-left:18px; font-size:12px; color:#15803d;">{achievements_html}</ul>
            </div>
            <div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; padding:10px 12px;">
                <div style="font-size:11px; font-weight:800; color:#1e40af; text-transform:uppercase; margin-bottom:4px;">💡 AI Recommendations & Next Steps</div>
                <ul style="margin:0; padding-left:18px; font-size:12px; color:#1e3a8a;">{recs_html}</ul>
            </div>
        </div>

        <div style="background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:10px 12px; font-size:12px; color:#92400e;">
            <strong>🚧 Blockers & Risk Assessment:</strong> {frappe.utils.escape_html(parsed.get("blockers_analysis") or poa.blockers_summary or "No active blockers.")}
        </div>
    </div>
    """

    return {
        "status": "success",
        "html_summary": html_report,
        "configured_model": model_used,
        "generated_at": generated_ts,
        "has_github_account": has_github_account,
        "github_events_count": len(gh_events),
    }


def generate_employee_poa_summary(poa_name: str) -> str:
    """Backward-compatible wrapper returning HTML string or raising user-safe error."""
    res = generate_employee_poa_summary_structured(poa_name)
    if res.get("status") == "success":
        return res.get("html_summary", "")
    frappe.throw(_("{0} {1}").format(res.get("user_message", ""), res.get("admin_hint", "")).strip())


@frappe.whitelist()
def generate_organization_path_insight(target_date: str = None):
    """Generates the daily organization-wide Path CEO Insight."""
    t_date = getdate(target_date or today())
    ctx = build_operational_context(start_date=str(t_date), end_date=str(t_date), category="Daily Operational Analysis")
    prompt_cfg = get_active_prompt("Daily Operational Analysis")

    prompt_text = prompt_cfg["prompt_template"].replace("{{ context_json }}", json.dumps(ctx, default=str))
    if "{{ context_json }}" not in prompt_cfg["prompt_template"]:
        prompt_text = f"{prompt_cfg['prompt_template']}\n\n{json.dumps(ctx, default=str)}"

    ai_res = call_gemini_resilient(
        prompt=prompt_text,
        system_instruction=prompt_cfg["system_instruction"],
        temperature=prompt_cfg["temperature"],
        model_override=prompt_cfg.get("model_override"),
    )
    if ai_res.get("status") != "success":
        frappe.throw(_("{0} {1}").format(ai_res.get("user_message", ""), ai_res.get("admin_hint", "")).strip())

    raw_out = ai_res.get("text", "").strip()
    if raw_out.startswith("```"):
        raw_out = raw_out.split("\n", 1)[1]
        if raw_out.endswith("```"):
            raw_out = raw_out.rsplit("```", 1)[0]
    raw_out = raw_out.strip()

    try:
        parsed = json.loads(raw_out)
    except Exception:
        parsed = {
            "did_company_move_forward": "PARTIALLY",
            "executive_summary": raw_out[:500],
            "biggest_risk": "See full report",
            "most_important_action": "Review daily POAs",
            "html_report": f"<div>{frappe.utils.escape_html(raw_out)}</div>",
        }

    doc = frappe.get_doc({
        "doctype": "Xavirgin AI Summary Log",
        "summary_date": t_date,
        "scope_type": "Organization - Path CEO",
        "did_company_move_forward": parsed.get("did_company_move_forward", "PARTIALLY"),
        "biggest_risk": parsed.get("biggest_risk", ""),
        "most_important_action": parsed.get("most_important_action", ""),
        "summary_html": parsed.get("html_report") or parsed.get("executive_summary") or raw_out,
        "raw_json_response": json.dumps(parsed, indent=2),
    })
    doc.insert(ignore_permissions=True)
    return doc


@frappe.whitelist()
def generate_historical_period_analysis(start_date: str, end_date: str, prompt_name: str = None):
    """Generates a multi-day historical operational analysis."""
    ctx = build_operational_context(start_date=start_date, end_date=end_date, category="Historical Company Analysis")
    prompt_cfg = get_active_prompt("Historical Company Analysis")
    if prompt_name and frappe.db.exists("Xavirgin Prompt", prompt_name):
        p_doc = frappe.get_doc("Xavirgin Prompt", prompt_name)
        prompt_cfg["system_instruction"] = p_doc.system_instruction or prompt_cfg["system_instruction"]
        prompt_cfg["prompt_template"] = p_doc.prompt_template or prompt_cfg["prompt_template"]
        prompt_cfg["model_override"] = p_doc.model_override

    prompt_text = f"{prompt_cfg['prompt_template']}\n\n{json.dumps(ctx, default=str)}"
    ai_res = call_gemini_resilient(
        prompt=prompt_text,
        system_instruction=prompt_cfg["system_instruction"],
        temperature=prompt_cfg["temperature"],
        model_override=prompt_cfg.get("model_override"),
    )
    if ai_res.get("status") != "success":
        frappe.throw(_("{0} {1}").format(ai_res.get("user_message", ""), ai_res.get("admin_hint", "")).strip())

    doc = frappe.get_doc({
        "doctype": "Xavirgin AI Summary Log",
        "summary_date": getdate(end_date),
        "scope_type": "Organization - Path CEO",
        "summary_html": ai_res.get("text", ""),
    })
    doc.insert(ignore_permissions=True)
    return {"report_id": doc.name}