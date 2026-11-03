import hashlib
import hmac
import json
import frappe
from frappe.utils import getdate, now_datetime


def verify_github_signature(payload_bytes: bytes, secret: str, signature_header: str) -> bool:
	"""Strictly verifies GitHub HMAC-SHA256 webhook signature in constant time."""
	if not secret:
		return True
	if not signature_header:
		return False
	computed = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
	expected = f"sha256={computed}"
	return hmac.compare_digest(expected, signature_header)


def resolve_employee_from_github(github_username: str = "", author_email: str = "") -> str:
	"""3-Tier Employee Mapping for GitHub Contributors:

	1. Match Employee.custom_github_username (exact or full github.com URL).
	2. Match author_email against Employee.company_email, personal_email, or user_id.
	3. Match Xavirgin Candidate.github_url -> converted Employee ID.
	"""
	handle = (github_username or "").strip().lower()
	email = (author_email or "").strip().lower()

	if handle:
		emp = frappe.db.get_value(
			"Employee",
			{"custom_github_username": ["in", [handle, f"https://github.com/{handle}", f"https://github.com/{github_username}"]]},
			"name",
		)
		if not emp:
			emp = frappe.db.get_value(
				"Employee",
				{"custom_github_username": ["like", f"%{handle}%"], "status": "Active"},
				"name",
			)
		if emp:
			return emp

	if email and not email.endswith("@users.noreply.github.com"):
		emp = (
			frappe.db.get_value("Employee", {"company_email": email, "status": "Active"}, "name")
			or frappe.db.get_value("Employee", {"personal_email": email, "status": "Active"}, "name")
			or frappe.db.get_value("Employee", {"user_id": email, "status": "Active"}, "name")
		)
		if emp:
			return emp

	if handle:
		cand_emp = frappe.db.get_value(
			"Xavirgin Candidate",
			{"github_url": ["like", f"%{handle}%"], "employee": ["is", "set"]},
			"employee",
		)
		if cand_emp:
			return cand_emp

	return None


@frappe.whitelist(allow_guest=True)
def webhook():
	"""Idempotent GitHub Organization/Repository Webhook Receiver.

	URL: /api/method/xavirgin_os.github.webhook
	"""
	request = frappe.local.request
	payload_bytes = request.get_data()
	headers = request.headers

	sig_256 = headers.get("X-Hub-Signature-256") or headers.get("X-HUB-SIGNATURE-256")
	event_type = headers.get("X-GitHub-Event") or headers.get("X-Github-Event") or "ping"
	delivery_id = headers.get("X-GitHub-Delivery") or headers.get("X-Github-Delivery") or frappe.generate_hash(length=20)

	settings = frappe.get_single("Xavirgin HR Settings")
	secret = settings.get_github_webhook_secret()

	if secret and not verify_github_signature(payload_bytes, secret, sig_256):
		frappe.local.response["http_status_code"] = 403
		return {"status": "error", "message": "Invalid X-Hub-Signature-256"}

	if event_type == "ping":
		return {"status": "success", "message": "Xavirgin OS GitHub Webhook Active"}

	# Idempotency Check: Never process duplicate webhook deliveries
	if frappe.db.exists("Xavirgin GitHub Activity", {"delivery_id": delivery_id}):
		return {"status": "duplicate_ignored", "delivery_id": delivery_id}

	try:
		payload = json.loads(payload_bytes.decode("utf-8")) if payload_bytes else {}
	except Exception:
		payload = {}

	sender_login = (payload.get("sender") or {}).get("login") or ""
	repo_name = (payload.get("repository") or {}).get("full_name") or (payload.get("repository") or {}).get("name") or "Xavirgin"

	author_email = ""
	action = payload.get("action") or ""
	branch = ""
	reference_id = ""
	commit_count = 0
	summary = ""
	xp_earned = 0

	if event_type == "push":
		ref = payload.get("ref") or ""
		branch = ref.replace("refs/heads/", "")
		commits = payload.get("commits") or []
		commit_count = len(commits)
		if commit_count == 0:
			return {"status": "ignored", "reason": "Empty push"}
		head_commit = payload.get("head_commit") or commits[-1]
		author_email = (head_commit.get("author") or {}).get("email") or ""
		reference_id = (head_commit.get("id") or "")[:7]
		msg_first_line = (head_commit.get("message") or "").splitlines()[0]
		action = "pushed"
		summary = f"Pushed {commit_count} commit(s) to {branch}: '{msg_first_line}' [{reference_id}]"
		xp_earned = int(settings.commit_xp or 5)

	elif event_type == "pull_request":
		pr = payload.get("pull_request") or {}
		pr_num = payload.get("number") or pr.get("number")
		pr_title = pr.get("title") or ""
		merged = bool(pr.get("merged"))
		branch = (pr.get("head") or {}).get("ref") or ""
		reference_id = f"PR #{pr_num}"
		if action == "closed" and merged:
			action = "merged"
			xp_earned = int(settings.pr_merged_xp or 50)
		elif action == "opened":
			xp_earned = int(settings.pr_opened_xp or 15)
		summary = f"PR #{pr_num} '{pr_title}' {action} ({repo_name})"

	elif event_type == "pull_request_review":
		review = payload.get("review") or {}
		pr = payload.get("pull_request") or {}
		pr_num = pr.get("number")
		reference_id = f"PR #{pr_num} Review"
		summary = f"Reviewed PR #{pr_num} ({review.get('state', 'reviewed')}) in {repo_name}"
		xp_earned = int(settings.issue_created_xp or 10)

	elif event_type == "issues":
		issue = payload.get("issue") or {}
		issue_num = issue.get("number")
		issue_title = issue.get("title") or ""
		reference_id = f"Issue #{issue_num}"
		summary = f"Issue #{issue_num} '{issue_title}' {action} ({repo_name})"
		if action in ("opened", "closed"):
			xp_earned = int(settings.issue_created_xp or 10)
	else:
		return {"status": "ignored", "event": event_type}

	employee = resolve_employee_from_github(sender_login, author_email)

	doc = frappe.get_doc({
		"doctype": "Xavirgin GitHub Activity",
		"delivery_id": delivery_id,
		"employee": employee,
		"github_username": sender_login or "unknown",
		"author_email": author_email,
		"event_type": event_type,
		"action": action,
		"repository": repo_name,
		"branch": branch,
		"reference_id": reference_id,
		"commit_count": commit_count,
		"xp_awarded": xp_earned if employee else 0,
		"activity_date": getdate(),
		"event_timestamp": now_datetime(),
		"summary": summary,
		"raw_payload": json.dumps(payload, indent=2),
	}).insert(ignore_permissions=True)

	frappe.db.commit()
	return {
		"status": "success",
		"activity_id": doc.name,
		"employee": employee,
		"xp_awarded": doc.xp_awarded,
		"summary": summary,
	}