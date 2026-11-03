import requests
import frappe
from frappe import _


def call_gemini(prompt: str, system_instruction: str = None, temperature: float = 0.7, timeout: int = 30) -> str:
	"""Centralized wrapper for Google Gemini API calls across all Xavirgin OS modules.

	:param prompt: The user/task prompt.
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
	url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

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
		if not candidates or not candidates[0].get("content", {}).get("parts"):
			frappe.throw(_("Gemini returned an empty response or the content was filtered."))

		return candidates[0]["content"]["parts"][0]["text"]

	except requests.exceptions.Timeout:
		frappe.throw(_("Gemini API request timed out after {0} seconds. Please try again.").format(timeout))
	except requests.exceptions.RequestException as e:
		frappe.log_error(frappe.get_traceback(), "Gemini Request Exception")
		frappe.throw(_("Network error connecting to Gemini API: {0}").format(str(e)))
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Gemini Service Failure")
		raise