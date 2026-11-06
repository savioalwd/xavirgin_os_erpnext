frappe.listview_settings["Xavirgin Interview"] = {
    add_fields: [
        "candidate",
        "candidate_name",
        "department",
        "designation",
        "interview_round",
        "status",
        "interview_date",
        "start_time",
        "end_time",
        "meeting_platform",
        "meeting_url",
        "submitted_evaluations_count",
        "average_score",
        "consensus_recommendation",
    ],

    get_indicator(doc) {
        if (doc.status === "Completed") return [__("Completed"), "green", "status,=,Completed"];
        if (doc.status === "In Progress") return [__("In Progress"), "orange", "status,=,In Progress"];
        if (doc.status === "Rescheduled") return [__("Rescheduled"), "purple", "status,=,Rescheduled"];
        if (doc.status === "Cancelled" || doc.status === "No Show") return [__(doc.status), "red", `status,=,${doc.status}`];
        return [__("Scheduled"), "blue", "status,=,Scheduled"];
    },

    onload(listview) {
        listview._xav_active_tab = "overview"; // overview | today | upcoming | pipeline | completed | departments
        listview._xav_dept_filter = "";
        listview._xav_search_text = "";
        listview._xav_collapsed = false;

        if (!listview.page.wrapper.find(".xav-interview-kanban-board").length) {
            const $board = $(`<div class="xav-interview-kanban-board" style="padding: 12px 15px 4px 15px;"></div>`);
            listview.page.main.prepend($board);
        }

        listview.refresh_interview_dashboard = function () {
            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_interview.xavirgin_interview.get_interview_kanban_dashboard",
                args: {
                    department: listview._xav_dept_filter || "",
                    search_text: listview._xav_search_text || "",
                },
                callback(r) {
                    if (r.message) {
                        listview.render_interview_dashboard(r.message);
                    }
                },
            });
        };

        listview.render_interview_card = function (iv, highlightToday) {
            const stColors = {
                "In Progress": { bg: "#fef9c3", text: "#854d0e", border: "#fde047", label: "⚡ In Progress" },
                Scheduled: { bg: "#dbeafe", text: "#1e40af", border: "#93c5fd", label: "📅 Scheduled" },
                Rescheduled: { bg: "#f3e8ff", text: "#6b21a8", border: "#d8b4fe", label: "🔄 Rescheduled" },
                Completed: { bg: "#dcfce7", text: "#166534", border: "#86efac", label: "✅ Completed" },
                Cancelled: { bg: "#fee2e2", text: "#991b1b", border: "#fca5a5", label: "✖ Cancelled" },
                "No Show": { bg: "#fee2e2", text: "#991b1b", border: "#fca5a5", label: "⚠️ No Show" },
            };
            const st = stColors[iv.status] || stColors.Scheduled;

            const panelBadges = (iv.panel || [])
                .map((p) => {
                    const done = p.eval_status === "Submitted";
                    return `<span style="background:${done ? "#dcfce7" : "#f1f5f9"}; color:${done ? "#166534" : "#475569"}; padding:2px 7px; border-radius:999px; font-size:10px; font-weight:600;">
                        ${done ? "✅" : "⏳"} ${frappe.utils.escape_html(p.full_name)}
                    </span>`;
                })
                .join(" ");

            const evalBadge =
                iv.submitted_evals > 0
                    ? `<span style="background:#e0e7ff; color:#3730a3; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700;">
                        📊 ${iv.average_score}/${iv.max_marks} (${iv.submitted_evals}/${iv.panel_count} Evals)
                       </span>`
                    : `<span style="background:#f1f5f9; color:#64748b; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:600;">
                        📝 0/${iv.panel_count} Evals
                       </span>`;

            return `
            <div class="xav-int-card" data-int="${frappe.utils.escape_html(iv.name)}" style="background:#ffffff; border:1px solid ${iv.status === "In Progress" ? "#f59e0b" : highlightToday ? "#60a5fa" : "#e2e8f0"}; border-radius:10px; padding:12px 14px; display:flex; flex-direction:column; justify-content:space-between; cursor:pointer; box-shadow:0 1px 3px rgba(0,0,0,0.04); transition:all 0.15s;">
                <div>
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:6px; margin-bottom:6px;">
                        <div>
                            <div style="font-size:13px; font-weight:800; color:#0f172a;">
                                ${frappe.utils.escape_html(iv.candidate_name)}
                            </div>
                            <div style="font-size:11px; color:#64748b;">
                                ${frappe.utils.escape_html(iv.candidate)} • ${frappe.utils.escape_html(iv.designation)}
                            </div>
                        </div>
                        <span style="background:${st.bg}; color:${st.text}; border:1px solid ${st.border}; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700; white-space:nowrap;">
                            ${st.label}
                        </span>
                    </div>

                    <div style="display:flex; flex-wrap:wrap; gap:5px; margin-bottom:8px;">
                        <span style="background:#f3e8ff; color:#6b21a8; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700;">
                            🛡️ ${frappe.utils.escape_html(iv.department)}
                        </span>
                        <span style="background:#e0f2fe; color:#0369a1; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700;">
                            🎯 ${frappe.utils.escape_html(iv.interview_round)}
                        </span>
                        ${evalBadge}
                    </div>

                    <div style="background:#f8fafc; border:1px solid #f1f5f9; border-radius:6px; padding:6px 8px; font-size:11px; color:#1e293b; margin-bottom:8px;">
                        <div><strong>📅 Date:</strong> ${iv.formatted_date}</div>
                        <div><strong>⏰ Time (12-Hr):</strong> <span style="color:#2563eb; font-weight:700;">${iv.formatted_time_12h}</span></div>
                    </div>

                    <div style="margin-bottom:8px;">
                        <div style="font-size:10px; font-weight:700; color:#64748b; text-transform:uppercase; margin-bottom:3px;">Assigned Panel</div>
                        <div style="display:flex; flex-wrap:wrap; gap:4px;">
                            ${panelBadges || `<span style="font-size:10px; color:#94a3b8;">No panel assigned</span>`}
                        </div>
                    </div>
                </div>

                <div style="display:flex; justify-content:space-between; align-items:center; padding-top:8px; border-top:1px solid #f1f5f9;">
                    <span style="font-size:10px; font-weight:600; color:#64748b;">Ref: ${frappe.utils.escape_html(iv.name)}</span>
                    ${
                        iv.meeting_url
                            ? `<a href="${iv.meeting_url}" target="_blank" class="xav-meet-link" style="background:#2563eb; color:#ffffff; padding:3px 10px; border-radius:6px; font-size:11px; font-weight:700; text-decoration:none;">
                                🔗 Join ${frappe.utils.escape_html(iv.meeting_platform)}
                               </a>`
                            : ""
                    }
                </div>
            </div>`;
        };

        listview.render_candidate_card = function (c, isCompleted) {
            const badgeColor =
                c.pipeline_stage === "Hired"
                    ? { bg: "#dcfce7", text: "#166534", border: "#86efac" }
                    : c.pipeline_stage === "Rejected"
                    ? { bg: "#fee2e2", text: "#991b1b", border: "#fca5a5" }
                    : { bg: "#dbeafe", text: "#1e40af", border: "#93c5fd" };

            return `
            <div class="xav-cand-card" data-cand="${frappe.utils.escape_html(c.candidate)}" style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:12px 14px; cursor:pointer; box-shadow:0 1px 3px rgba(0,0,0,0.03);">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:6px; margin-bottom:6px;">
                    <div>
                        <div style="font-size:13px; font-weight:800; color:#0f172a;">${frappe.utils.escape_html(c.full_name)}</div>
                        <div style="font-size:11px; color:#64748b;">${frappe.utils.escape_html(c.candidate)} • ${frappe.utils.escape_html(c.designation)}</div>
                    </div>
                    <span style="background:${badgeColor.bg}; color:${badgeColor.text}; border:1px solid ${badgeColor.border}; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700;">
                        ${frappe.utils.escape_html(c.pipeline_stage)}
                    </span>
                </div>
                <div style="display:flex; flex-wrap:wrap; gap:5px; margin-top:6px;">
                    <span style="background:#f3e8ff; color:#6b21a8; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700;">
                        🛡️ ${frappe.utils.escape_html(c.department)}
                    </span>
                    ${
                        c.average_score > 0
                            ? `<span style="background:#fef3c7; color:#92400e; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700;">⭐ Avg Score: ${c.average_score}</span>`
                            : ""
                    }
                    ${
                        c.employee
                            ? `<span style="background:#dcfce7; color:#166534; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700;">👤 ${frappe.utils.escape_html(c.employee)}</span>`
                            : ""
                    }
                </div>
                <div style="font-size:10px; color:#64748b; margin-top:8px; display:flex; justify-content:space-between;">
                    <span>Applied: ${c.applied_on}</span>
                    ${c.latest_interview ? `<span style="color:#2563eb; font-weight:600;">Interview: ${c.latest_interview}</span>` : ""}
                </div>
            </div>`;
        };

        listview.render_interview_dashboard = function (data) {
            const $container = listview.page.wrapper.find(".xav-interview-kanban-board");
            if (!$container.length) return;

            const c = data.counts || {};
            const tab = listview._xav_active_tab || "overview";

            const deptOptions = [`<option value="">All Departments</option>`]
                .concat(
                    (data.all_departments || []).map(
                        (d) => `<option value="${frappe.utils.escape_html(d)}" ${listview._xav_dept_filter === d ? "selected" : ""}>${frappe.utils.escape_html(d)}</option>`
                    )
                )
                .join("");

            let bodyContent = "";

            if (tab === "overview" || tab === "today") {
                const todayCards = (data.todays_interviews || [])
                    .map((iv) => listview.render_interview_card(iv, true))
                    .join("");
                bodyContent += `
                <div style="margin-bottom:16px;">
                    <div style="font-size:13px; font-weight:800; color:#1e40af; margin-bottom:8px; display:flex; align-items:center; gap:8px;">
                        <span>🟢 A. Today's Interviews (${data.today_date}) — ${c.today_total || 0} Scheduled</span>
                        ${c.today_in_progress > 0 ? `<span style="background:#fef9c3; color:#854d0e; padding:2px 8px; border-radius:999px; font-size:11px;">⚡ ${c.today_in_progress} In Progress Now</span>` : ""}
                    </div>
                    <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(300px, 1fr)); gap:12px;">
                        ${todayCards || `<div style="padding:12px; background:#f8fafc; border:1px dashed #cbd5e1; border-radius:8px; color:#64748b; font-size:12px;">No interviews scheduled for today.</div>`}
                    </div>
                </div>`;
            }

            if (tab === "overview" || tab === "upcoming") {
                const upcomingCards = (data.upcoming_interviews || [])
                    .map((iv) => listview.render_interview_card(iv, false))
                    .join("");
                bodyContent += `
                <div style="margin-bottom:16px;">
                    <div style="font-size:13px; font-weight:800; color:#0f172a; margin-bottom:8px;">
                        🗓️ B. Upcoming Scheduled Interviews (Chronological) — ${c.upcoming_total || 0}
                    </div>
                    <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(300px, 1fr)); gap:12px;">
                        ${upcomingCards || `<div style="padding:12px; background:#f8fafc; border:1px dashed #cbd5e1; border-radius:8px; color:#64748b; font-size:12px;">No future upcoming interviews scheduled.</div>`}
                    </div>
                </div>`;
            }

            if (tab === "pipeline") {
                const pipeCards = (data.pipeline_candidates || [])
                    .map((cand) => listview.render_candidate_card(cand, false))
                    .join("");
                bodyContent += `
                <div style="margin-bottom:16px;">
                    <div style="font-size:13px; font-weight:800; color:#0369a1; margin-bottom:8px;">
                        🚀 C. Active Recruitment Pipeline Candidates — ${c.pipeline_total || 0}
                    </div>
                    <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:12px;">
                        ${pipeCards || `<div class="text-muted" style="padding:12px;">No active pipeline candidates found.</div>`}
                    </div>
                </div>`;
            }

            if (tab === "completed") {
                const compCards = (data.completed_candidates || [])
                    .map((cand) => listview.render_candidate_card(cand, true))
                    .join("");
                bodyContent += `
                <div style="margin-bottom:16px;">
                    <div style="font-size:13px; font-weight:800; color:#15803d; margin-bottom:8px;">
                        🏁 D. Completed Recruitment Outcomes (Hired: ${c.hired_total || 0} | Rejected: ${c.rejected_total || 0})
                    </div>
                    <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:12px;">
                        ${compCards || `<div class="text-muted" style="padding:12px;">No completed (Hired/Rejected) candidate outcomes yet.</div>`}
                    </div>
                </div>`;
            }

            if (tab === "departments") {
                const deptCards = (data.departments || [])
                    .map(
                        (d) => `
                    <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:12px 14px;">
                        <div style="font-size:14px; font-weight:800; color:#0f172a; margin-bottom:8px;">
                            🛡️ ${frappe.utils.escape_html(d.department)}
                        </div>
                        <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:4px; text-align:center; background:#f8fafc; padding:6px; border-radius:6px; font-size:11px; margin-bottom:8px;">
                            <div><div style="font-weight:700; color:#2563eb;">${d.today_interviews}</div><div style="font-size:9px; color:#64748b;">Today</div></div>
                            <div><div style="font-weight:700; color:#4f46e5;">${d.upcoming_interviews}</div><div style="font-size:9px; color:#64748b;">Upcoming</div></div>
                            <div><div style="font-weight:700; color:#d97706;">${d.pipeline_count}</div><div style="font-size:9px; color:#64748b;">Pipeline</div></div>
                            <div><div style="font-weight:700; color:#16a34a;">${d.completed_count}</div><div style="font-size:9px; color:#64748b;">Done</div></div>
                        </div>
                        <div style="max-height:180px; overflow-y:auto;">
                            ${(d.candidates || [])
                                .slice(0, 12)
                                .map(
                                    (mc) => `
                                <div class="xav-cand-card" data-cand="${frappe.utils.escape_html(mc.candidate)}" style="display:flex; justify-content:space-between; align-items:center; padding:5px 8px; border-bottom:1px solid #f1f5f9; font-size:11px; cursor:pointer;">
                                    <span style="font-weight:600; color:#1e293b;">${frappe.utils.escape_html(mc.full_name)}</span>
                                    <span style="font-size:10px; font-weight:700; color:#475569;">${frappe.utils.escape_html(mc.pipeline_stage)}</span>
                                </div>`
                                )
                                .join("")}
                        </div>
                    </div>`
                    )
                    .join("");

                bodyContent += `
                <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(290px, 1fr)); gap:12px;">
                    ${deptCards || `<div class="text-muted">No department data available.</div>`}
                </div>`;
            }

            const tabBtn = (id, label, badgeCount) => {
                const active = tab === id;
                return `<button class="btn btn-xs xav-int-tab-btn" data-tab="${id}" style="font-weight:700; border-radius:999px; padding:4px 12px; background:${active ? "#2563eb" : "#f1f5f9"}; color:${active ? "#ffffff" : "#334155"}; border:none;">
                    ${label} (${badgeCount})
                </button>`;
            };

            const html = `
            <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:14px 16px; margin-bottom:10px; box-shadow:0 1px 4px rgba(0,0,0,0.03);">
                <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px; margin-bottom:${listview._xav_collapsed ? "0" : "12px"};">
                    <div style="display:flex; flex-wrap:wrap; align-items:center; gap:6px;">
                        <span style="font-size:15px; font-weight:800; color:#0f172a; margin-right:6px;">🎯 Interview & Recruitment Hub</span>
                        ${tabBtn("overview", "Overview", (c.today_total || 0) + (c.upcoming_total || 0))}
                        ${tabBtn("today", "Today", c.today_total || 0)}
                        ${tabBtn("upcoming", "Upcoming", c.upcoming_total || 0)}
                        ${tabBtn("pipeline", "Pipeline", c.pipeline_total || 0)}
                        ${tabBtn("completed", "Completed (Hired/Rejected)", c.completed_total || 0)}
                        ${tabBtn("departments", "By Department", (data.departments || []).length)}
                    </div>

                    <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                        <select class="form-control input-xs xav-int-dept-select" style="width:160px; height:28px; font-weight:600;">
                            ${deptOptions}
                        </select>
                        <input type="text" class="form-control input-xs xav-int-search" placeholder="Search candidate / role..." value="${frappe.utils.escape_html(listview._xav_search_text)}" style="width:160px; height:28px;" />
                        <button class="btn btn-xs btn-default xav-int-collapse-btn" style="font-weight:600;">
                            ${listview._xav_collapsed ? "▼ Expand Dashboard" : "▲ Collapse"}
                        </button>
                    </div>
                </div>

                <div style="display:${listview._xav_collapsed ? "none" : "block"};">
                    ${bodyContent}
                </div>
            </div>`;

            $container.html(html);

            $container.find(".xav-int-tab-btn").on("click", function () {
                listview._xav_active_tab = $(this).attr("data-tab");
                listview.render_interview_dashboard(data);
            });

            $container.find(".xav-int-dept-select").on("change", function () {
                listview._xav_dept_filter = $(this).val() || "";
                listview.refresh_interview_dashboard();
            });

            $container.find(".xav-int-search").on("change", function () {
                listview._xav_search_text = $(this).val() || "";
                listview.refresh_interview_dashboard();
            });

            $container.find(".xav-int-collapse-btn").on("click", function () {
                listview._xav_collapsed = !listview._xav_collapsed;
                listview.render_interview_dashboard(data);
            });

            $container.find(".xav-meet-link").on("click", function (e) {
                e.stopPropagation();
            });

            $container.find(".xav-int-card").on("click", function () {
                const intName = $(this).attr("data-int");
                if (intName) frappe.set_route("Form", "Xavirgin Interview", intName);
            });

            $container.find(".xav-cand-card").on("click", function () {
                const candName = $(this).attr("data-cand");
                if (candName) frappe.set_route("Form", "Xavirgin Candidate", candName);
            });
        };

        listview.refresh_interview_dashboard();
    },

    refresh(listview) {
        if (listview.refresh_interview_dashboard) {
            listview.refresh_interview_dashboard();
        }
    },
};