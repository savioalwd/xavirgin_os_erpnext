import json
import re
import requests
import frappe
from frappe import _
from frappe.utils import getdate, today


def call_gemini(prompt: str, system_instruction: str = None, temperature: float = 0.7, timeout: int = 45) -> str:
	"""Centralized wrapper for Google Gemini API calls across all Xavirgin OS modules."""
	settings = frappe.get_single("Xavirgin HR Settings")
	creds = settings.get_gemini_credentials()

	api_key = creds.get("api_key")
	if not api_key:
		frappe.throw(_("Gemini API Key is not configured in Xavirgin HR Settings."))

	model = creds.get("model") or "gemini-2.5-flash"
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
		frappe.throw(_("Gemini API request timed out after {0} seconds. Please try again.").format(timeout))
	except requests.exceptions.RequestException as e:
		frappe.log_error(frappe.get_traceback(), "Gemini Request Exception")
		frappe.throw(_("Network error connecting to Gemini API: {0}").format(str(e)))
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Gemini Service Failure")
		raise


def call_gemini_json(prompt: str, system_instruction: str = None, timeout: int = 45):
	"""Calls Gemini API and guarantees a parsed Python dictionary/list, stripping markdown wrappers."""
	sys_prompt = (system_instruction or "") + "\nRespond ONLY with valid JSON. Never enclose response in markdown backticks."
	raw_output = call_gemini(prompt=prompt, system_instruction=sys_prompt, temperature=0.1, timeout=timeout)

	clean_json = raw_output.strip()
	if clean_json.startswith("```"):
		clean_json = clean_json.split("\n", 1)[1]
		if clean_json.endswith("```"):
			clean_json = clean_json.rsplit("```", 1)[0]
	clean_json = clean_json.strip()

	try:
		return json.loads(clean_json)
	except Exception as exc:
		frappe.log_error(f"Raw Output: {raw_output}\nError: {str(exc)}", "Gemini JSON Parse Error")
		frappe.throw(_("Failed to parse Gemini response as JSON: {0}").format(str(exc)))


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
	Employee: {poa.employee_name} ({poa.designation} - {poa.department})
	Date: {poa.poa_date}
	Attendance Status: {poa.attendance_status} ({poa.attendance_hours_logged}h logged)
	GitHub Contributions Today: {poa.github_contributions_summary or 'None'}
	Tasks: {json.dumps(tasks_data, indent=2)}

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

	return clean_html


def generate_organization_path_insight(target_date: str = None):
	"""Generates the full Organization-wide 'Path' Autonomous CEO Daily Report and stores it in Xavirgin AI Summary Log."""
	t_date = getdate(target_date or today())

	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "department", "designation", "custom_is_team_lead", "custom_xp_points"],
	)
	attendances = frappe.get_all(
		"Xavirgin Attendance Session",
		filters={"attendance_date": t_date},
		fields=["employee", "employee_name", "worked_hours", "status", "day_classification"],
	)
	att_emp_ids = {a.employee for a in attendances}

	teams_payload = {}
	absentees = []
	for emp in employees:
		dept_name = emp.department or "Unassigned"
		teams_payload.setdefault(dept_name, []).append({
			"id": emp.name,
			"name": emp.employee_name,
			"designation": emp.designation,
			"is_team_lead": bool(emp.custom_is_team_lead),
			"xp_points": int(emp.custom_xp_points or 0),
		})
		if emp.name not in att_emp_ids:
			absentees.append(f"{emp.employee_name} ({emp.name})")

	poas = frappe.get_all(
		"Xavirgin Daily POA",
		filters={"poa_date": t_date},
		fields=["name", "employee", "employee_name", "department", "status", "total_actual_hours", "completed_tasks_count", "blocked_tasks_count", "blockers_summary"],
	)
	poa_payload = []
	for p in poas:
		tasks = frappe.get_all(
			"Xavirgin POA Task",
			filters={"parent": p.name},
			fields=["task_title", "task_type", "status", "actual_hours", "github_ref", "blocker_reason"],
		)
		poa_payload.append({
			"poa_id": p.name,
			"employee": p.employee_name,
			"department": p.department,
			"poa_status": p.status,
			"tasks": tasks,
		})

	github_logs = frappe.get_all(
		"Xavirgin GitHub Activity",
		filters={"activity_date": t_date},
		fields=["employee_name", "github_username", "event_type", "action", "repository", "summary"],
	)

	past_insights = frappe.get_all(
		"Xavirgin AI Summary Log",
		filters={"scope_type": "Organization - Path CEO", "summary_date": ["<", t_date]},
		fields=["summary_date", "summary_metrics", "most_important_action"],
		order_by="summary_date desc",
		limit=3,
	)
	historical_context = "\n".join(
		[f"- Date {p.summary_date}: {p.summary_metrics} | Next Action: {p.most_important_action or 'N/A'}" for p in past_insights]
	) or "No prior historical logs."

	total_done = sum(int(p.completed_tasks_count or 0) for p in poas)
	total_blocked = sum(int(p.blocked_tasks_count or 0) for p in poas)
	total_poa_hours = round(sum(float(p.total_actual_hours or 0) for p in poas), 2)

	metrics_text = (
		f"Date: {t_date} | Active Roster: {len(employees)} | Absentees: {len(absentees)} | "
		f"POAs Filed: {len(poas)} (Tasks Done: {total_done}, Blocked: {total_blocked}) | "
		f"Task Hours: {total_poa_hours}h | GitHub Events: {len(github_logs)}"
	)

	raw_payload_dict = {
		"date": str(t_date),
		"absentees": absentees,
		"teams": teams_payload,
		"attendance": attendances,
		"poas": poa_payload,
		"github": github_logs,
		"historical_context": historical_context,
	}
	raw_payload_json = json.dumps(raw_payload_dict, indent=2, default=str)

	system_prompt = """You are "Path" (Paatha), strategic AI autonomous CEO of XAVIRGIN. You are an operational intelligence system designed to help XAVIRGIN survive, execute, generate revenue, and avoid wasting time, engineering capacity, founder attention, team attention, and cash.
XAVIRGIN operates under a "ZERO ENERGY" model:
- Minimal spending. Every hour must produce measurable progress.
- Attendance, meetings, writing tasks, creating PRs/issues, or earning XP are NOT automatically productivity.
- Core directive: SURVIVE -> EXECUTE -> BUILD -> DELIVER -> GENERATE REVENUE -> SCALE.
- Treat supplied data as the ONLY authoritative source. Do NOT invent commits, PRs, hours, leave, or XP.
- Output strictly valid HTML with inline CSS. First character MUST be "<" and last character MUST be ">".
- Include at the end inside a Bottom Line block:
  <p><strong>Did XAVIRGIN move forward today?</strong> [YES / PARTIALLY / NO]</p>
  <p><strong>Biggest Risk:</strong> [One clear sentence]</p>
  <p><strong>Most Important Action Tomorrow:</strong> [One clear action]</p>"""

	prev_versions = frappe.db.count(
		"Xavirgin AI Summary Log",
		{"summary_date": t_date, "scope_type": "Organization - Path CEO"},
	)

	try:
		ai_analysis = call_gemini(
			prompt=f"TODAY'S TELEMETRY PAYLOAD:\n{raw_payload_json}",
			system_instruction=system_prompt,
			temperature=0.3,
			timeout=60,
		)
		ai_analysis = ai_analysis.replace("```html", "").replace("```", "").strip()
		status = "Generated"
		error_msg = ""
	except Exception as exc:
		ai_analysis = f"<p style='color:#dc2626;'>Path AI Generation Failed: {str(exc)}</p>"
		status = "Failed"
		error_msg = str(exc)

	did_move = "PARTIALLY"
	if "move forward today?</strong> YES" in ai_analysis or "move forward today? YES" in ai_analysis:
		did_move = "YES"
	elif "move forward today?</strong> NO" in ai_analysis or "move forward today? NO" in ai_analysis:
		did_move = "NO"

	risk_match = re.search(r"<strong>Biggest Risk:<\/strong>\s*(.*?)(<\/p>|<br\/?>|\n)", ai_analysis, re.IGNORECASE | re.DOTALL)
	action_match = re.search(r"<strong>Most Important Action Tomorrow:<\/strong>\s*(.*?)(<\/p>|<br\/?>|\n)", ai_analysis, re.IGNORECASE | re.DOTALL)

	doc = frappe.get_doc({
		"doctype": "Xavirgin AI Summary Log",
		"summary_date": t_date,
		"scope_type": "Organization - Path CEO",
		"status": status,
		"version": prev_versions + 1,
		"did_company_move_forward": did_move,
		"summary_metrics": metrics_text,
		"biggest_risk": risk_match.group(1).strip() if risk_match else "",
		"most_important_action": action_match.group(1).strip() if action_match else "",
		"ai_html_report": ai_analysis,
		"raw_input_payload": raw_payload_json,
		"error_log": error_msg,
	}).insert(ignore_permissions=True)

	frappe.db.commit()
	return doc

@frappe.whitelist()
def secure_download_dms_file(file_name: str):
	"""Securely streams a private DMS file attachment after verifying folder read permissions."""
	file_doc = frappe.get_doc("Xavirgin DMS File", file_name)
	if not file_doc or not file_doc.folder:
		frappe.throw(_("File record not found."))

	from xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder import user_has_folder_access
	if not user_has_folder_access(file_doc.folder):
		frappe.throw(_("Access Denied: You do not have permission to access this file."))

	file_url = file_doc.file_attachment
	if not file_url:
		frappe.throw(_("No file attachment found on this record."))

	# Resolve file path on disk
	site_path = frappe.get_site_path()
	relative_path = file_url.lstrip("/files/").lstrip("/private/files/")
	
	import os
	absolute_path = os.path.join(site_path, "private", "files", relative_path)
	if not os.path.exists(absolute_path):
		absolute_path = os.path.join(site_path, "public", "files", relative_path)

	if not os.path.exists(absolute_path):
		frappe.throw(_("File missing from server storage."))

	# Log audit event
	frappe.get_doc({
		"doctype": "Xavirgin DMS Audit Log",
		"timestamp": now_datetime(),
		"user": frappe.session.user,
		"action_type": "Download File",
		"folder": file_doc.folder,
		"file_title": file_doc.title,
		"ip_address": frappe.local.request.remote_addr if frappe.local.request else "127.0.0.1",
	}).insert(ignore_permissions=True)
	frappe.db.commit()

	with open(absolute_path, "rb") as f:
		file_content = f.read()

	frappe.local.response.filename = file_url.split("/")[-1]
	frappe.local.response.filecontent = file_content
	frappe.local.response.type = "download"


@frappe.whitelist()
def reveal_dms_credential(file_name: str):
	"""Safely decrypts and returns credential details for authorized users, logging an audit trail."""
	file_doc = frappe.get_doc("Xavirgin DMS File", file_name)
	if not file_doc or file_doc.item_type != "Login Credential":
		frappe.throw(_("Invalid credential record."))

	from xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder import user_has_folder_access
	if not user_has_folder_access(file_doc.folder):
		frappe.throw(_("Access Denied: You do not have permission to view credentials in this folder."))

	password = ""
	try:
		password = frappe.utils.password.get_decrypted_password("Xavirgin DMS File", file_doc.name, "credential_password")
	except Exception:
		password = file_doc.credential_password

	# Log audit event
	frappe.get_doc({
		"doctype": "Xavirgin DMS Audit Log",
		"timestamp": now_datetime(),
		"user": frappe.session.user,
		"action_type": "Reveal Credential",
		"folder": file_doc.folder,
		"file_title": file_doc.title,
		"ip_address": frappe.local.request.remote_addr if frappe.local.request else "127.0.0.1",
	}).insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		"title": file_doc.title,
		"url": file_doc.credential_url,
		"username": file_doc.credential_username,
		"password": password,
		"notes": file_doc.notes,
	}