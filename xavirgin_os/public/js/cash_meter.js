frappe.provide("xavirgin_os");

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
								<p><b>💰 Survival Energy (Cash + Bank):</b> ${r.message.currency_symbol} ${r.message.formatted_balance}</p>
								<p><b>▲ FY Income (Gain):</b> ${r.message.currency_symbol} ${r.message.formatted_gain}</p>
								<p><b>▼ FY Expenses (Debt):</b> ${r.message.currency_symbol} ${r.message.formatted_debt}</p>
								<p><b>📥 Outstanding Receivables:</b> ${r.message.currency_symbol} ${r.message.receivables}</p>
								<p><b>📤 Outstanding Payables:</b> ${r.message.currency_symbol} ${r.message.payables}</p>
								<p><b>🤝 Director Loans Outstanding:</b> ${r.message.currency_symbol} ${r.message.director_loan}</p>
							</div>
						`,
						indicator: "blue",
					});
				} else {
					frappe.show_alert({ message: __("Financial telemetry restricted to authorized roles."), indicator: "red" });
				}
			},
		});
	},
	description: __("Toggle Cash Meter Financial HUD"),
});

$(document).on("app_ready", () => {
	frappe.call({
		method: "xavirgin_os.finance.get_xavirgin_liquidity",
		callback(r) {
			if (r.message && r.message.visible) {
				const data = r.message;
				let statusClass = "xavirgin-safe";
				let pulseClass = "pulse-safe";
				let amt = data.amount || 0;

				if (amt < 0) {
					statusClass = "xavirgin-crisis";
					pulseClass = "pulse-crisis";
				} else if (amt < 10000) {
					statusClass = "xavirgin-warning";
					pulseClass = "pulse-warning";
				}

				const $hud = $(`
					<div class="xavirgin-cyber-meter d-flex align-items-center gap-2 px-3 py-1" title="Click for Detailed Financial Breakdown (Ctrl+Shift+C)">
						<div class="hud-status-indicator">
							<span class="pulse-ring ${pulseClass}"></span>
							<span class="status-dot ${statusClass}"></span>
						</div>
						<div class="hud-content-wrapper d-flex flex-column align-items-center">
							<div class="d-flex align-items-center gap-1">
								<span class="hud-label-cyber">SURVIVAL ENERGY</span>
								<i class="fa fa-bolt hud-icon-bolt"></i>
							</div>
							<div class="hud-value-container">
								<span class="balance-cyber-value ${statusClass}">${data.currency_symbol} ${data.formatted_balance}</span>
							</div>
						</div>
						<div class="hud-divider"></div>
						<div class="hud-stats-grid d-flex flex-column justify-content-center">
							<div class="stat-row text-neon-green">
								<span class="stat-prefix">▲ GAIN:</span>
								<span class="stat-num">${data.formatted_gain}</span>
							</div>
							<div class="stat-row text-neon-red">
								<span class="stat-prefix">▼ DEBT:</span>
								<span class="stat-num">${data.formatted_debt}</span>
							</div>
						</div>
					</div>
				`);

				$hud.on("click", () => {
					frappe.ui.keys.get_shortcut("ctrl+shift+c").action();
				});

				// Mount into Frappe navbar
				if ($(".navbar .navbar-collapse").length) {
					$(".navbar .navbar-collapse").prepend($hud);
				} else {
					$("header.navbar").append($hud);
				}
			}
		},
	});
});