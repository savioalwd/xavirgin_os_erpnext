frappe.provide("xavirgin_os");

// Global shortcut to inspect full breakdown (Ctrl+Shift+C)
frappe.ui.keys.add_shortcut({
	shortcut: "ctrl+shift+c",
	action: () => {
		frappe.call({
			method: "xavirgin_os.finance.get_xavirgin_liquidity",
			callback(r) {
				if (r.message && r.message.visible) {
					frappe.msgprint({
						title: __("⚡ Xavirgin Cash Meter & Financial Overview"),
						message: `
							<div style="font-family: monospace; line-height: 1.6; font-size: 13px;">
								<p><b>💰 Survival Energy:</b> ${r.message.currency_symbol} ${r.message.formatted_balance}</p>
								<p><b>▲ FY Income (Gain):</b> ${r.message.currency_symbol} ${r.message.formatted_gain}</p>
								<p><b>▼ FY Expenses (Debt):</b> ${r.message.currency_symbol} ${r.message.formatted_debt}</p>
								<p><b>📥 Receivables:</b> ${r.message.currency_symbol} ${r.message.receivables}</p>
								<p><b>📤 Payables:</b> ${r.message.currency_symbol} ${r.message.payables}</p>
								<p><b>🤝 Director Loan:</b> ${r.message.currency_symbol} ${r.message.director_loan}</p>
							</div>
						`,
						indicator: "blue",
					});
				}
			},
		});
	},
	description: __("Toggle Cash Meter Financial HUD"),
});

xavirgin_os.renderCashMeter = function () {
	// If already in the DOM and visible, skip
	if ($("#xavirgin-cash-meter-hud").length) return;

	frappe.call({
		method: "xavirgin_os.finance.get_xavirgin_liquidity",
		callback(r) {
			if (!r.message || !r.message.visible) return;

			const data = r.message;
			let statusColor = "#38bdf8"; // cyan
			let amt = data.amount || 0;

			if (amt < 0) {
				statusColor = "#f87171"; // crisis red
			} else if (amt < 10000) {
				statusColor = "#fbbf24"; // warning amber
			}

			const hudHtml = `
				<div id="xavirgin-cash-meter-hud" class="xavirgin-cyber-meter" title="Click for Financial Breakdown (Ctrl+Shift+C)">
					<div class="hud-status-indicator">
						<span class="status-dot" style="background: ${statusColor}; box-shadow: 0 0 8px ${statusColor};"></span>
					</div>
					<div class="hud-content-wrapper">
						<div class="hud-label-cyber">
							<span>SURVIVAL ENERGY</span>
							<i class="fa fa-bolt" style="color: #fbbf24; font-size: 8px;"></i>
						</div>
						<div class="balance-cyber-value" style="color: ${statusColor};">
							${data.currency_symbol} ${data.formatted_balance}
						</div>
					</div>
					<div class="hud-divider"></div>
					<div class="hud-stats-grid">
						<div class="stat-row" style="color: #34d399;">
							<span class="stat-prefix">▲ GAIN:</span>
							<span>${data.formatted_gain}</span>
						</div>
						<div class="stat-row" style="color: #f87171;">
							<span class="stat-prefix">▼ DEBT:</span>
							<span>${data.formatted_debt}</span>
						</div>
					</div>
				</div>
			`;

			const $hud = $(hudHtml);
			$hud.on("click", () => {
				frappe.ui.keys.get_shortcut("ctrl+shift+c").action();
			});

			// Append directly to <body> so it is completely immune to navbar nesting or overflow
			$("body").append($hud);
		},
	});
};

// Immediate invocation + event listeners for dynamic routes
$(function () {
	setTimeout(xavirgin_os.renderCashMeter, 300);
});
$(document).on("app_ready", () => {
	setTimeout(xavirgin_os.renderCashMeter, 300);
});
$(document).on("page-change", () => {
	setTimeout(xavirgin_os.renderCashMeter, 300);
});