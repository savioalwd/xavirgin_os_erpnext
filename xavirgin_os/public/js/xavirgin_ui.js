frappe.provide("xavirgin_os.ui");

xavirgin_os.ui.iconMap = {
	"Xavirgin Daily POA": "es-line-check-list",
	"Xavirgin GitHub Activity": "branch",
	"Xavirgin Attendance Session": "es-line-clock",
	"Xavirgin Daily Meeting Log": "chat",
	"Xavirgin Leave Request": "calendar",
	"Xavirgin Job Opening": "briefcase",
	"Xavirgin Candidate": "users",
	"Xavirgin Interview": "video",
	"Xavirgin Interview Evaluation": "star",
	"Xavirgin Assessment Template": "file",
	"Xavirgin Offer Letter": "file-text",
	"Xavirgin DMS Folder": "folder-normal",
	"Xavirgin DMS Audit Log": "shield",
	"Xavirgin AI Summary Log": "sparkles",
	"Xavirgin HR Settings": "setting-gear",
	"Xavirgin Organizational Chart": "organization",
	"Interactive Org Chart": "organization"
};

xavirgin_os.ui.applySidebarIcons = function () {
	// Query each sidebar item container using its exact data attributes
	$(".sidebar-item-container").each(function () {
		const $container = $(this);
		const itemName = $container.attr("item-name") || $container.attr("data-id") || "";

		for (const [title, iconSymbol] of Object.entries(xavirgin_os.ui.iconMap)) {
			if (itemName === title || itemName.includes(title)) {
				const $useTag = $container.find(".sidebar-item-icon svg use");
				if ($useTag.length) {
					const currentHref = $useTag.attr("href") || "";
					const targetHref = `#${iconSymbol}`;
					if (currentHref !== targetHref) {
						$useTag.attr("href", targetHref);
						$container.find(".sidebar-item-icon").attr("item-icon", iconSymbol);
					}
				}
				break;
			}
		}
	});
};

$(document).on("app_ready", () => {
	xavirgin_os.ui.applySidebarIcons();
	setInterval(xavirgin_os.ui.applySidebarIcons, 1000);
});

$(document).on("page-change", () => {
	setTimeout(xavirgin_os.ui.applySidebarIcons, 200);
});