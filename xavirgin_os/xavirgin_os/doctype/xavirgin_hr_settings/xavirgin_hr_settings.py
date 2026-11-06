import frappe
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password

DEFAULT_INTERVIEW_INSTRUCTIONS_HTML = (
    "<div style=\"font-family: Arial, sans-serif; font-size: 13px; line-height: 1.6; color: #2d3748;\">"
    "<h4 style=\"color: #0000FF; margin-bottom: 8px;\">📌 Mandatory Online Interview Instructions</h4>"
    "<ol style=\"margin-top: 0; padding-left: 20px;\">"
    "<li><strong>Early Arrival:</strong> Join the meeting at least <strong>5 minutes prior</strong> to the scheduled start time to test audio and camera readiness.</li>"
    "<li><strong>Hardware & Platform:</strong> Join <strong>exclusively via Laptop or Desktop</strong> with a working webcam and microphone. Mobile logins are strictly disallowed unless explicitly pre-approved by HR.</li>"
    "<li><strong>Connectivity:</strong> Ensure a stable broadband/high-speed internet connection in a quiet, well-lit, distraction-free environment.</li>"
    "<li><strong>Screen Sharing & IDE:</strong> Be ready to share your entire desktop screen and demonstrate live problem-solving using your primary local development environment / IDE.</li>"
    "<li><strong>Verification:</strong> Keep a valid government identity card accessible for visual identity verification at the start of the round.</li>"
    "</ol>"
    "</div>"
)


class XavirginHRSettings(Document):
    def get_gemini_credentials(self):
        """Safely decodes and returns the Gemini API key and active model string."""
        api_key = None
        try:
            api_key = get_decrypted_password(
                "Xavirgin HR Settings", "Xavirgin HR Settings", "gemini_api_key", raise_exception=False
            )
        except Exception:
            pass
        if not api_key:
            api_key = self.gemini_api_key

        return {
            "api_key": api_key,
            "model": (self.gemini_model or "").strip() or "gemini-2.5-flash",
            "enable_screening": bool(self.enable_ai_candidate_screening),
            "enable_jd_helper": bool(self.enable_ai_job_description_helper),
            "enable_auto_insights": bool(self.enable_path_ceo_auto_insights),
        }

    def get_github_webhook_secret(self) -> str:
        """Decodes and returns the configured GitHub HMAC secret."""
        try:
            secret = get_decrypted_password(
                "Xavirgin HR Settings", "Xavirgin HR Settings", "github_webhook_secret", raise_exception=False
            )
            if secret:
                return secret.strip()
        except Exception:
            pass
        return (self.github_webhook_secret or "").strip()


@frappe.whitelist()
def get_global_hr_defaults():
    """Whitelisted API endpoint for client scripts and controllers to pull global HR, Interview & Assessment defaults."""
    settings = frappe.get_single("Xavirgin HR Settings")
    return {
        "default_meet_link": settings.default_meet_link or "https://meet.google.com/xzx-icxk-uje",
        "default_meeting_platform": settings.default_meeting_platform or "Google Meet",
        "default_meeting_duration_mins": int(settings.default_meeting_duration_mins or 40),
        "default_interview_instructions": (
            getattr(settings, "default_interview_instructions", None) or DEFAULT_INTERVIEW_INSTRUCTIONS_HTML
        ),
        "default_assessment_template": getattr(settings, "default_assessment_template", None),
        "default_assessment_total_marks": float(getattr(settings, "default_assessment_total_marks", None) or 100.0),
        "default_assessment_criteria_count": int(getattr(settings, "default_assessment_criteria_count", None) or 5),
        "strongly_recommended_threshold_pct": float(
            getattr(settings, "strongly_recommended_threshold_pct", None) or 85.0
        ),
        "recommended_threshold_pct": float(getattr(settings, "recommended_threshold_pct", None) or 65.0),
        "hold_threshold_pct": float(getattr(settings, "hold_threshold_pct", None) or 50.0),
        "internship_required_active_days": int(settings.internship_required_active_days or 90),
        "initial_evaluation_days": int(settings.initial_evaluation_days or 15),
        "default_supervisor": settings.default_supervisor,
        "default_hiring_manager": settings.default_hiring_manager,
        "gemini_model": (settings.gemini_model or "").strip() or "gemini-2.5-flash",
        "poa_base_xp": int(settings.poa_base_xp or 15),
        "poa_duration_bonus_xp": int(settings.poa_duration_bonus_xp or 10),
    }