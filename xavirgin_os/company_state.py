import json
import frappe
from frappe import _
from frappe.utils import now_datetime, today, getdate
from xavirgin_os.finance import get_xavirgin_liquidity


DEFAULT_FACTS = [
    {"fact": "XAVIRGIN (OPC) PRIVATE LIMITED incorporated on November 17, 2025. CIN: U62090KL2025OPC098558.", "verified": True},
    {"fact": "Primary operational model: ZERO ENERGY Protocol (Capital = 0, Revenue from Value-Creation).", "verified": True},
    {"fact": "Core platform products: Xavirgin OS (Enterprise Desk) and Xoly (Trade & Gig Marketplace).", "verified": True},
    {"fact": "Talent Development: 90-Day Remote Engineering Residency & Zero Energy Intern Cohorts.", "verified": True}
]


def get_current_company_state_dict() -> dict:
    """Returns the persistent Company State as a clean Python dictionary.
    Initializes default structure if accessing for the first time."""
    if not frappe.db.exists("DocType", "Xavirgin Company State"):
        return get_initial_company_state_template()

    state_doc = frappe.get_single("Xavirgin Company State")
    if not state_doc.full_state_json or state_doc.full_state_json.strip() == "":
        return initialize_first_time_company_state()

    try:
        data = json.loads(state_doc.full_state_json)
    except Exception:
        data = get_initial_company_state_template()

    # Always inject authoritative real-time financials directly from ERPNext General Ledger
    verified_finance = get_verified_erpnext_financials()
    data["financial_state"] = verified_finance
    return data


def get_verified_erpnext_financials() -> dict:
    """Queries ERPNext General Ledger directly. AI is never allowed to override these numbers."""
    telemetry = get_xavirgin_liquidity()
    company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
    
    # Separate cash and bank accounts
    cash_balance = 0.0
    bank_balance = 0.0
    if company:
        accounts = frappe.get_all(
            "Account",
            filters={"company": company, "is_group": 0, "account_type": ["in", ["Cash", "Bank"]]},
            fields=["name", "account_type"]
        )
        for acc in accounts:
            gl = frappe.db.sql(
                "SELECT SUM(debit - credit) FROM `tabGL Entry` WHERE company=%s AND is_cancelled=0 AND account=%s",
                (company, acc.name)
            )
            bal = float(gl[0][0] or 0.0)
            if acc.account_type == "Cash":
                cash_balance += bal
            else:
                bank_balance += bal

    return {
        "cash_balance": round(cash_balance, 2),
        "bank_balance": round(bank_balance, 2),
        "total_liquidity": round(telemetry.get("amount", 0.0), 2),
        "currency_symbol": telemetry.get("currency_symbol", "₹"),
        "receivables": telemetry.get("receivables", "0.00"),
        "payables": telemetry.get("payables", "0.00"),
        "director_loans": telemetry.get("director_loan", "0.00"),
        "fiscal_year_gain": telemetry.get("formatted_gain", "0.00"),
        "fiscal_year_debt": telemetry.get("formatted_debt", "0.00"),
        "verified_at": str(now_datetime()),
        "source": "ERPNext Chart of Accounts & tabGL Entry"
    }


def get_initial_company_state_template() -> dict:
    return {
        "company": {
            "name": "XAVIRGIN (OPC) PRIVATE LIMITED",
            "cin": "U62090KL2025OPC098558",
            "last_updated": str(today())
        },
        "financial_state": get_verified_erpnext_financials(),
        "operational_state": {
            "active_projects": [
                {"name": "Xavirgin OS", "status": "Active", "lead": "Savio Babu", "focus": "Internal ERP & Telemetry"},
                {"name": "Xoly", "status": "Active", "focus": "Trade & Gig Marketplace"}
            ],
            "completed_projects": [],
            "blocked_projects": [],
            "active_departments": ["Software Development", "UI/UX Design", "Quality Assurance", "Human Resources"]
        },
        "human_resources": {
            "active_squad_count": 0,
            "interns_in_residency": 0,
            "pending_offer_letters": 0
        },
        "decisions": [],
        "pending_actions": [],
        "unresolved_issues": [],
        "risks": [],
        "opportunities": [],
        "long_term_objectives": [
            "Execute Zero Energy survival protocol: convert engineering intelligence to sustained cash flows",
            "Deliver 90-day practical developer competencies through structured remote cohorts",
            "Automate company operational intelligence using self-updating state models"
        ],
        "important_historical_facts": DEFAULT_FACTS
    }


def initialize_first_time_company_state() -> dict:
    """Populates the single DocType with initial baseline memory."""
    state_dict = get_initial_company_state_template()
    state_doc = frappe.get_single("Xavirgin Company State")
    state_doc.company_name = state_dict["company"]["name"]
    state_doc.active_version = 1
    state_doc.last_updated_date = today()
    state_doc.last_updated_time = now_datetime()
    state_doc.last_update_source = "System Bootstrap Initialization"
    
    _sync_dict_to_state_doc(state_doc, state_dict)
    state_doc.flags.ignore_permissions = True
    state_doc.save()
    frappe.db.commit()
    return state_dict


def _sync_dict_to_state_doc(state_doc, state_dict: dict):
    """Binds structured sections into DocType fields."""
    fin = state_dict.get("financial_state", {})
    state_doc.cash_balance = fin.get("cash_balance", 0.0)
    state_doc.bank_balance = fin.get("bank_balance", 0.0)
    state_doc.total_liquidity = fin.get("total_liquidity", 0.0)

    state_doc.operational_state_json = json.dumps(state_dict.get("operational_state", {}), indent=2)
    state_doc.human_resources_json = json.dumps(state_dict.get("human_resources", {}), indent=2)
    state_doc.active_decisions_json = json.dumps(state_dict.get("decisions", []), indent=2)
    state_doc.pending_actions_json = json.dumps(state_dict.get("pending_actions", []), indent=2)
    state_doc.unresolved_issues_json = json.dumps(state_dict.get("unresolved_issues", []), indent=2)
    state_doc.risks_json = json.dumps(state_dict.get("risks", []), indent=2)
    state_doc.opportunities_json = json.dumps(state_dict.get("opportunities", []), indent=2)
    state_doc.long_term_objectives_json = json.dumps(state_dict.get("long_term_objectives", []), indent=2)
    state_doc.important_historical_facts_json = json.dumps(state_dict.get("important_historical_facts", []), indent=2)
    state_doc.full_state_json = json.dumps(state_dict, indent=2)


def apply_proposed_state_updates(history_name: str, reviewer_user: str = None) -> bool:
    """Atomically commits proposed updates from a history record into the active Company State."""
    hist = frappe.get_doc("Xavirgin Company State History", history_name)
    if hist.approval_status == "Applied":
        frappe.throw(_("History record {0} has already been applied.").format(history_name))

    current_state = get_current_company_state_dict()
    proposed = json.loads(hist.proposed_updates_json or "{}")

    # 1. Decisions: Append new tracked decisions
    for dec in proposed.get("add_decisions", []):
        dec["recorded_date"] = dec.get("recorded_date") or str(today())
        current_state["decisions"].insert(0, dec)

    # 2. Pending Actions: Add new and remove resolved
    resolved_action_keys = set(proposed.get("resolve_actions", []))
    current_state["pending_actions"] = [
        a for a in current_state.get("pending_actions", [])
        if a.get("action") not in resolved_action_keys and a.get("id") not in resolved_action_keys
    ]
    for act in proposed.get("add_actions", []):
        act["created_date"] = act.get("created_date") or str(today())
        current_state["pending_actions"].append(act)

    # 3. Unresolved Issues / Blockers
    resolved_issue_keys = set(proposed.get("resolve_issues", []))
    current_state["unresolved_issues"] = [
        i for i in current_state.get("unresolved_issues", [])
        if i.get("issue") not in resolved_issue_keys and i.get("id") not in resolved_issue_keys
    ]
    for iss in proposed.get("add_issues", []):
        iss["reported_date"] = iss.get("reported_date") or str(today())
        current_state["unresolved_issues"].append(iss)

    # 4. Strategic Risks & Opportunities (Replace with latest operational landscape)
    if proposed.get("update_risks") is not None:
        current_state["risks"] = proposed["update_risks"]
    if proposed.get("update_opportunities") is not None:
        current_state["opportunities"] = proposed["update_opportunities"]

    # 5. Immutable facts & objectives preservation
    for fact in proposed.get("add_historical_facts", []):
        if fact not in current_state["important_historical_facts"]:
            current_state["important_historical_facts"].append(fact)

    # 6. Re-assert absolute verified financial values from ERPNext
    current_state["financial_state"] = get_verified_erpnext_financials()
    current_state["company"]["last_updated"] = str(today())

    # Save to Master State
    state_doc = frappe.get_single("Xavirgin Company State")
    new_version = int(state_doc.active_version or 1) + 1
    state_doc.active_version = new_version
    state_doc.last_updated_date = today()
    state_doc.last_updated_time = now_datetime()
    state_doc.last_update_source = f"Applied Update {hist.name}"
    state_doc.last_applied_history = hist.name
    state_doc.last_ai_execution_id = hist.ai_execution_id

    _sync_dict_to_state_doc(state_doc, current_state)
    state_doc.flags.ignore_permissions = True
    state_doc.save()

    # Update History record status
    hist.approval_status = "Applied"
    hist.applied_by = reviewer_user or frappe.session.user
    hist.applied_timestamp = now_datetime()
    hist.new_state_json = json.dumps(current_state, indent=2)
    hist.version = new_version
    hist.flags.ignore_permissions = True
    hist.save()

    frappe.db.commit()
    return True