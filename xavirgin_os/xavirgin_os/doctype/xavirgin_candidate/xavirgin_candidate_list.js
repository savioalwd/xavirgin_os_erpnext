frappe.listview_settings["Xavirgin Candidate"] = {
    add_fields: [
        "full_name",
        "email",
        "phone",
        "job_opening",
        "department",
        "designation",
        "pipeline_stage",
        "source",
        "ai_match_score",
        "average_evaluation_score",
        "overall_recommendation",
        "employee",
    ],

    get_indicator(doc) {
        if (doc.pipeline_stage === "Hired") return [__("Hired"), "green", "pipeline_stage,=,Hired"];
        if (doc.pipeline_stage === "Rejected" || doc.pipeline_stage === "Offer Rejected") {
            return [__(doc.pipeline_stage), "red", `pipeline_stage,=,${doc.pipeline_stage}`];
        }
        if (doc.pipeline_stage === "Withdrawn") return [__("Withdrawn"), "gray", "pipeline_stage,=,Withdrawn"];
        if (doc.pipeline_stage === "Interview Scheduled" || doc.pipeline_stage === "Interview Completed") {
            return [__(doc.pipeline_stage), "blue", `pipeline_stage,=,${doc.pipeline_stage}`];
        }
        if (doc.pipeline_stage === "Offer Preparation" || doc.pipeline_stage === "Offer Sent" || doc.pipeline_stage === "Offer Accepted") {
            return [__(doc.pipeline_stage), "purple", `pipeline_stage,=,${doc.pipeline_stage}`];
        }
        return [__(doc.pipeline_stage || "New Application"), "orange", `pipeline_stage,=,${doc.pipeline_stage}`];
    },

    onload(listview) {
        listview._xav_tab = "kanban"; // kanban | funnel | attention | completed
        listview._xav_dept = "";
        listview._xav_job = "";
        listview._xav_source = "";
        listview._xav_search = "";
        listview._xav_collapsed = false;

        if (!listview.page.wrapper.find(".xav-candidate-pipeline-hub").length) {
            const $hub = $(`<div class="xav-candidate-pipeline-hub" style="padding: 12px 15px 4px 15px;"></div>`);
            listview.page.main.prepend($hub);
        }

        listview.refresh_pipeline_hub = function () {
            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_candidate.xavirgin_candidate.get_candidate_pipeline_dashboard",
                args: {
                    department: listview._xav_dept,
                    job_opening: listview._xav_job,
                    source: listview._xav_source,
                    search_text: listview._xav_search,
                },
                callback(r) {
                    if (r.message) {
                        listview.render_pipeline_hub(r.message);
                    }
                },
            });
        };

        listview.render_cand_card = function (c, canManage, allStages) {
            const stageMenu = canManage
                ? `<button class="btn btn-xs btn-default xav-quick-stage-btn" data-cand="${frappe.utils.escape_html(c.name)}" data-stage="${frappe.utils.escape_html(c.pipeline_stage)}" title="Move Stage" style="padding:1px 6px; font-size:10px; font-weight:700;">⇄ Stage</button>`
                : "";

            const attnBadge = c.attention_reason
                ? `<div style="background:#fff1f2; color:#be123c; border:1px solid #fecdd3; padding:2px 7px; border-radius:6px; font-size:10px; font-weight:700; margin-bottom:6px;">
                    ⚠️ ${frappe.utils.escape_html(c.attention_reason)}
                   </div>`
                : "";

            return `
            <div class="xav-pipe-card" data-cand="${frappe.utils.escape_html(c.name)}" style="background:#ffffff; border:1px solid ${c.attention_reason ? "#fda4af" : "#e2e8f0"}; border-radius:9px; padding:10px 12px; margin-bottom:8px; cursor:pointer; box-shadow:0 1px 2px rgba(0,0,0,0.03); transition:all 0.15s;">
                ${attnBadge}
                <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:6px; margin-bottom:4px;">
                    <div style="font-size:12px; font-weight:800; color:#0f172a; line-height:1.3;">
                        ${frappe.utils.escape_html(c.full_name)}
                    </div>
                    ${stageMenu}
                </div>
                <div style="font-size:10px; color:#64748b; margin-bottom:6px;">
                    ${frappe.utils.escape_html(c.name)} • ${frappe.utils.escape_html(c.designation)}
                </div>

                <div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:6px;">
                    <span style="background:#f3e8ff; color:#6b21a8; padding:1px 6px; border-radius:999px; font-size:9px; font-weight:700;">
                        🛡️ ${frappe.utils.escape_html(c.department)}
                    </span>
                    <span style="background:#f1f5f9; color:#334155; padding:1px 6px; border-radius:999px; font-size:9px; font-weight:600;">
                        📡 ${frappe.utils.escape_html(c.source)}
                    </span>
                    ${
                        c.ai_score > 0
                            ? `<span style="background:#fef3c7; color:#92400e; padding:1px 6px; border-radius:999px; font-size:9px; font-weight:700;">🤖 AI: ${c.ai_score}/10</span>`
                            : ""
                    }
                    ${
                        c.eval_score > 0
                            ? `<span style="background:#dcfce7; color:#166534; padding:1px 6px; border-radius:999px; font-size:9px; font-weight:700;">⭐ Eval: ${c.eval_score}</span>`
                            : ""
                    }
                </div>

                ${
                    c.interview_name
                        ? `<div style="font-size:10px; color:#1e40af; background:#eff6ff; padding:3px 6px; border-radius:4px; margin-bottom:4px;">
                            🗓️ Interview: <b>${c.interview_status}</b> ${c.interview_date ? `(${c.interview_date})` : ""}
                           </div>`
                        : ""
                }

                <div style="display:flex; justify-content:space-between; align-items:center; font-size:9px; color:#94a3b8; padding-top:4px; border-top:1px solid #f8fafc;">
                    <span>Applied: ${c.applied_date}</span>
                    <span>${c.last_activity_days === 0 ? "Active today" : `${c.last_activity_days}d ago`}</span>
                </div>
            </div>`;
        };

        listview.render_pipeline_hub = function (data) {
            const $container = listview.page.wrapper.find(".xav-candidate-pipeline-hub");
            if (!$container.length) return;

            const k = data.kpis || {};
            const opts = data.filter_options || {};
            const tab = listview._xav_tab || "kanban";

            const kpiCard = (label, val, sub, bg, color) => `
                <div style="background:${bg}; border-radius:8px; padding:8px 12px; min-width:125px; flex:1;">
                    <div style="font-size:18px; font-weight:800; color:${color}; line-height:1.2;">${val}</div>
                    <div style="font-size:11px; font-weight:700; color:#334155;">${label}</div>
                    <div style="font-size:9px; color:#64748b;">${sub}</div>
                </div>`;

            let mainViewHtml = "";

            if (tab === "kanban") {
                const columnsHtml = (data.stage_columns || [])
                    .map((col) => {
                        const cards = (col.candidates || [])
                            .map((c) => listview.render_cand_card(c, data.can_manage, opts.stages))
                            .join("");
                        return `
                        <div style="min-width:255px; max-width:275px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:10px; display:flex; flex-direction:column; max-height:460px;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; padding-bottom:6px; border-bottom:2px solid #cbd5e1;">
                                <span style="font-size:12px; font-weight:800; color:#0f172a;">${frappe.utils.escape_html(col.stage)}</span>
                                <span style="background:#e2e8f0; color:#1e293b; padding:1px 8px; border-radius:999px; font-size:11px; font-weight:800;">${col.count}</span>
                            </div>
                            <div style="overflow-y:auto; flex:1; padding-right:2px;">
                                ${cards || `<div style="font-size:11px; color:#94a3b8; text-align:center; padding:18px 6px;">No candidates in this stage</div>`}
                            </div>
                        </div>`;
                    })
                    .join("");

                mainViewHtml = `
                <div style="display:flex; gap:10px; overflow-x:auto; padding-bottom:8px;">
                    ${columnsHtml}
                </div>`;
            } else if (tab === "funnel") {
                const funnelBars = (data.funnel || [])
                    .map(
                        (f) => `
                    <div style="margin-bottom:8px;">
                        <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:700; color:#1e293b; margin-bottom:3px;">
                            <span>${frappe.utils.escape_html(f.label)}</span>
                            <span>${f.count} (${f.pct}%)</span>
                        </div>
                        <div style="width:100%; height:10px; background:#f1f5f9; border-radius:999px; overflow:hidden;">
                            <div style="width:${Math.min(100, f.pct)}%; height:100%; background:${f.color}; border-radius:999px;"></div>
                        </div>
                    </div>`
                    )
                    .join("");

                const sourceRows = (data.sources || [])
                    .map(
                        (s) => `
                    <tr>
                        <td style="padding:6px 8px; font-weight:700; color:#0f172a;">📡 ${frappe.utils.escape_html(s.source)}</td>
                        <td style="padding:6px 8px; text-align:center; font-weight:700;">${s.total}</td>
                        <td style="padding:6px 8px; text-align:center; color:#2563eb; font-weight:600;">${s.shortlisted}</td>
                        <td style="padding:6px 8px; text-align:center; color:#16a34a; font-weight:700;">${s.hired}</td>
                        <td style="padding:6px 8px; text-align:center; color:#dc2626;">${s.rejected}</td>
                        <td style="padding:6px 8px; text-align:right; font-weight:700;">${s.total > 0 ? ((s.hired / s.total) * 100).toFixed(1) : "0.0"}%</td>
                    </tr>`
                    )
                    .join("");

                const deptRows = (data.departments || [])
                    .map(
                        (d) => `
                    <tr>
                        <td style="padding:6px 8px; font-weight:700; color:#0f172a;">🛡️ ${frappe.utils.escape_html(d.department)}</td>
                        <td style="padding:6px 8px; text-align:center; font-weight:700;">${d.total}</td>
                        <td style="padding:6px 8px; text-align:center; color:#2563eb; font-weight:700;">${d.active}</td>
                        <td style="padding:6px 8px; text-align:center; color:#16a34a; font-weight:700;">${d.hired}</td>
                        <td style="padding:6px 8px; text-align:center; color:#dc2626;">${d.rejected}</td>
                    </tr>`
                    )
                    .join("");

                mainViewHtml = `
                <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(310px, 1fr)); gap:14px;">
                    <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:14px;">
                        <div style="font-size:13px; font-weight:800; color:#0f172a; margin-bottom:10px;">🌪️ Stage-to-Stage Conversion Funnel</div>
                        ${funnelBars}
                    </div>
                    <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:14px;">
                        <div style="font-size:13px; font-weight:800; color:#0f172a; margin-bottom:10px;">📡 Application Source Attribution & Conversion</div>
                        <table class="table table-bordered" style="background:#fff; font-size:11px; margin-bottom:0;">
                            <thead><tr style="background:#f1f5f9;"><th>Source</th><th>Total</th><th>Screened</th><th>Hired</th><th>Rejected</th><th>Hire %</th></tr></thead>
                            <tbody>${sourceRows || `<tr><td colspan="6" class="text-center text-muted">No source data</td></tr>`}</tbody>
                        </table>
                    </div>
                    <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:14px;">
                        <div style="font-size:13px; font-weight:800; color:#0f172a; margin-bottom:10px;">🛡️ Department Recruitment Distribution</div>
                        <table class="table table-bordered" style="background:#fff; font-size:11px; margin-bottom:0;">
                            <thead><tr style="background:#f1f5f9;"><th>Department</th><th>Total</th><th>Active</th><th>Hired</th><th>Rejected</th></tr></thead>
                            <tbody>${deptRows || `<tr><td colspan="5" class="text-center text-muted">No department data</td></tr>`}</tbody>
                        </table>
                    </div>
                </div>`;
            } else if (tab === "attention") {
                const attnCards = (data.needs_attention || [])
                    .map((c) => listview.render_cand_card(c, data.can_manage, opts.stages))
                    .join("");
                mainViewHtml = `
                <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:10px;">
                    ${attnCards || `<div style="padding:14px; color:#16a34a; font-weight:700;">✅ All active candidates are up to date! No overdue items.</div>`}
                </div>`;
            } else if (tab === "completed") {
                const compCards = (data.completed_outcomes || [])
                    .map((c) => {
                        const isHired = c.pipeline_stage === "Hired";
                        return `
                        <div class="xav-pipe-card" data-cand="${frappe.utils.escape_html(c.name)}" style="background:#ffffff; border:1px solid ${isHired ? "#86efac" : "#fca5a5"}; border-radius:9px; padding:10px 12px; cursor:pointer;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                                <span style="font-size:13px; font-weight:800; color:#0f172a;">${frappe.utils.escape_html(c.full_name)}</span>
                                <span style="background:${isHired ? "#dcfce7" : "#fee2e2"}; color:${isHired ? "#166534" : "#991b1b"}; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700;">
                                    ${frappe.utils.escape_html(c.pipeline_stage)}
                                </span>
                            </div>
                            <div style="font-size:11px; color:#64748b; margin-bottom:6px;">${frappe.utils.escape_html(c.designation)} • ${frappe.utils.escape_html(c.department)}</div>
                            ${c.employee ? `<div style="font-size:11px; color:#15803d; font-weight:700;">👤 Employee ID: ${frappe.utils.escape_html(c.employee)}</div>` : ""}
                            ${c.decision_reason ? `<div style="font-size:10px; color:#64748b; margin-top:4px;">Note: ${frappe.utils.escape_html(c.decision_reason)}</div>` : ""}
                        </div>`;
                    })
                    .join("");
                mainViewHtml = `
                <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:10px;">
                    ${compCards || `<div class="text-muted" style="padding:12px;">No completed (Hired / Rejected) outcomes matching filters.</div>`}
                </div>`;
            }

            const tabBtn = (id, label, count) => {
                const act = tab === id;
                return `<button class="btn btn-xs xav-cand-tab-btn" data-tab="${id}" style="font-weight:700; border-radius:999px; padding:4px 12px; background:${act ? "#2563eb" : "#f1f5f9"}; color:${act ? "#fff" : "#334155"}; border:none;">
                    ${label} (${count})
                </button>`;
            };

            const deptOptions = [`<option value="">All Departments</option>`]
                .concat((opts.departments || []).map((d) => `<option value="${frappe.utils.escape_html(d)}" ${listview._xav_dept === d ? "selected" : ""}>${frappe.utils.escape_html(d)}</option>`))
                .join("");

            const sourceOptions = [`<option value="">All Sources</option>`]
                .concat((opts.sources || []).map((s) => `<option value="${frappe.utils.escape_html(s)}" ${listview._xav_source === s ? "selected" : ""}>${frappe.utils.escape_html(s)}</option>`))
                .join("");

            const html = `
            <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:14px 16px; margin-bottom:10px; box-shadow:0 1px 4px rgba(0,0,0,0.03);">
                <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px; margin-bottom:12px;">
                    <div style="display:flex; flex-wrap:wrap; align-items:center; gap:6px;">
                        <span style="font-size:15px; font-weight:800; color:#0f172a; margin-right:6px;">🧬 Recruitment Pipeline & Funnel</span>
                        ${tabBtn("kanban", "📋 Active Pipeline Kanban", k.active_pipeline || 0)}
                        ${tabBtn("funnel", "📊 Funnel & Sources", (data.sources || []).length)}
                        ${tabBtn("attention", "⚠️ Needs Attention", k.needs_attention_count || 0)}
                        ${tabBtn("completed", "🏁 Completed (Hired/Rejected)", (k.hired_count || 0) + (k.rejected_count || 0))}
                    </div>

                    <div style="display:flex; flex-wrap:wrap; align-items:center; gap:6px;">
                        <select class="form-control input-xs xav-cand-dept-filter" style="width:150px; height:28px; font-weight:600;">${deptOptions}</select>
                        <select class="form-control input-xs xav-cand-source-filter" style="width:140px; height:28px; font-weight:600;">${sourceOptions}</select>
                        <input type="text" class="form-control input-xs xav-cand-search-input" placeholder="Search candidate / skill..." value="${frappe.utils.escape_html(listview._xav_search)}" style="width:160px; height:28px;" />
                        <button class="btn btn-xs btn-default xav-cand-collapse-btn" style="font-weight:600;">
                            ${listview._xav_collapsed ? "▼ Expand" : "▲ Collapse"}
                        </button>
                    </div>
                </div>

                <div style="display:${listview._xav_collapsed ? "none" : "block"};">
                    <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px;">
                        ${kpiCard("Total Applied", k.total_applications || 0, `+${k.today_applications || 0} Today`, "#f8fafc", "#0f172a")}
                        ${kpiCard("Active Pipeline", k.active_pipeline || 0, `${k.awaiting_interview || 0} Awaiting Interview`, "#eff6ff", "#1d4ed8")}
                        ${kpiCard("Interviews Set", k.interviews_scheduled || 0, `${k.assessments_completed || 0} Scored`, "#f3e8ff", "#6b21a8")}
                        ${kpiCard("Pending Decision", k.awaiting_hr_decision || 0, `${k.offers_processing || 0} In Offer Stage`, "#fef9c3", "#854d0e")}
                        ${kpiCard("Hired", k.hired_count || 0, `${k.conversion_rate_pct || 0}% Conversion`, "#dcfce7", "#166534")}
                        ${kpiCard("Rejected", k.rejected_count || 0, `${k.rejection_rate_pct || 0}% Rejection`, "#fee2e2", "#991b1b")}
                    </div>
                    ${mainViewHtml}
                </div>
            </div>`;

            $container.html(html);

            $container.find(".xav-cand-tab-btn").on("click", function () {
                listview._xav_tab = $(this).attr("data-tab");
                listview.render_pipeline_hub(data);
            });

            $container.find(".xav-cand-dept-filter").on("change", function () {
                listview._xav_dept = $(this).val() || "";
                listview.refresh_pipeline_hub();
            });

            $container.find(".xav-cand-source-filter").on("change", function () {
                listview._xav_source = $(this).val() || "";
                listview.refresh_pipeline_hub();
            });

            $container.find(".xav-cand-search-input").on("change", function () {
                listview._xav_search = $(this).val() || "";
                listview.refresh_pipeline_hub();
            });

            $container.find(".xav-cand-collapse-btn").on("click", function () {
                listview._xav_collapsed = !listview._xav_collapsed;
                listview.render_pipeline_hub(data);
            });

            $container.find(".xav-quick-stage-btn").on("click", function (e) {
                e.stopPropagation();
                const candName = $(this).attr("data-cand");
                const curStage = $(this).attr("data-stage");
                let d = new frappe.ui.Dialog({
                    title: __("Move Candidate Stage ({0})", [candName]),
                    fields: [
                        {
                            fieldname: "new_stage",
                            label: __("Target Pipeline Stage"),
                            fieldtype: "Select",
                            options: (opts.stages || []).join("\n"),
                            default: curStage,
                            reqd: 1,
                        },
                        {
                            fieldname: "remarks",
                            label: __("Audit Note / Reason (Optional)"),
                            fieldtype: "Small Text",
                        },
                    ],
                    primary_action_label: __("Update Stage"),
                    primary_action(values) {
                        d.hide();
                        frappe.call({
                            method: "xavirgin_os.xavirgin_os.doctype.xavirgin_candidate.xavirgin_candidate.update_candidate_stage",
                            args: {
                                candidate_name: candName,
                                new_stage: values.new_stage,
                                remarks: values.remarks || "",
                            },
                            callback() {
                                frappe.show_alert({ message: __("Moved {0} to {1}", [candName, values.new_stage]), indicator: "green" });
                                listview.refresh_pipeline_hub();
                                listview.refresh();
                            },
                        });
                    },
                });
                d.show();
            });

            $container.find(".xav-pipe-card").on("click", function () {
                const candName = $(this).attr("data-cand");
                if (candName) frappe.set_route("Form", "Xavirgin Candidate", candName);
            });
        };

        listview.refresh_pipeline_hub();
    },

    refresh(listview) {
        if (listview.refresh_pipeline_hub) {
            listview.refresh_pipeline_hub();
        }
    },
};