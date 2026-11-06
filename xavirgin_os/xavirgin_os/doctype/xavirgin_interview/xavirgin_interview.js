frappe.ui.form.on("Xavirgin Interview", {
    setup(frm) {
        frm.add_fetch("candidate", "full_name", "candidate_name");
        frm.add_fetch("candidate", "email", "candidate_email");
        frm.add_fetch("candidate", "phone", "candidate_phone");
        frm.add_fetch("candidate", "job_opening", "job_opening");
        frm.add_fetch("candidate", "department", "department");
        frm.add_fetch("candidate", "designation", "designation");
    },

    onload(frm) {
        if (frm.is_new()) {
            frappe.db.get_single_value("Xavirgin HR Settings", "default_meet_link").then((link) => {
                if (link && !frm.doc.meeting_url) {
                    frm.set_value("meeting_url", link);
                }
            });

            frappe.db.get_single_value("Xavirgin HR Settings", "default_meeting_platform").then((platform) => {
                if (platform && !frm.doc.meeting_platform) {
                    frm.set_value("meeting_platform", platform);
                }
            });

            if (!frm.doc.interview_date) {
                frm.set_value("interview_date", frappe.datetime.get_today());
            }

            if (!frm.doc.start_time) {
                let now = moment();
                let remainder = 60 - now.minutes();
                let nextHour = now.add(remainder, "m").seconds(0);
                frm.set_value("start_time", nextHour.format("HH:mm:00"));
                frm.trigger("calculate_end_time");
            }

            if (!frm.doc.interview_instructions) {
                const defaultInstructions = `<div style="font-family: Arial, sans-serif; font-size: 13px; line-height: 1.6; color: #2d3748;">
    <h4 style="color: #0000FF; margin-bottom: 8px;">📌 Mandatory Online Interview Instructions</h4>
    <ol style="margin-top: 0; padding-left: 20px;">
        <li><strong>Early Arrival:</strong> Join the meeting at least <strong>5 minutes prior</strong> to the scheduled start time to test audio and camera readiness.</li>
        <li><strong>Hardware & Platform:</strong> Join <strong>exclusively via Laptop or Desktop</strong> with a working webcam and microphone. Mobile logins are strictly disallowed unless explicitly pre-approved by HR.</li>
        <li><strong>Connectivity:</strong> Ensure a stable broadband/high-speed internet connection in a quiet, well-lit, distraction-free environment.</li>
        <li><strong>Screen Sharing & IDE:</strong> Be ready to share your entire desktop screen and demonstrate live problem-solving using your primary local development environment / IDE.</li>
        <li><strong>Verification:</strong> Keep a valid government identity card accessible for visual identity verification at the start of the round.</li>
    </ol>
</div>`;
                frm.set_value("interview_instructions", defaultInstructions);
            }
        }
    },

    refresh(frm) {
        frm.trigger("render_12hour_time_badges");

        if (!frm.is_new()) {
            frm.trigger("load_comprehensive_overview");
        }
    },

    load_comprehensive_overview(frm) {
        frappe.call({
            method: "xavirgin_os.xavirgin_os.doctype.xavirgin_interview.xavirgin_interview.get_interview_comprehensive_overview",
            args: { interview_name: frm.doc.name },
            callback(r) {
                const data = r.message || {};

                // 1. Enforce Read-Only UI for non-HR / non-Admin viewers
                if (!data.can_manage) {
                    frm.disable_save();
                    frm.set_read_only();
                } else {
                    // Authorized HR/Admin Buttons
                    frm.add_custom_button(__("🔄 Reschedule / Send Updated Invite"), () => {
                        let d = new frappe.ui.Dialog({
                            title: __("Reschedule Interview & Notify Candidate + Panel"),
                            fields: [
                                {
                                    fieldname: "interview_date",
                                    label: __("New Interview Date"),
                                    fieldtype: "Date",
                                    default: frm.doc.interview_date,
                                    reqd: 1,
                                },
                                {
                                    fieldname: "start_time",
                                    label: __("New Start Time (24-Hr HH:mm:ss)"),
                                    fieldtype: "Time",
                                    default: frm.doc.start_time,
                                    reqd: 1,
                                },
                                {
                                    fieldname: "end_time",
                                    label: __("New End Time (24-Hr HH:mm:ss)"),
                                    fieldtype: "Time",
                                    default: frm.doc.end_time,
                                    reqd: 1,
                                },
                                {
                                    fieldname: "meeting_platform",
                                    label: __("Meeting Platform"),
                                    fieldtype: "Select",
                                    options: "Google Meet\nZoom\nMicrosoft Teams\nCustom WebRTC",
                                    default: frm.doc.meeting_platform || "Google Meet",
                                },
                                {
                                    fieldname: "meeting_url",
                                    label: __("Meeting URL"),
                                    fieldtype: "Data",
                                    default: frm.doc.meeting_url,
                                    reqd: 1,
                                },
                            ],
                            primary_action_label: __("Save & Dispatch Reschedule Emails"),
                            primary_action(values) {
                                d.hide();
                                frappe.call({
                                    doc: frm.doc,
                                    method: "reschedule_interview_and_notify",
                                    args: values,
                                    freeze: true,
                                    freeze_message: __("Updating schedule & sending notifications..."),
                                    callback(res) {
                                        if (res.message) {
                                            frappe.show_alert({ message: res.message, indicator: "green" });
                                            frm.reload_doc();
                                        }
                                    },
                                });
                            },
                        });
                        d.show();
                    });

                    frm.add_custom_button(__("📧 Re-Send Candidate Invitation"), () => {
                        frappe.confirm(
                            __("Send interview invitation email to {0}?", [frm.doc.candidate_email]),
                            () => {
                                frappe.call({
                                    doc: frm.doc,
                                    method: "send_candidate_interview_invitation",
                                    args: { is_rescheduled: 0 },
                                    freeze: true,
                                    freeze_message: __("Sending Technical Interview Invitation..."),
                                    callback(res) {
                                        if (res.message) {
                                            frappe.show_alert({ message: res.message, indicator: "green" });
                                            frm.reload_doc();
                                        }
                                    },
                                });
                            }
                        );
                    });
                }

                // 2. Scorecard Button for Assigned Panel Members & HR/Admins
                if (data.can_manage || data.is_panel_member) {
                    if (data.my_existing_evaluation) {
                        frm.add_custom_button(__("📝 Open My Scorecard ({0})", [data.my_existing_evaluation]), () => {
                            frappe.set_route("Form", "Xavirgin Interview Evaluation", data.my_existing_evaluation);
                        }).addClass("btn-primary");
                    } else {
                        frm.add_custom_button(__("📝 Submit My Scorecard"), () => {
                            frappe.new_doc("Xavirgin Interview Evaluation", {
                                interview: frm.doc.name,
                                candidate: frm.doc.candidate,
                                candidate_name: frm.doc.candidate_name,
                                job_opening: frm.doc.job_opening,
                                assessment_template: frm.doc.assessment_template,
                            });
                        }).addClass("btn-primary");
                    }
                }

                frm.events.render_comprehensive_header(frm, data);
            },
        });
    },

    render_comprehensive_header(frm, data) {
        const cand = data.candidate || {};
        const evals = data.evaluations || [];
        const otherInts = data.other_interviews || [];
        const docs = data.candidate_documents || [];
        const offers = data.offer_letters || [];

        const statusBadgeMap = {
            Scheduled: { bg: "#dbeafe", text: "#1e40af", border: "#93c5fd" },
            "In Progress": { bg: "#fef9c3", text: "#854d0e", border: "#fde047" },
            Completed: { bg: "#dcfce7", text: "#166534", border: "#86efac" },
            Rescheduled: { bg: "#f3e8ff", text: "#6b21a8", border: "#d8b4fe" },
            Cancelled: { bg: "#fee2e2", text: "#991b1b", border: "#fca5a5" },
            "No Show": { bg: "#fee2e2", text: "#991b1b", border: "#fca5a5" },
        };
        const stStyle = statusBadgeMap[frm.doc.status] || statusBadgeMap.Scheduled;

        // Related Records Navigation Bar
        let navButtons = [];
        if (cand.name) {
            navButtons.push(
                `<a href="/app/xavirgin-candidate/${encodeURIComponent(cand.name)}" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px;">👤 Candidate (${cand.name})</a>`
            );
        }
        if (frm.doc.job_opening) {
            navButtons.push(
                `<a href="/app/xavirgin-job-opening/${encodeURIComponent(frm.doc.job_opening)}" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px;">💼 Job Opening</a>`
            );
        }
        if (frm.doc.assessment_template) {
            navButtons.push(
                `<a href="/app/xavirgin-assessment-template/${encodeURIComponent(frm.doc.assessment_template)}" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px;">📋 Rubric (${data.template_max_marks || 10} Marks)</a>`
            );
        }
        navButtons.push(
            `<a href="/app/xavirgin-interview-evaluation?interview=${encodeURIComponent(frm.doc.name)}" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px;">📝 Evaluations (${evals.length}/${(frm.doc.interviewers || []).length})</a>`
        );
        if (otherInts.length > 1) {
            navButtons.push(
                `<a href="/app/xavirgin-interview?candidate=${encodeURIComponent(cand.name || "")}" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px;">🗓️ All Candidate Interviews (${otherInts.length})</a>`
            );
        }
        if (offers.length > 0) {
            navButtons.push(
                `<a href="/app/xavirgin-offer-letter/${encodeURIComponent(offers[0].name)}" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px;">📄 Offer Letter (${offers[0].workflow_state})</a>`
            );
        }
        if (cand.employee) {
            navButtons.push(
                `<a href="/app/employee/${encodeURIComponent(cand.employee)}" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px; background:#dcfce7; color:#166534;">🚀 Hired Employee (${cand.employee})</a>`
            );
        }
        if (cand.resume_attachment) {
            navButtons.push(
                `<a href="${cand.resume_attachment}" target="_blank" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px;">📎 View Resume</a>`
            );
        }
        docs.forEach((docItem) => {
            navButtons.push(
                `<a href="${docItem.url}" target="_blank" class="btn btn-xs btn-default" style="font-weight:600; border-radius:6px;">📎 ${frappe.utils.escape_html(docItem.title)}</a>`
            );
        });

        // Individual Panelist Evaluation Cards
        let evalCardsHtml = "";
        if (evals.length > 0) {
            evalCardsHtml = evals
                .map((ev) => {
                    const recColor =
                        ev.recommendation === "Strongly Recommended"
                            ? "#166534"
                            : ev.recommendation === "Recommended"
                            ? "#1e40af"
                            : ev.recommendation === "Hold"
                            ? "#854d0e"
                            : "#991b1b";

                    const critPills = (ev.criteria || [])
                        .map(
                            (c) =>
                                `<span style="background:#f1f5f9; color:#334155; padding:2px 8px; border-radius:6px; font-size:11px; font-weight:600;">
                                    ${frappe.utils.escape_html(c.criterion_name)}: <b>${c.score_obtained}/${c.max_marks}</b>
                                </span>`
                        )
                        .join(" ");

                    return `
                    <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px 12px; margin-bottom:8px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:6px;">
                            <div>
                                <a href="/app/xavirgin-interview-evaluation/${encodeURIComponent(ev.name)}" style="font-weight:700; font-size:13px; color:#2563eb; text-decoration:none;">
                                    👤 ${frappe.utils.escape_html(ev.interviewer_name)} (${ev.name})
                                </a>
                                <span style="font-size:11px; color:#64748b; margin-left:6px;">• ${ev.evaluation_date} (${ev.status})</span>
                            </div>
                            <div style="display:flex; align-items:center; gap:8px;">
                                <span style="background:#e0e7ff; color:#3730a3; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700;">
                                    Score: ${ev.total_score} / ${ev.max_possible_score} (${ev.percentage}%)
                                </span>
                                <span style="color:${recColor}; font-weight:700; font-size:12px;">
                                    ${frappe.utils.escape_html(ev.recommendation)}
                                </span>
                            </div>
                        </div>
                        <div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:6px;">
                            ${critPills}
                        </div>
                        ${
                            ev.strengths || ev.weaknesses
                                ? `<div style="font-size:11px; color:#475569; display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:4px;">
                                    <div><strong style="color:#15803d;">Strengths:</strong> ${frappe.utils.escape_html(ev.strengths || "-")}</div>
                                    <div><strong style="color:#b91c1c;">Weaknesses:</strong> ${frappe.utils.escape_html(ev.weaknesses || "-")}</div>
                                   </div>`
                                : ""
                        }
                    </div>`;
                })
                .join("");
        } else {
            evalCardsHtml = `<div style="font-size:12px; color:#64748b; padding:8px 0;">No panel evaluations submitted yet for this round.</div>`;
        }

        const html = `
            <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:14px 16px; margin-bottom:12px; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
                <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px; border-bottom:1px solid #f1f5f9; padding-bottom:10px;">
                    <div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px;">
                        <span style="background:${stStyle.bg}; color:${stStyle.text}; border:1px solid ${stStyle.border}; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px;">
                            📅 ${frappe.utils.escape_html(frm.doc.status)}
                        </span>
                        <span style="background:#f3e8ff; color:#6b21a8; border:1px solid #d8b4fe; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px;">
                            🛡️ ${frappe.utils.escape_html(frm.doc.department || cand.department || "Unassigned")}
                        </span>
                        <span style="background:#e0f2fe; color:#0369a1; border:1px solid #bae6fd; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px;">
                            🎯 Stage: ${frappe.utils.escape_html(cand.pipeline_stage || "Interview Scheduled")}
                        </span>
                        <span style="background:#fef3c7; color:#92400e; border:1px solid #fde68a; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px;">
                            ⏰ ${data.formatted_date} • ${data.formatted_start_12h} – ${data.formatted_end_12h}
                        </span>
                    </div>
                    <div>
                        ${
                            frm.doc.meeting_url
                                ? `<a href="${frm.doc.meeting_url}" target="_blank" class="btn btn-xs btn-primary" style="font-weight:700; border-radius:6px;">🔗 Join ${frappe.utils.escape_html(frm.doc.meeting_platform || "Meeting")}</a>`
                                : ""
                        }
                    </div>
                </div>

                <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:10px; padding:10px 0; border-bottom:1px solid #f1f5f9; font-size:12px;">
                    <div>
                        <div style="color:#64748b; font-size:10px; font-weight:700; text-transform:uppercase;">Candidate</div>
                        <div style="font-weight:700; color:#0f172a; font-size:13px;">${frappe.utils.escape_html(cand.full_name || frm.doc.candidate_name)}</div>
                        <div style="color:#475569;">${frappe.utils.escape_html(cand.email || frm.doc.candidate_email || "-")} • ${frappe.utils.escape_html(cand.phone || frm.doc.candidate_phone || "-")}</div>
                    </div>
                    <div>
                        <div style="color:#64748b; font-size:10px; font-weight:700; text-transform:uppercase;">Position & Track</div>
                        <div style="font-weight:700; color:#0f172a;">${frappe.utils.escape_html(cand.designation || frm.doc.designation || "-")}</div>
                        <div style="color:#475569;">Applied: ${cand.application_date || "-"}</div>
                    </div>
                    <div>
                        <div style="color:#64748b; font-size:10px; font-weight:700; text-transform:uppercase;">Panel Rollup & Consensus</div>
                        <div style="font-weight:700; color:#2563eb;">Avg Score: ${frm.doc.average_score || 0} / ${data.template_max_marks || 10}</div>
                        <div style="font-weight:600; color:#4f46e5;">${frappe.utils.escape_html(frm.doc.consensus_recommendation || "Awaiting Evaluations")}</div>
                    </div>
                </div>

                <div style="margin-top:10px;">
                    <div style="font-size:11px; font-weight:700; text-transform:uppercase; color:#64748b; margin-bottom:6px;">
                        🔗 Related Recruitment & HR Records
                    </div>
                    <div style="display:flex; flex-wrap:wrap; gap:6px;">
                        ${navButtons.join("")}
                    </div>
                </div>

                <div style="margin-top:12px; padding-top:10px; border-top:1px solid #f1f5f9;">
                    <div style="font-size:11px; font-weight:700; text-transform:uppercase; color:#64748b; margin-bottom:6px;">
                        🧑‍⚖️ Individual Interview Panel Evaluations (${evals.length} Submitted / ${(frm.doc.interviewers || []).length} Assigned)
                    </div>
                    ${evalCardsHtml}
                </div>
            </div>
        `;

        frm.dashboard.clear_headline();
        frm.dashboard.set_headline_alert(html);
    },

    candidate(frm) {
        if (frm.doc.candidate) {
            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_candidate.xavirgin_candidate.get_candidate_lifecycle_context",
                args: { candidate_name: frm.doc.candidate },
                callback(r) {
                    const data = r.message || {};
                    if (data.job_opening) {
                        frm.set_value("job_opening", data.job_opening);
                        frappe.db.get_value("Xavirgin Job Opening", data.job_opening, "assessment_template", (res) => {
                            if (res && res.assessment_template) {
                                frm.set_value("assessment_template", res.assessment_template);
                            }
                        });
                    }
                    if (data.department) frm.set_value("department", data.department);
                    if (data.designation) frm.set_value("designation", data.designation);
                },
            });
        }
    },

    start_time(frm) {
        frm.trigger("calculate_end_time");
        frm.trigger("render_12hour_time_badges");
    },

    end_time(frm) {
        frm.trigger("render_12hour_time_badges");
    },

    calculate_end_time(frm) {
        if (!frm.doc.start_time) return;

        frappe.db.get_single_value("Xavirgin HR Settings", "default_meeting_duration_mins").then((duration) => {
            let durationMins = parseInt(duration || 40);
            let start = moment(frm.doc.start_time, "HH:mm:ss");
            if (start.isValid()) {
                let end = start.clone().add(durationMins, "minutes");
                frm.set_value("end_time", end.format("HH:mm:ss"));
            }
        });
    },

    render_12hour_time_badges(frm) {
        if (frm.fields_dict.start_time) {
            let startVal = frm.doc.start_time;
            if (startVal) {
                let formattedStart = moment(startVal, "HH:mm:ss").format("hh:mm A");
                frm.get_field("start_time").set_description(
                    `<span style="color:#0000FF; font-weight:600;">⏰ 12-Hour Display: ${formattedStart}</span>`
                );
            } else {
                frm.get_field("start_time").set_description("");
            }
        }

        if (frm.fields_dict.end_time) {
            let endVal = frm.doc.end_time;
            if (endVal) {
                let formattedEnd = moment(endVal, "HH:mm:ss").format("hh:mm A");
                frm.get_field("end_time").set_description(
                    `<span style="color:#0000FF; font-weight:600;">⏰ 12-Hour Display: ${formattedEnd}</span>`
                );
            } else {
                frm.get_field("end_time").set_description("");
            }
        }
    },
});

frappe.ui.form.on("Xavirgin Interview Participant", {
    employee(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.employee) {
            frappe.db.get_value(
                "Employee",
                row.employee,
                ["employee_name", "company_email", "personal_email", "user_id", "designation", "department"],
                (r) => {
                    if (r) {
                        frappe.model.set_value(cdt, cdn, "full_name", r.employee_name);
                        frappe.model.set_value(cdt, cdn, "interviewer_user", r.user_id || "");
                        frappe.model.set_value(cdt, cdn, "designation", r.designation || "");
                        frappe.model.set_value(cdt, cdn, "department", r.department || "");

                        let candidateEmail = r.company_email || r.personal_email;
                        if (candidateEmail) {
                            frappe.model.set_value(cdt, cdn, "email", candidateEmail.trim().toLowerCase());
                        } else if (r.user_id) {
                            frappe.db.get_value("User", r.user_id, "email", (u) => {
                                if (u && u.email) {
                                    frappe.model.set_value(cdt, cdn, "email", u.email.trim().toLowerCase());
                                }
                            });
                        }
                    }
                }
            );
        }
    },

    interviewer_user(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.interviewer_user && !row.employee) {
            frappe.db.get_value("User", row.interviewer_user, ["full_name", "email"], (u) => {
                if (u) {
                    if (!row.full_name) frappe.model.set_value(cdt, cdn, "full_name", u.full_name);
                    if (!row.email) frappe.model.set_value(cdt, cdn, "email", (u.email || "").trim().toLowerCase());
                }
            });
        }
    },
});