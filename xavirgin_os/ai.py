import json
import requests
import frappe
from frappe import _


def call_gemini(prompt: str, system_instruction: str = None, temperature: float = 0.7, timeout: int = 30) -> str:
	"""Centralized wrapper for Google Gemini API calls across all Xavirgin OS modules.

	:param prompt: The user prompt.
	:param system_instruction: Optional system instruction for the model.
	:param temperature: Sampling temperature (0.0 to 2.0).
	:param timeout: Request timeout in seconds.
	:return: Generated text response.
	"""
	settings = frappe.get_single("Xavirgin HR Settings")
	creds = settings.get_gemini_credentials()

	api_key = creds.get("api_key")
	if not api_key:
		frappe.throw(_("Gemini API Key is not configured in Xavirgin HR Settings."))

	model = creds.get("model") or "gemini-2.5-flash"
	url = f"[https://generativelanguage.googleapis.com/v1beta/models/](https://generativelanguage.googleapis.com/v1beta/models/){model}:generateContent?key={api_key}"

	headers = {"Content-Type": "application/json"}
	payload = {
		"contents": [{"parts": [{"text": prompt}]}],
		"generationConfig": {
			"temperature": temperature
		}
	}

	if system_instruction:
		payload["systemInstruction"] = {
			"parts": [{"text": system_instruction}]
		}

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


def call_gemini_json(prompt: str, system_instruction: str = None, timeout: int = 30):
	"""Calls Gemini API and guarantees a parsed Python dictionary/list, stripping any markdown wrappers.

	:param prompt: Prompt requesting JSON output.
	:param system_instruction: System prompt enforcing JSON response.
	:return: Parsed Python dict or list.
	"""
	sys_prompt = (system_instruction or "") + "\nRespond ONLY with valid JSON. Never enclose response in markdown backticks or explanations."
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