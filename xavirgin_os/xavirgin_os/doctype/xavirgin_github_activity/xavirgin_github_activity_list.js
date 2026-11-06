frappe.listview_settings["Xavirgin GitHub Activity"] = {
    add_fields: [
        "employee",
        "employee_name",
        "department",
        "github_username",
        "event_type",
        "action",
        "repository",
        "branch",
        "summary",
        "reference_id",
        "commit_count",
        "activity_date",
        "event_timestamp",
        "xp_awarded",
    ],

    onload(listview) {
        listview._xav_gh_tab = "employees"; // employees | repositories | webhooks
        listview._xav_range = "7d"; // today | yesterday | 7d | 30d | custom
        listview._xav_start_date = "";
        listview._xav_end_date = "";
        listview._xav_dept = "";
        listview._xav_repo = "";
        listview._xav_search = "";
        listview._xav_show_table = false;

        listview.toggle_standard_table = function (show) {
            const $tbl = listview.page.wrapper.find(
                ".result-list, .frappe-list, .list-row-container, .list-paging-area, .standard-filter-section, .filter-section"
            );
            if (show) $tbl.show();
            else $tbl.hide();
        };

        if (!listview.page.wrapper.find(".xav-github-activity-dashboard").length) {
            const $dash = $(`<div class="xav-github-activity-dashboard" style="padding: 12px 15px 4px 15px;"></div>`);
            listview.page.main.prepend($dash);
        }

        listview.refresh_github_dashboard = function () {
            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_github_activity.xavirgin_github_activity.get_github_activity_dashboard",
                args: {
                    date_range: listview._xav_range,
                    start_date: listview._xav_start_date,
                    end_date: listview._xav_end_date,
                    department: listview._xav_dept,
                    repository: listview._xav_repo,
                    search_text: listview._xav_search,
                },
                callback(r) {
                    if (r.message) {
                        listview.render_github_dashboard(r.message);
                    }
                },
            });
        };

        listview.render_github_dashboard = function (data) {
            const $container = listview.page.wrapper.find(".xav-github-activity-dashboard");
            if (!$container.length) return;

            listview.toggle_standard_table(listview._xav_show_table);

            const k = data.kpis || {};
            const opts = data.filter_options || {};
            const tab = listview._xav_gh_tab || "employees";

            const kpiBox = (label, val, sub, bg, color) => `
                <div style="background:${bg}; border-radius:8px; padding:8px 12px; min-width:120px; flex:1;">
                    <div style="font-size:18px; font-weight:800; color:${color}; line-height:1.2;">${val}</div>
                    <div style="font-size:11px; font-weight:700; color:#334155;">${label}</div>
                    <div style="font-size:9px; color:#64748b;">${sub}</div>
                </div>`;

            let bodyHtml = "";

            if (tab === "employees") {
                const empCards = (data.employees || [])
                    .map((e) => {
                        const recentHtml = (e.recent_events || [])
                            .map(
                                (re) => `
                            <div style="font-size:11px; padding:5px 8px; background:#f8fafc; border-left:3px solid #2563eb; margin-bottom:4px; border-radius:4px;">
                                <div style="display:flex; justify-content:space-between; font-weight:700; color:#0f172a;">
                                    <span>
                                        [${frappe.utils.escape_html(re.event_type)}] ${frappe.utils.escape_html(re.repository)}
                                        ${re.branch ? `<span style="color:#64748b; font-weight:600;">(${frappe.utils.escape_html(re.branch)})</span>` : ""}
                                    </span>
                                    <span style="font-size:10px; color:#64748b;">${re.time}</span>
                                </div>
                                <div style="color:#475569; display:flex; justify-content:space-between; align-items:center; gap:6px; margin-top:2px;">
                                    <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                                        ${re.sha ? `<code>${frappe.utils.escape_html(re.sha)}</code> ` : ""}${frappe.utils.escape_html(re.summary)}
                                    </span>
                                    ${re.url ? `<a href="${re.url}" target="_blank" style="font-size:10px; font-weight:700; color:#2563eb; white-space:nowrap;">GitHub ↗</a>` : ""}
                                </div>
                            </div>`
                            )
                            .join("");

                        return `
                        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:12px 14px; display:flex; flex-direction:column; justify-content:space-between; box-shadow:0 1px 3px rgba(0,0,0,0.03);">
                            <div>
                                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px;">
                                    <div>
                                        <a href="/app/employee/${encodeURIComponent(e.employee)}" style="font-size:13px; font-weight:800; color:#0f172a; text-decoration:none;">
                                            👤 ${frappe.utils.escape_html(e.employee_name)}
                                        </a>
                                        <div style="font-size:11px; color:#64748b;">
                                            <a href="https://github.com/${encodeURIComponent(e.github_username)}" target="_blank" style="color:#2563eb; font-weight:600;">@${frappe.utils.escape_html(e.github_username)}</a>
                                            • ${frappe.utils.escape_html(e.department)}
                                        </div>
                                    </div>
                                    <span style="background:#dcfce7; color:#166534; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700;">
                                        ⚡ +${e.xp_earned} XP
                                    </span>
                                </div>

                                <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:4px; text-align:center; background:#f8fafc; padding:6px; border-radius:6px; font-size:11px; margin-bottom:8px;">
                                    <div><div style="font-weight:800; color:#2563eb;">${e.commits}</div><div style="font-size:9px; color:#64748b;">Commits</div></div>
                                    <div><div style="font-weight:800; color:#7c3aed;">${e.prs}</div><div style="font-size:9px; color:#64748b;">PRs</div></div>
                                    <div><div style="font-weight:800; color:#d97706;">${e.issues}</div><div style="font-size:9px; color:#64748b;">Issues</div></div>
                                    <div><div style="font-weight:800; color:#0f172a;">${e.repo_count}</div><div style="font-size:9px; color:#64748b;">Repos</div></div>
                                </div>

                                <div>
                                    ${recentHtml || `<div style="font-size:11px; color:#94a3b8; padding:8px 0;">No webhook events in selected period.</div>`}
                                </div>
                            </div>
                            <div style="display:flex; justify-content:space-between; align-items:center; font-size:10px; color:#64748b; padding-top:6px; border-top:1px solid #f1f5f9; margin-top:6px;">
                                <span>Last Active: ${e.latest_timestamp}</span>
                                <a href="/app/xavirgin-daily-poa?employee=${encodeURIComponent(e.employee)}" style="font-weight:700; color:#2563eb;">View Daily POAs →</a>
                            </div>
                        </div>`;
                    })
                    .join("");

                bodyHtml = `
                <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(310px, 1fr)); gap:12px;">
                    ${empCards || `<div class="text-muted" style="padding:16px;">No developer GitHub activity found for the selected filter.</div>`}
                </div>`;
            } else if (tab === "repositories") {
                const repoCards = (data.repositories || [])
                    .map((r) => {
                        const commitsHtml = (r.recent_commits || [])
                            .map(
                                (c) => `
                            <div style="font-size:11px; padding:4px 6px; background:#f8fafc; border-radius:4px; margin-bottom:4px;">
                                <code>#${frappe.utils.escape_html(c.sha)}</code>
                                <strong>${frappe.utils.escape_html(c.author)}</strong>
                                ${c.branch ? `<span style="color:#64748b;">(${frappe.utils.escape_html(c.branch)})</span>` : ""}:
                                <span style="color:#334155;">${frappe.utils.escape_html(c.summary)}</span>
                            </div>`
                            )
                            .join("");

                        return `
                        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:12px 14px;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                                <a href="https://github.com/${frappe.utils.escape_html(r.repository)}" target="_blank" style="font-size:14px; font-weight:800; color:#2563eb; text-decoration:none;">
                                    📦 ${frappe.utils.escape_html(r.repository)} ↗
                                </a>
                                <span style="background:#e0e7ff; color:#3730a3; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700;">
                                    ${r.total_events} Events
                                </span>
                            </div>
                            <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:4px; text-align:center; background:#f8fafc; padding:6px; border-radius:6px; font-size:11px; margin-bottom:8px;">
                                <div><div style="font-weight:800; color:#0f172a;">${r.contributor_count}</div><div style="font-size:9px; color:#64748b;">Devs</div></div>
                                <div><div style="font-weight:800; color:#2563eb;">${r.commits}</div><div style="font-size:9px; color:#64748b;">Commits</div></div>
                                <div><div style="font-weight:800; color:#7c3aed;">${r.prs}</div><div style="font-size:9px; color:#64748b;">PRs</div></div>
                                <div><div style="font-weight:800; color:#d97706;">${r.issues}</div><div style="font-size:9px; color:#64748b;">Issues</div></div>
                            </div>
                            ${commitsHtml}
                            <div style="font-size:10px; color:#64748b; margin-top:6px;">Last Activity: ${r.last_activity}</div>
                        </div>`;
                    })
                    .join("");

                bodyHtml = `
                <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(310px, 1fr)); gap:12px;">
                    ${repoCards || `<div class="text-muted" style="padding:16px;">No repository events found in this period.</div>`}
                </div>`;
            } else if (tab === "webhooks") {
                const whRows = (data.webhooks || [])
                    .map((w) => {
                        const stStyle =
                            w.status === "Processed"
                                ? { bg: "#dcfce7", text: "#166534" }
                                : w.status === "Unmapped"
                                ? { bg: "#fef9c3", text: "#854d0e" }
                                : { bg: "#fee2e2", text: "#991b1b" };

                        return `
                        <tr class="xav-wh-row" data-name="${frappe.utils.escape_html(w.name)}" style="cursor:pointer;">
                            <td style="font-size:11px; white-space:nowrap;">${w.timestamp}</td>
                            <td>
                                <span style="background:#e0e7ff; color:#3730a3; padding:2px 7px; border-radius:999px; font-size:10px; font-weight:700;">
                                    ${frappe.utils.escape_html(w.event_type)} ${w.action ? `(${frappe.utils.escape_html(w.action)})` : ""}
                                </span>
                            </td>
                            <td style="font-weight:700; font-size:12px;">
                                ${frappe.utils.escape_html(w.repository)}
                                ${w.branch ? `<div style="font-size:10px; color:#64748b;">🌿 ${frappe.utils.escape_html(w.branch)}</div>` : ""}
                            </td>
                            <td style="font-size:12px;">
                                <code>@${frappe.utils.escape_html(w.github_username)}</code>
                                ${
                                    w.employee_name
                                        ? `<div style="font-size:10px; color:#15803d; font-weight:700;">👤 ${frappe.utils.escape_html(w.employee_name)}</div>`
                                        : `<div style="font-size:10px; color:#d97706; font-weight:700;">⚠️ Unmapped Handle</div>`
                                }
                            </td>
                            <td style="font-size:11px;">
                                ${w.short_sha ? `<code>${frappe.utils.escape_html(w.short_sha)}</code> ` : ""}
                                ${frappe.utils.escape_html(w.summary)}
                                ${w.event_url ? ` <a href="${w.event_url}" target="_blank" class="xav-wh-ext-link" style="font-weight:700; color:#2563eb;">↗</a>` : ""}
                            </td>
                            <td>
                                <span style="background:${stStyle.bg}; color:${stStyle.text}; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700;">
                                    ${w.status}
                                </span>
                            </td>
                        </tr>`;
                    })
                    .join("");

                bodyHtml = `
                <div style="overflow-x:auto;">
                    <table class="table table-bordered" style="background:#fff; font-size:12px; margin-bottom:0;">
                        <thead><tr style="background:#f8fafc;"><th>Timestamp</th><th>Event</th><th>Repository / Branch</th><th>Sender / Employee</th><th>Commit / PR Summary</th><th>Status</th></tr></thead>
                        <tbody>${whRows || `<tr><td colspan="6" class="text-center text-muted">No webhook events recorded in this period.</td></tr>`}</tbody>
                    </table>
                </div>`;
            }

            const tabBtn = (id, label, count) => {
                const act = tab === id;
                return `<button class="btn btn-xs xav-gh-tab-btn" data-tab="${id}" style="font-weight:700; border-radius:999px; padding:4px 12px; background:${act ? "#2563eb" : "#f1f5f9"}; color:${act ? "#fff" : "#334155"}; border:none;">
                    ${label} (${count})
                </button>`;
            };

            const rangeBtn = (rKey, label) => {
                const act = listview._xav_range === rKey;
                return `<button class="btn btn-xs xav-gh-range-btn" data-range="${rKey}" style="font-weight:700; background:${act ? "#0f172a" : "#f8fafc"}; color:${act ? "#fff" : "#334155"}; border:1px solid #cbd5e1;">${label}</button>`;
            };

            const deptOpts = [`<option value="">All Departments</option>`]
                .concat(
                    (opts.departments || []).map(
                        (d) => `<option value="${frappe.utils.escape_html(d)}" ${listview._xav_dept === d ? "selected" : ""}>${frappe.utils.escape_html(d)}</option>`
                    )
                )
                .join("");

            const repoOpts = [`<option value="">All Repositories</option>`]
                .concat(
                    (opts.repositories || []).map(
                        (rp) => `<option value="${frappe.utils.escape_html(rp)}" ${listview._xav_repo === rp ? "selected" : ""}>${frappe.utils.escape_html(rp)}</option>`
                    )
                )
                .join("");

            const html = `
            <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:14px 16px; margin-bottom:10px; box-shadow:0 1px 4px rgba(0,0,0,0.03);">
                <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px; margin-bottom:12px;">
                    <div style="display:flex; flex-wrap:wrap; align-items:center; gap:6px;">
                        <span style="font-size:15px; font-weight:800; color:#0f172a; margin-right:6px;">💻 GitHub Engineering & Webhook Telemetry</span>
                        ${tabBtn("employees", "👨‍💻 By Developer", (data.employees || []).length)}
                        ${tabBtn("repositories", "📦 By Repository", k.total_repositories || 0)}
                        ${tabBtn("webhooks", "📡 Webhook Stream", (data.webhooks || []).length)}
                    </div>

                    <div style="display:flex; flex-wrap:wrap; align-items:center; gap:6px;">
                        <div class="btn-group">
                            ${rangeBtn("today", "Today")}
                            ${rangeBtn("yesterday", "Yesterday")}
                            ${rangeBtn("7d", "7D")}
                            ${rangeBtn("30d", "30D")}
                            ${rangeBtn("custom", "Custom")}
                        </div>
                        <select class="form-control input-xs xav-gh-dept-filter" style="width:140px; height:28px; font-weight:600;">${deptOpts}</select>
                        <select class="form-control input-xs xav-gh-repo-filter" style="width:145px; height:28px; font-weight:600;">${repoOpts}</select>
                        <input type="text" class="form-control input-xs xav-gh-search" placeholder="Search dev, SHA, msg..." value="${frappe.utils.escape_html(listview._xav_search)}" style="width:150px; height:28px;" />
                        ${
                            data.can_manage && k.unmapped_events > 0
                                ? `<button class="btn btn-xs btn-warning xav-gh-remap-btn" style="font-weight:700;">🔗 Auto-Link Unmapped (${k.unmapped_events})</button>`
                                : ""
                        }
                        <button class="btn btn-xs btn-default xav-gh-toggle-table-btn" style="font-weight:700;">
                            ${listview._xav_show_table ? "▲ Hide Table" : "▼ Show Table"}
                        </button>
                    </div>
                </div>

                <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px;">
                    ${kpiBox("Webhook Events", k.total_events || 0, `${data.period.start_date} → ${data.period.end_date}`, "#f8fafc", "#0f172a")}
                    ${kpiBox("Total Commits", k.total_commits || 0, `${k.active_contributors || 0} Active Contributors`, "#eff6ff", "#1d4ed8")}
                    ${kpiBox("Repositories", k.total_repositories || 0, "Active Codebases", "#f3e8ff", "#6b21a8")}
                    ${kpiBox("Pull Requests", `${k.pr_opened || 0} Open / ${k.pr_merged || 0} Merged`, `${k.pr_closed || 0} Closed`, "#dcfce7", "#166534")}
                    ${kpiBox("Issues", `${k.issues_opened || 0} Open / ${k.issues_closed || 0} Closed`, "Tracked Issues", "#fef9c3", "#854d0e")}
                    ${kpiBox("Webhook Health", `${k.unmapped_events || 0} Unmapped`, `${k.failed_events || 0} Failed`, k.unmapped_events > 0 ? "#fff1f2" : "#f0fdf4", k.unmapped_events > 0 ? "#be123c" : "#15803d")}
                </div>

                ${bodyHtml}
            </div>`;

            $container.html(html);

            $container.find(".xav-gh-tab-btn").on("click", function () {
                listview._xav_gh_tab = $(this).attr("data-tab");
                listview.render_github_dashboard(data);
            });

            $container.find(".xav-gh-range-btn").on("click", function () {
                const selectedRange = $(this).attr("data-range");
                if (selectedRange === "custom") {
                    frappe.prompt(
                        [
                            {
                                fieldname: "start_date",
                                label: __("Start Date"),
                                fieldtype: "Date",
                                default: listview._xav_start_date || frappe.datetime.add_days(frappe.datetime.get_today(), -14),
                                reqd: 1,
                            },
                            {
                                fieldname: "end_date",
                                label: __("End Date"),
                                fieldtype: "Date",
                                default: listview._xav_end_date || frappe.datetime.get_today(),
                                reqd: 1,
                            },
                        ],
                        (values) => {
                            listview._xav_range = "custom";
                            listview._xav_start_date = values.start_date;
                            listview._xav_end_date = values.end_date;
                            listview.refresh_github_dashboard();
                        },
                        __("Select Custom Date Range"),
                        __("Apply Filter")
                    );
                } else {
                    listview._xav_range = selectedRange;
                    listview.refresh_github_dashboard();
                }
            });

            $container.find(".xav-gh-dept-filter").on("change", function () {
                listview._xav_dept = $(this).val() || "";
                listview.refresh_github_dashboard();
            });

            $container.find(".xav-gh-repo-filter").on("change", function () {
                listview._xav_repo = $(this).val() || "";
                listview.refresh_github_dashboard();
            });

            $container.find(".xav-gh-search").on("change", function () {
                listview._xav_search = $(this).val() || "";
                listview.refresh_github_dashboard();
            });

            $container.find(".xav-gh-toggle-table-btn").on("click", function () {
                listview._xav_show_table = !listview._xav_show_table;
                listview.render_github_dashboard(data);
            });

            $container.find(".xav-gh-remap-btn").on("click", function () {
                frappe.call({
                    method: "xavirgin_os.xavirgin_os.doctype.xavirgin_github_activity.xavirgin_github_activity.remap_unmapped_github_events",
                    freeze: true,
                    freeze_message: __("Matching GitHub handles to Employees and Daily POAs..."),
                    callback(res) {
                        if (res.message) {
                            frappe.show_alert({
                                message: __("Linked {0} webhook event(s) to Employee records.", [res.message.remapped_count || 0]),
                                indicator: "green",
                            });
                            listview.refresh_github_dashboard();
                            listview.refresh();
                        }
                    },
                });
            });

            $container.find(".xav-wh-ext-link").on("click", function (e) {
                e.stopPropagation();
            });

            $container.find(".xav-wh-row").on("click", function () {
                const docName = $(this).attr("data-name");
                if (docName) frappe.set_route("Form", "Xavirgin GitHub Activity", docName);
            });
        };

        listview.refresh_github_dashboard();
    },

    refresh(listview) {
        if (listview.refresh_github_dashboard) {
            listview.refresh_github_dashboard();
        }
        if (listview.toggle_standard_table) {
            listview.toggle_standard_table(listview._xav_show_table);
        }
    },
};