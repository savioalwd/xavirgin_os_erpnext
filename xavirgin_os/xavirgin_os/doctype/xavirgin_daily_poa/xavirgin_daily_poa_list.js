frappe.listview_settings["Xavirgin Daily POA"] = {
    add_fields: [
        "employee",
        "employee_name",
        "department",
        "poa_date",
        "status",
        "attendance_verified",
        "attendance_status",
        "total_actual_hours",
        "completed_tasks_count",
        "total_poa_xp",
    ],

    get_indicator(doc) {
        if (doc.status === "Completed for Today" || doc.status === "Submitted (EOD Report)") {
            return [__("Submitted"), "green", "status,=,Completed for Today"];
        }
        if (doc.status === "Working" || doc.status === "In Progress") {
            return [__("Working"), "blue", "status,=,Working"];
        }
        if (doc.status === "Stuck / Blocked" || doc.status === "Blocked") {
            return [__("Blocked"), "red", "status,=,Stuck / Blocked"];
        }
        return [__("Morning Plan"), "orange", "status,=,Morning Plan"];
    },

    onload(listview) {
        const todayStr = frappe.datetime.get_today();
        listview._xav_selected_date = todayStr;
        listview._xav_show_table = false; // Keep standard table hidden by default so Kanban is clean

        listview.toggle_underlying_table = function (show) {
            const $standardList = listview.page.wrapper.find(
                ".result-list, .frappe-list, .list-row-container, .list-paging-area, .standard-filter-section, .filter-section"
            );
            if (show) {
                $standardList.show();
            } else {
                $standardList.hide();
            }
        };

        setTimeout(() => {
            const existingFilters = listview.filter_area ? listview.filter_area.get() : [];
            const hasDateFilter = existingFilters.some((f) => f[1] === "poa_date");
            if (!hasDateFilter && listview.filter_area) {
                listview.filter_area.add([["Xavirgin Daily POA", "poa_date", "=", todayStr]]);
            }
            listview.toggle_underlying_table(listview._xav_show_table);
        }, 150);

        // Primary Action Override: Open today's existing POA if already created, else create new
        listview.page.set_primary_action(__("➕ My Today's POA"), () => {
            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_daily_poa.xavirgin_daily_poa.get_session_poa_Bootstrap",
                args: { poa_date: frappe.datetime.get_today() },
                freeze: true,
                freeze_message: __("Loading your Daily POA..."),
                callback(r) {
                    const data = r.message || {};
                    if (data.existing_poa && data.existing_poa.name) {
                        frappe.set_route("Form", "Xavirgin Daily POA", data.existing_poa.name);
                    } else {
                        frappe.new_doc("Xavirgin Daily POA", {
                            employee: data.employee,
                            poa_date: frappe.datetime.get_today(),
                        });
                    }
                },
            });
        });

        // Mount Department-Wise Kanban Dashboard Container
        if (!listview.page.wrapper.find(".xav-poa-kanban-dashboard").length) {
            const $dashboard = $(`<div class="xav-poa-kanban-dashboard" style="padding: 12px 15px 4px 15px;"></div>`);
            listview.page.main.prepend($dashboard);
        }

        listview.refresh_poa_dashboard = function (targetDate) {
            const queryDate = targetDate || listview._xav_selected_date || frappe.datetime.get_today();
            listview._xav_selected_date = queryDate;

            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_daily_poa.xavirgin_daily_poa.get_department_poa_dashboard",
                args: { target_date: queryDate },
                callback(r) {
                    const data = r.message;
                    if (!data) return;
                    listview.render_poa_dashboard(data);
                },
            });
        };

        listview.render_poa_dashboard = function (data) {
            const $container = listview.page.wrapper.find(".xav-poa-kanban-dashboard");
            if (!$container.length) return;

            listview.toggle_underlying_table(listview._xav_show_table);

            const t = data.totals || {};
            const depts = data.departments || [];

            const statusBadgeMeta = {
                Submitted: { bg: "#dcfce7", text: "#166534", border: "#86efac", dot: "#16a34a", label: "Submitted" },
                "In Progress": { bg: "#dbeafe", text: "#1e40af", border: "#93c5fd", dot: "#2563eb", label: "Working" },
                Blocked: { bg: "#fee2e2", text: "#991b1b", border: "#fca5a5", dot: "#dc2626", label: "Blocked" },
                Missing: { bg: "#f1f5f9", text: "#64748b", border: "#cbd5e1", dot: "#94a3b8", label: "Missing" },
            };

            const deptCardsHtml = depts
                .map((d) => {
                    const pctColor =
                        d.submission_pct >= 80 ? "#16a34a" : d.submission_pct >= 50 ? "#d97706" : "#dc2626";
                    const mySquadBadge = d.is_my_department
                        ? `<span style="background:#4f46e5; color:#fff; font-size:10px; font-weight:700; padding:2px 7px; border-radius:999px; margin-left:6px;">MY SQUAD</span>`
                        : "";

                    const memberRows = (d.employees || [])
                        .map((m) => {
                            const meta = statusBadgeMeta[m.ui_category] || statusBadgeMeta.Missing;
                            const attPill =
                                m.attendance_sessions > 0
                                    ? `<span title="Checked In (${m.attendance_hours}h)" style="color:#15803d; font-size:11px; font-weight:600;">🟢 ${m.attendance_hours}h</span>`
                                    : `<span title="Not Checked In" style="color:#94a3b8; font-size:11px;">⚪ 0h</span>`;

                            const leadStar = m.is_team_lead ? `<span title="Team Lead">⭐ </span>` : "";

                            let actionAttr = "";
                            if (m.poa_name) {
                                actionAttr = `data-poa="${frappe.utils.escape_html(m.poa_name)}"`;
                            } else if (m.can_manage) {
                                actionAttr = `data-create-emp="${frappe.utils.escape_html(m.employee)}"`;
                            } else {
                                actionAttr = `data-view-emp="${frappe.utils.escape_html(m.employee)}"`;
                            }

                            return `
                            <div class="xav-poa-member-row" ${actionAttr} style="display:flex; justify-content:space-between; align-items:center; padding:6px 8px; border-radius:6px; background:#f8fafc; border:1px solid #f1f5f9; margin-bottom:5px; cursor:pointer; transition:all 0.15s;">
                                <div style="min-width:0; flex:1; padding-right:6px;">
                                    <div style="font-size:12px; font-weight:600; color:#1e293b; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                                        ${leadStar}${frappe.utils.escape_html(m.employee_name)}
                                    </div>
                                    <div style="font-size:10px; color:#64748b; display:flex; align-items:center; gap:6px;">
                                        <span>${frappe.utils.escape_html(m.designation)}</span>
                                        <span>•</span>
                                        ${attPill}
                                        ${m.poa_name ? `<span>• ✅ ${m.completed_tasks} tasks</span>` : ""}
                                    </div>
                                </div>
                                <span style="background:${meta.bg}; color:${meta.text}; border:1px solid ${meta.border}; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700; white-space:nowrap;">
                                    ${meta.label}
                                </span>
                            </div>`;
                        })
                        .join("");

                    return `
                    <div class="xav-dept-card" style="background:#ffffff; border:1px solid ${d.is_my_department ? "#818cf8" : "#e2e8f0"}; border-radius:10px; padding:14px; display:flex; flex-direction:column; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
                            <div>
                                <a href="#" class="xav-filter-dept" data-dept="${frappe.utils.escape_html(d.department)}" style="font-size:14px; font-weight:700; color:#0f172a; text-decoration:none;">
                                    🛡️ ${frappe.utils.escape_html(d.department)}
                                </a>
                                ${mySquadBadge}
                            </div>
                            <span style="font-size:13px; font-weight:800; color:${pctColor};">
                                ${d.submission_pct}%
                            </span>
                        </div>

                        <div style="width:100%; height:6px; background:#f1f5f9; border-radius:999px; overflow:hidden; margin-bottom:10px;">
                            <div style="width:${Math.min(100, d.submission_pct)}%; height:100%; background:${pctColor}; border-radius:999px;"></div>
                        </div>

                        <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:4px; text-align:center; margin-bottom:10px; padding:6px 4px; background:#f8fafc; border-radius:6px; font-size:11px;">
                            <div>
                                <div style="font-weight:700; color:#334155;">${d.total_employees}</div>
                                <div style="font-size:9px; color:#64748b;">Total</div>
                            </div>
                            <div>
                                <div style="font-weight:700; color:#16a34a;">${d.submitted_count}</div>
                                <div style="font-size:9px; color:#64748b;">Done</div>
                            </div>
                            <div>
                                <div style="font-weight:700; color:#2563eb;">${d.in_progress_count}</div>
                                <div style="font-size:9px; color:#64748b;">Active</div>
                            </div>
                            <div>
                                <div style="font-weight:700; color:#dc2626;">${d.missing_count}</div>
                                <div style="font-size:9px; color:#64748b;">Missing</div>
                            </div>
                        </div>

                        <div style="max-height:260px; overflow-y:auto; padding-right:2px;">
                            ${memberRows}
                        </div>
                    </div>`;
                })
                .join("");

            const html = `
                <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:14px 16px; margin-bottom:10px; box-shadow:0 1px 4px rgba(0,0,0,0.03);">
                    <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px; margin-bottom:14px;">
                        <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
                            <span style="font-size:15px; font-weight:800; color:#0f172a;">
                                📊 Squad Daily POA Kanban Board
                            </span>
                            <input type="date" class="form-control input-xs xav-poa-date-picker" value="${data.date}" style="width:140px; font-weight:600; height:28px; display:inline-block;" />
                            <button class="btn btn-xs btn-default xav-poa-today-btn" style="font-weight:600;">Today</button>
                            <button class="btn btn-xs btn-default xav-poa-all-dates-btn" style="font-weight:600;">All History Table</button>
                        </div>

                        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                            <span style="background:#f1f5f9; color:#334155; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:700;">
                                👥 Total: ${t.total_employees || 0}
                            </span>
                            <span style="background:#dcfce7; color:#166534; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:700;">
                                ✅ Submitted: ${t.submitted_count || 0}
                            </span>
                            <span style="background:#dbeafe; color:#1e40af; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:700;">
                                ⚡ Working: ${t.in_progress_count || 0}
                            </span>
                            <span style="background:#fee2e2; color:#991b1b; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:700;">
                                ⚠️ Missing: ${t.missing_count || 0}
                            </span>
                            <span style="background:#e0e7ff; color:#3730a3; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:800;">
                                📈 ${t.overall_submission_pct || 0}% Active
                            </span>
                            <button class="btn btn-xs btn-default xav-toggle-table-btn" style="font-weight:700;">
                                ${listview._xav_show_table ? "▲ Hide Standard Table" : "▼ Show Standard Table"}
                            </button>
                        </div>
                    </div>

                    <div class="xav-kanban-grid-body" style="display:grid; grid-template-columns:repeat(auto-fill, minmax(290px, 1fr)); gap:12px;">
                        ${deptCardsHtml || `<div class="text-muted" style="padding:12px;">No active departments found.</div>`}
                    </div>
                </div>
            `;

            $container.html(html);

            // Bind Date Picker Change
            $container.find(".xav-poa-date-picker").on("change", function () {
                const newDate = $(this).val();
                if (newDate) {
                    listview._xav_selected_date = newDate;
                    if (listview.filter_area) {
                        listview.filter_area.clear();
                        listview.filter_area.add([["Xavirgin Daily POA", "poa_date", "=", newDate]]);
                    }
                    listview.refresh_poa_dashboard(newDate);
                }
            });

            // Bind Today Button
            $container.find(".xav-poa-today-btn").on("click", function () {
                const tDate = frappe.datetime.get_today();
                listview._xav_selected_date = tDate;
                if (listview.filter_area) {
                    listview.filter_area.clear();
                    listview.filter_area.add([["Xavirgin Daily POA", "poa_date", "=", tDate]]);
                }
                listview.refresh_poa_dashboard(tDate);
            });

            // Bind All History Button (reveals the standard table & clears date filter)
            $container.find(".xav-poa-all-dates-btn").on("click", function () {
                listview._xav_show_table = true;
                listview.toggle_underlying_table(true);
                if (listview.filter_area) {
                    listview.filter_area.clear();
                }
                listview.refresh();
            });

            // Bind Show/Hide Standard Table Toggle
            $container.find(".xav-toggle-table-btn").on("click", function () {
                listview._xav_show_table = !listview._xav_show_table;
                listview.render_poa_dashboard(data);
            });

            // Bind Department Header Filter Click
            $container.find(".xav-filter-dept").on("click", function (e) {
                e.preventDefault();
                const dept = $(this).attr("data-dept");
                if (listview.filter_area && dept) {
                    listview._xav_show_table = true;
                    listview.toggle_underlying_table(true);
                    listview.filter_area.clear();
                    const filters = [["Xavirgin Daily POA", "poa_date", "=", data.date]];
                    if (dept !== "Unassigned Squad") {
                        filters.push(["Xavirgin Daily POA", "department", "=", dept]);
                    }
                    listview.filter_area.add(filters);
                }
            });

            // Bind Member Row Click
            $container.find(".xav-poa-member-row").on("click", function () {
                const poaName = $(this).attr("data-poa");
                const createEmp = $(this).attr("data-create-emp");
                const viewEmp = $(this).attr("data-view-emp");

                if (poaName) {
                    frappe.set_route("Form", "Xavirgin Daily POA", poaName);
                } else if (createEmp) {
                    frappe.new_doc("Xavirgin Daily POA", {
                        employee: createEmp,
                        poa_date: data.date,
                    });
                } else if (viewEmp) {
                    frappe.show_alert({
                        message: __("This member has not submitted a Daily POA for {0} yet.", [data.date]),
                        indicator: "orange",
                    });
                }
            });
        };

        listview.refresh_poa_dashboard(todayStr);
    },

    refresh(listview) {
        if (listview.refresh_poa_dashboard) {
            listview.refresh_poa_dashboard(listview._xav_selected_date || frappe.datetime.get_today());
        }
        if (listview.toggle_underlying_table) {
            listview.toggle_underlying_table(listview._xav_show_table);
        }
    },
};