import frappe
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password


class XavirginHRSettings(Document):
	def get_gemini_credentials(self):
		"""Safely decodes and returns the Gemini API key and active model name."""
		api_key = None
		try:
			api_key = get_decrypted_password("Xavirgin HR Settings", "Xavirgin HR Settings", "gemini_api_key")
		except Exception:
			api_key = self.gemini_api_key

		return {
			"api_key": api_key,
			"model": self.gemini_model or "gemini-3.8-flash",
			"enable_screening": bool(self.enable_ai_candidate_screening),
			"enable_jd_helper": bool(self.enable_ai_job_description_helper),
		}


@frappe.whitelist()
def get_global_hr_defaults():
	"""Whitelisted API endpoint for client scripts to pull intelligent fallbacks."""
	settings = frappe.get_single("Xavirgin HR Settings")
	return {
		"default_meet_link": settings.default_meet_link,
		"default_meeting_platform": settings.default_meeting_platform,
		"default_meeting_duration_mins": settings.default_meeting_duration_mins,
		"internship_required_active_days": settings.internship_required_active_days or 90,
		"initial_evaluation_days": settings.initial_evaluation_days or 15,
		"default_supervisor": settings.default_supervisor,
		"default_hiring_manager": settings.default_hiring_manager,
		"gemini_model": settings.gemini_model or "gemini-3.8-flash",
	}