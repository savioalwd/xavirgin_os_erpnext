frappe.provide("xavirgin_os.ui");

$(document).on("app_ready", () => {
	// Dynamically load Feather Icons CDN if not present
	if (!window.feather) {
		const script = document.createElement("script");
		script.src = "https://unpkg.com/feather-icons";
		script.onload = () => {
			window.feather.replace();
			setInterval(() => window.feather.replace(), 2000);
		};
		document.head.appendChild(script);
	}

	// Custom branding badge on sidebar header
	setTimeout(() => {
		const $brand = $(".standard-sidebar .board-dropdown, .navbar-brand");
		if ($brand.length && !$("#xavirgin-brand-glow").length) {
			$brand.append('<span id="xavirgin-brand-glow" class="badge bg-purple ms-2" style="background: linear-gradient(135deg, #7c3aed, #d926ff); font-size: 9px;">XAVIRGIN OS v16</span>');
		}
	}, 1500);
});