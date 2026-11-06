frappe.ui.form.on("Xavirgin Candidate", {
    setup(frm) {
        frm.add_fetch("job_opening", "department", "department");
        frm.add_fetch("job_opening", "designation", "designation");
        frm.add_fetch("job_opening", "engagement_category", "engagement_category");
        frm.add_fetch("job_opening", "skill_area", "skill_area");
        frm.add_fetch("job_opening", "assigned_recruiter", "assigned_recruiter");
    },

    full_name(frm) {
        if (frm.doc.full_name) {
            let parts = frm.doc.full_name.trim().split(" ");
            let first = parts[0] || "";
            let rest = parts.slice(1).join(" ") || "";
            if (!frm.doc.first_name || frm.doc.first_name !== first) {
                frm.set_value("first_name", first);
            }
            if (!frm.doc.last_name || frm.doc.last_name !== rest) {
                frm.set_value("last_name", rest);
            }
        }
    },

    first_name(frm) {
        if (frm.doc.first_name) {
            let full = `${frm.doc.first_name} ${frm.doc.last_name || ""}`.trim();
            if (frm.doc.full_name !== full) {
                frm.set_value("full_name", full);
            }
        }
    },

    last_name(frm) {
        if (frm.doc.first_name) {
            let full = `${frm.doc.first_name} ${frm.doc.last_name || ""}`.trim();
            if (frm.doc.full_name !== full) {
                frm.set_value("full_name", full);
            }
        }
    },

    github_url(frm) {
        if (frm.doc.github_url) {
            let clean = frm.doc.github_url.trim().replace(/\/+$/, "");
            let handle = clean.split("/").pop();
            frm.set_value("github_username", handle);
        }
    },

    existing_employee(frm) {
        if (frm.doc.existing_employee) {
            frappe.db.get_value(
                "Employee",
                frm.doc.existing_employee,
                [
                    "employee_name",
                    "first_name",
                    "last_name",
                    "company_email",
                    "personal_email",
                    "cell_number",
                    "current_address",
                    "custom_github_username",
                    "department",
                    "designation",
                    "gender",
                    "date_of_birth",
                ],
                (r) => {
                    if (r) {
                        frm.set_value("full_name", r.employee_name);
                        frm.set_value("first_name", r.first_name);
                        frm.set_value("last_name", r.last_name);
                        frm.set_value("email", r.personal_email || r.company_email);
                        frm.set_value("phone", r.cell_number);
                        frm.set_value("address_line", r.current_address);
                        frm.set_value("gender", r.gender || "Prefer not to say");
                        if (r.date_of_birth) frm.set_value("date_of_birth", r.date_of_birth);
                        if (r.department) frm.set_value("department", r.department);
                        if (r.designation) frm.set_value("designation", r.designation);
                        if (r.custom_github_username) {
                            frm.set_value("github_username", r.custom_github_username);
                            frm.set_value("github_url", `https://github.com/${r.custom_github_username}`);
                        }
                    }
                }
            );
        }
    },

    refresh(frm) {
        if (frm.is_new()) return;

        frappe.call({
            method: "xavirgin_os.xavirgin_os.doctype.xavirgin_candidate.xavirgin_candidate.get_candidate_workspace_overview",
            args: { candidate_name: frm.doc.name },
            callback(r) {
                const data = r.message || {};
                if (!data.can_manage) {
                    frm.disable_save();
                    frm.set_read_only();
                } else {
                    frm.events.bind_hr_action_buttons(frm);
                }
                frm.events.render_candidate_workspace(frm, data);
            },
        });
    },

    bind_hr_action_buttons(frm) {
        if (!frm.doc.employee) {
            frm.add_custom_button(__("🚀 Convert to Employee / Intern"), () => {
                frappe.confirm(
                    __("Directly convert candidate <b>{0}</b> into an active ERPNext Employee record with auto-provisioned user access?", [frm.doc.full_name]),
                    () => {
                        frappe.call({
                            doc: frm.doc,
                            method: "convert_to_employee",
                            freeze: true,
                            freeze_message: __("Executing atomic Employee onboarding..."),
                            callback(r) {
                                if (r.message) {
                                    frappe.msgprint({
                                        title: __("Onboarding Complete"),
                                        message: __("Employee <b>{0}</b> created and linked to Candidate {1}.", [r.message, frm.doc.name]),
                                        indicator: "green",
                                    });
                                    frm.reload_doc();
                                }
                            },
                        });
                    }
                );
            }).addClass("btn-primary");
        } else {
            frm.add_custom_button(__("👤 View Employee Card"), () => {
                frappe.set_route("Form", "Employee", frm.doc.employee);
            }, __("Lineage"));
        }

        frm.add_custom_button(__("✨ Run AI Screening"), () => {
            frappe.call({
                doc: frm.doc,
                method: "run_ai_screening",
                freeze: true,
                freeze_message: __("Evaluating candidate profile against job opening..."),
                callback(r) {
                    if (r.message) {
                        frm.reload_doc();
                        frappe.show_alert({
                            message: __("AI Screening complete! Match Score: {0}/10", [r.message.score]),
                            indicator: "green",
                        });
                    }
                },
            });
        }, __("AI Assistant"));

        frm.add_custom_button(__("📅 Schedule Interview"), () => {
            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_candidate.xavirgin_candidate.get_candidate_lifecycle_context",
                args: { candidate_name: frm.doc.name },
                callback(r) {
                    const ctx = r.message || {};
                    frappe.new_doc("Xavirgin Interview", {
                        candidate: ctx.name,
                        candidate_name: ctx.full_name,
                        candidate_email: ctx.email,
                        job_opening: ctx.job_opening,
                        department: ctx.department,
                    });
                },
            });
        }, __("Recruitment Actions"));

        if (!frm.doc.employee) {
            frm.add_custom_button(__("📄 Generate Offer Letter & NDA"), () => {
                frappe.call({
                    method: "xavirgin_os.xavirgin_os.doctype.xavirgin_candidate.xavirgin_candidate.get_candidate_lifecycle_context",
                    args: { candidate_name: frm.doc.name },
                    callback(r) {
                        const ctx = r.message || {};
                        frappe.new_doc("Xavirgin Offer Letter", {
                            candidate: ctx.name,
                            candidate_name: ctx.full_name,
                            candidate_email: ctx.email,
                            candidate_phone: ctx.phone,
                            candidate_address: ctx.address_line,
                            job_opening: ctx.job_opening,
                            department: ctx.department,
                            designation: ctx.designation,
                            engagement_category: ctx.engagement_category,
                            skill_area: ctx.skill_area,
                        });
                    },
                });
            }, __("Recruitment Actions"));
        }

        frm.add_custom_button(__("⚖️ Record HR Decision"), () => {
            frappe.prompt(
                [
                    {
                        fieldname: "decision",
                        label: __("Decision"),
                        fieldtype: "Select",
                        options: "Schedule Next Interview\nRequest Technical Assessment\nPut On Hold\nInitiate Offer Letter\nReject Candidate",
                        reqd: 1,
                    },
                    {
                        fieldname: "reason",
                        label: __("Candidate-Safe Reason (Sent in Email if Rejected)"),
                        fieldtype: "Small Text",
                    },
                    {
                        fieldname: "internal_remarks",
                        label: __("Confidential HR Internal Notes"),
                        fieldtype: "Small Text",
                    },
                ],
                (values) => {
                    frappe.call({
                        doc: frm.doc,
                        method: "record_hr_decision",
                        args: values,
                        freeze: true,
                        callback() {
                            frm.reload_doc();
                        },
                    });
                },
                __("Record Candidate Decision"),
                __("Confirm Decision")
            );
        }, __("Recruitment Actions"));
    },

    render_candidate_workspace(frm, data) {
        const initials = (frm.doc.full_name || "C")
            .split(" ")
            .map((p) => p[0])
            .join("")
            .substring(0, 2)
            .toUpperCase();

        // 1. Outcome Banner (Hired vs Rejected vs Active Pipeline)
        let outcomeBanner = "";
        const emp = data.employee_info || {};
        if (data.is_hired) {
            outcomeBanner = `
            <div style="background:linear-gradient(90deg, #dcfce7 0%, #f0fdf4 100%); border:1px solid #86efac; border-radius:8px; padding:10px 14px; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div>
                    <span style="font-weight:800; color:#166534; font-size:13px;">🎉 HIRED & ONBOARDED</span>
                    <span style="color:#15803d; font-size:12px; margin-left:8px;">
                        Converted to Employee <b>${frappe.utils.escape_html(emp.name || frm.doc.employee || "")}</b>
                        ${emp.formatted_joining ? `on ${emp.formatted_joining}` : ""}
                        ${emp.custom_badge_level ? `• 🏆 ${emp.custom_badge_level} (${emp.custom_xp_points || 0} XP)` : ""}
                    </span>
                </div>
                ${
                    emp.name || frm.doc.employee
                        ? `<a href="/app/employee/${encodeURIComponent(emp.name || frm.doc.employee)}" class="btn btn-xs btn-success" style="font-weight:700;">👤 Open Employee Profile →</a>`
                        : ""
                }
            </div>`;
        } else if (data.is_rejected) {
            outcomeBanner = `
            <div style="background:#fef2f2; border:1px solid #fca5a5; border-radius:8px; padding:10px 14px; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div>
                    <span style="font-weight:800; color:#991b1b; font-size:13px;">🛑 OUTCOME: ${frappe.utils.escape_html(data.current_stage.toUpperCase())}</span>
                    <span style="color:#b91c1c; font-size:12px; margin-left:8px;">
                        ${frm.doc.decision_reason ? `Reason: ${frappe.utils.escape_html(frm.doc.decision_reason)}` : "Application closed."}
                    </span>
                </div>
            </div>`;
        } else {
            const nextIv = (data.interviews || [])[0];
            outcomeBanner = `
            <div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; padding:10px 14px; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div>
                    <span style="font-weight:800; color:#1e40af; font-size:13px;">🚀 ACTIVE PIPELINE: ${frappe.utils.escape_html(data.current_stage)}</span>
                    <span style="color:#1d4ed8; font-size:12px; margin-left:8px;">
                        ${
                            nextIv
                                ? `Latest Interview: <b>${nextIv.interview_round}</b> (${nextIv.status} on ${nextIv.formatted_date} at ${nextIv.formatted_time})`
                                : "No interview scheduled yet."
                        }
                    </span>
                </div>
                <span style="background:#dbeafe; color:#1e3a8a; font-weight:700; font-size:11px; padding:3px 10px; border-radius:999px;">
                    ⏳ ${data.days_in_pipeline || 0} Day(s) in Pipeline • ${data.progress_pct || 10}% Complete
                </span>
            </div>`;
        }

        // 2. Visual Progress Timeline
        const timelineHtml = (data.timeline || [])
            .map((step) => {
                let bg = "#f1f5f9",
                    color = "#64748b",
                    border = "#cbd5e1",
                    icon = "○";
                if (step.state === "completed") {
                    bg = "#dcfce7";
                    color = "#166534";
                    border = "#86efac";
                    icon = "✓";
                } else if (step.state === "current") {
                    bg = "#2563eb";
                    color = "#ffffff";
                    border = "#1d4ed8";
                    icon = "●";
                } else if (step.state === "rejected") {
                    bg = "#fee2e2";
                    color = "#991b1b";
                    border = "#fca5a5";
                    icon = "✕";
                }
                return `
                <div style="display:flex; flex-direction:column; align-items:center; min-width:95px; flex:1; text-align:center;">
                    <div style="background:${bg}; color:${color}; border:1px solid ${border}; padding:4px 8px; border-radius:999px; font-size:10px; font-weight:700; width:92%; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                        ${icon} ${frappe.utils.escape_html(step.stage)}
                    </div>
                    <div style="font-size:9px; color:#64748b; margin-top:3px; height:12px;">
                        ${step.date || ""}
                    </div>
                </div>`;
            })
            .join("");

        // 3. Related Records Cards
        const ivs = data.interviews || [];
        const evals = data.evaluations || [];
        const docs = data.documents || [];
        const offers = data.offers || [];

        const html = `
        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:14px 16px; margin-bottom:12px; box-shadow:0 1px 4px rgba(0,0,0,0.03);">
            ${outcomeBanner}

            <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:12px; padding-bottom:12px; border-bottom:1px solid #f1f5f9;">
                <div style="display:flex; align-items:center; gap:12px;">
                    <div style="width:46px; height:46px; border-radius:50%; background:linear-gradient(135deg, #2563eb, #7c3aed); color:#fff; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:16px;">
                        ${frappe.utils.escape_html(initials)}
                    </div>
                    <div>
                        <div style="font-size:16px; font-weight:800; color:#0f172a;">
                            ${frappe.utils.escape_html(frm.doc.full_name)}
                            <span style="font-size:12px; font-weight:600; color:#64748b; margin-left:6px;">(${frappe.utils.escape_html(frm.doc.name)})</span>
                        </div>
                        <div style="font-size:12px; color:#475569; margin-top:2px;">
                            📧 ${frappe.utils.escape_html(frm.doc.email || "-")} • 📞 ${frappe.utils.escape_html(frm.doc.phone || "-")}
                            ${frm.doc.location ? `• 📍 ${frappe.utils.escape_html(frm.doc.location)}` : ""}
                        </div>
                    </div>
                </div>

                <div style="display:flex; flex-wrap:wrap; gap:6px; align-items:center;">
                    <span style="background:#f3e8ff; color:#6b21a8; border:1px solid #d8b4fe; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700;">
                        🛡️ ${frappe.utils.escape_html(frm.doc.department || "Unassigned Dept")}
                    </span>
                    <span style="background:#e0f2fe; color:#0369a1; border:1px solid #bae6fd; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700;">
                        💼 ${frappe.utils.escape_html(data.job_title)}
                    </span>
                    <span style="background:#f1f5f9; color:#334155; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700;">
                        📡 Source: ${frappe.utils.escape_html(frm.doc.source || "Direct")}
                    </span>
                    <span style="background:#fef3c7; color:#92400e; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700;">
                        🤖 AI Match: ${frm.doc.ai_match_score || 0}/10
                    </span>
                    <span style="background:#e0e7ff; color:#3730a3; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700;">
                        ⭐ Eval Avg: ${frm.doc.average_evaluation_score || 0}
                    </span>
                </div>
            </div>

            <div style="margin-top:12px; padding-bottom:10px; border-bottom:1px solid #f1f5f9;">
                <div style="font-size:10px; font-weight:800; text-transform:uppercase; color:#64748b; margin-bottom:8px;">
                    📈 Recruitment Lifecycle Progress Tracker (Applied: ${data.applied_date})
                </div>
                <div style="display:flex; overflow-x:auto; gap:4px; padding-bottom:4px;">
                    ${timelineHtml}
                </div>
            </div>

            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:10px; margin-top:12px;">
                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px;">
                    <div style="font-size:11px; font-weight:800; color:#0f172a; margin-bottom:6px; display:flex; justify-content:space-between;">
                        <span>🗓️ Interviews (${ivs.length})</span>
                        <a href="/app/xavirgin-interview?candidate=${encodeURIComponent(frm.doc.name)}" style="font-size:11px; color:#2563eb;">View All →</a>
                    </div>
                    ${
                        ivs.length
                            ? ivs
                                  .slice(0, 2)
                                  .map(
                                      (i) => `<div style="font-size:11px; margin-bottom:4px;">
                                        <a href="/app/xavirgin-interview/${encodeURIComponent(i.name)}" style="font-weight:700; color:#2563eb;">${frappe.utils.escape_html(i.interview_round)}</a>
                                        <span style="color:#64748b;">• ${i.formatted_date} (${i.status})</span>
                                      </div>`
                                  )
                                  .join("")
                            : `<div style="font-size:11px; color:#94a3b8;">No interviews scheduled</div>`
                    }
                </div>

                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px;">
                    <div style="font-size:11px; font-weight:800; color:#0f172a; margin-bottom:6px; display:flex; justify-content:space-between;">
                        <span>📝 Panel Evaluations (${evals.length})</span>
                        <a href="/app/xavirgin-interview-evaluation?candidate=${encodeURIComponent(frm.doc.name)}" style="font-size:11px; color:#2563eb;">View All →</a>
                    </div>
                    ${
                        evals.length
                            ? evals
                                  .slice(0, 2)
                                  .map(
                                      (ev) => `<div style="font-size:11px; margin-bottom:4px;">
                                        <a href="/app/xavirgin-interview-evaluation/${encodeURIComponent(ev.name)}" style="font-weight:700; color:#2563eb;">${frappe.utils.escape_html(ev.interviewer_name)}</a>
                                        <span style="color:#475569;">• <b>${ev.total_score}/${ev.max_possible_score}</b> (${ev.recommendation || "Scored"})</span>
                                      </div>`
                                  )
                                  .join("")
                            : `<div style="font-size:11px; color:#94a3b8;">No evaluations submitted</div>`
                    }
                </div>

                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px;">
                    <div style="font-size:11px; font-weight:800; color:#0f172a; margin-bottom:6px;">
                        📎 Resume & Documents (${docs.length})
                    </div>
                    <div style="display:flex; flex-wrap:wrap; gap:4px;">
                        ${
                            docs.length
                                ? docs
                                      .map(
                                          (d) => `<a href="${d.url}" target="_blank" class="btn btn-xs btn-default" style="font-size:10px; font-weight:600;">
                                            ${d.verified ? "✅" : "📄"} ${frappe.utils.escape_html(d.type)}
                                          </a>`
                                      )
                                      .join("")
                                : `<span style="font-size:11px; color:#94a3b8;">No documents attached</span>`
                        }
                        ${frm.doc.github_url ? `<a href="${frm.doc.github_url}" target="_blank" class="btn btn-xs btn-default" style="font-size:10px; font-weight:600;">💻 GitHub</a>` : ""}
                        ${frm.doc.linkedin_url ? `<a href="${frm.doc.linkedin_url}" target="_blank" class="btn btn-xs btn-default" style="font-size:10px; font-weight:600;">🔗 LinkedIn</a>` : ""}
                        ${frm.doc.portfolio_url ? `<a href="${frm.doc.portfolio_url}" target="_blank" class="btn btn-xs btn-default" style="font-size:10px; font-weight:600;">🌐 Portfolio</a>` : ""}
                    </div>
                </div>

                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px;">
                    <div style="font-size:11px; font-weight:800; color:#0f172a; margin-bottom:6px;">
                        🚀 Offer & Onboarding Lineage
                    </div>
                    ${
                        offers.length
                            ? `<div style="font-size:11px; margin-bottom:4px;">
                                📄 Offer: <a href="/app/xavirgin-offer-letter/${encodeURIComponent(offers[0].name)}" style="font-weight:700; color:#2563eb;">${offers[0].name}</a> (${offers[0].workflow_state})
                               </div>`
                            : `<div style="font-size:11px; color:#64748b;">No Offer Letter issued</div>`
                    }
                    ${
                        emp.name
                            ? `<div style="font-size:11px;">
                                👤 Employee: <a href="/app/employee/${encodeURIComponent(emp.name)}" style="font-weight:700; color:#16a34a;">${emp.name}</a>
                                • <a href="/app/xavirgin-attendance-session?employee=${encodeURIComponent(emp.name)}" style="color:#2563eb;">${data.attendance_count || 0} Attendance Sessions</a>
                               </div>`
                            : ""
                    }
                </div>
            </div>
        </div>`;

        frm.dashboard.clear_headline();
        frm.dashboard.set_headline_alert(html);
    },
});