import frappe
from frappe import _


DEFAULT_PATH_CEO_SYSTEM = """You are "Path" (Paatha), the strategic autonomous intelligence engine for XAVIRGIN (OPC) PRIVATE LIMITED.
You operate on Xavirgin's "ZERO ENERGY PROTOCOL":
- Survival and cash-generation are your primary operational imperatives.
- Productivity is measured only by delivered, working systems, real client value, and actual revenue.
- Attendance, logging hours, filing tasks, or claiming XP do not equal output.
- You must strictly distinguish between VERIFIED FACTS (provided from ERPNext records) and YOUR RECOMMENDATIONS.
- NEVER fabricate financial figures, commits, or employee counts.

You must respond ONLY with a clean JSON object following this exact schema:
{
  "did_company_move_forward": "YES" | "PARTIALLY" | "NO",
  "executive_summary": "Concise assessment of strategic velocity",
  "biggest_risk": "One clear sentence describing immediate vulnerability",
  "most_important_action": "Single highest-leverage action required",
  "operational_findings": {
    "engineering_velocity": "Assessment of commits & PRs",
    "delivery_blockers": ["List of confirmed blockers"],
    "talent_observations": "Intern execution and squad consistency"
  },
  "proposed_state_updates": {
    "add_decisions": [
      {"decision": "Title", "rationale": "Reason", "owner": "Name"}
    ],
    "add_actions": [
      {"action": "Action item", "owner": "Name", "priority": "High|Medium", "deadline": "YYYY-MM-DD"}
    ],
    "resolve_actions": ["Exact string of action previously pending that was completed today"],
    "add_issues": [
      {"issue": "Description of blocker", "severity": "Critical|Moderate", "owner": "Name"}
    ],
    "resolve_issues": ["Exact string of resolved issue"],
    "update_risks": [
      {"risk": "Specific risk", "severity": "High|Medium", "mitigation": "Planned response"}
    ],
    "update_opportunities": [
      {"opportunity": "Avenue for cash or execution speed", "value": "High|Medium"}
    ]
  },
  "html_report": "<p>Formatted HTML version of the strategic analysis...</p>"
}"""


def get_active_prompt(category: str = "Daily Operational Analysis", model_name: str = None) -> dict:
    """Retrieves the active prompt configured by the administrator for the requested category."""
    if not frappe.db.exists("DocType", "Xavirgin Prompt"):
        return _fallback_prompt(category)

    prompts = frappe.get_all(
        "Xavirgin Prompt",
        filters={"category": category, "is_active": 1},
        fields=["name", "version", "system_instruction", "prompt_template", "model_override", "temperature"],
        order_by="is_default desc, version desc",
        limit=1
    )

    if not prompts:
        return _fallback_prompt(category)

    p = prompts[0]
    return {
        "prompt_doc_name": p.name,
        "version": p.version,
        "system_instruction": p.system_instruction or DEFAULT_PATH_CEO_SYSTEM,
        "prompt_template": p.prompt_template or "Analyze the attached operational telemetry and output the structured JSON.",
        "model_override": p.model_override,
        "temperature": p.temperature or 0.2
    }


def _fallback_prompt(category: str) -> dict:
    return {
        "prompt_doc_name": None,
        "version": 1,
        "system_instruction": DEFAULT_PATH_CEO_SYSTEM,
        "prompt_template": "Analyze the attached operational telemetry and output the structured JSON.",
        "model_override": None,
        "temperature": 0.2
    }


def seed_default_prompts():
    """Seeds default standard prompts into Xavirgin Prompt if empty."""
    if not frappe.db.exists("DocType", "Xavirgin Prompt"):
        return

    categories = [
        ("Daily Operational Analysis", "Path Autonomous CEO Daily Operational Analysis", DEFAULT_PATH_CEO_SYSTEM),
        ("Financial Analysis", "Xavirgin Liquidity & Zero Energy Telemetry", "Analyze ERPNext financial data, burn rate, and director loans against survival milestones."),
        ("CTO Assistant", "Engineering Velocity & Telemetry Analysis", "Evaluate commits, PR reviews, branches, and code submissions from Xavirgin GitHub activity.")
    ]

    for cat, title, instruction in categories:
        if not frappe.db.exists("Xavirgin Prompt", {"category": cat}):
            frappe.get_doc({
                "doctype": "Xavirgin Prompt",
                "title": title,
                "category": cat,
                "version": 1,
                "is_active": 1,
                "is_default": 1,
                "temperature": 0.2,
                "system_instruction": instruction,
                "prompt_template": "Evaluate the following structured context:\n\n{{ context_json }}"
            }).insert(ignore_permissions=True)