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
        // 1. Pull Global HR Settings & Prefill Defaults on New Records
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
                // Round up to the next top of the hour
                let now = moment();
                let remainder = 60 - now.minutes();
                let nextHour = now.add(remainder, "m").seconds(0);
                frm.set_value("start_time", nextHour.format("HH:mm:00"));
                frm.trigger("calculate_end_time");
            }

            // Populate Default Production-Grade Online Conduct Instructions
            if (!frm.doc.interview_instructions) {
                const defaultInstructions = 
`<div style="font-family: Arial, sans-serif; font-size: 13px; line-height: 1.6; color: #2d3748;">
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
            frm.add_custom_button(__("📧 Send Candidate Invitation"), () => {
                frappe.confirm(
                    __("Dispatch technical interview invitation and calendar details to {0}?", [frm.doc.candidate_email]),
                    () => {
                        frappe.call({
                            doc: frm.doc,
                            method: "send_candidate_interview_invitation",
                            freeze: true,
                            freeze_message: __("Sending Technical Interview Invitation..."),
                            callback(r) {
                                if (r.message) {
                                    frappe.show_alert({ message: r.message, indicator: "green" });
                                    frm.reload_doc();
                                }
                            },
                        });
                    }
                );
            }).addClass("btn-primary");

            frm.add_custom_button(__("📝 Submit My Scorecard"), () => {
                frappe.new_doc("Xavirgin Interview Evaluation", {
                    interview: frm.doc.name,
                    candidate: frm.doc.candidate,
                    candidate_name: frm.doc.candidate_name,
                    job_opening: frm.doc.job_opening,
                    assessment_template: frm.doc.assessment_template,
                });
            }, __("Actions"));
        }
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
                }
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
        // Formats military 24-hr field into user-friendly 12-hour AM/PM label
        if (frm.fields_dict.start_time) {
            let startVal = frm.doc.start_time;
            if (startVal) {
                let formattedStart = moment(startVal, "HH:mm:ss").format("hh:mm A");
                frm.get_field("start_time").set_description(
                    `<span style="color:#0000FF; font-weight:600;">⏰ 12-Hour: ${formattedStart}</span>`
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
                    `<span style="color:#0000FF; font-weight:600;">⏰ 12-Hour: ${formattedEnd}</span>`
                );
            } else {
                frm.get_field("end_time").set_description("");
            }
        }
    }
});

// Participant Auto-Fetch: Employee -> User -> Active Email Resolution
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

                        // Resolve Email: company_email -> personal_email -> User.email fallback
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
            frappe.db.get_value(
                "User",
                row.interviewer_user,
                ["full_name", "email"],
                (u) => {
                    if (u) {
                        if (!row.full_name) frappe.model.set_value(cdt, cdn, "full_name", u.full_name);
                        if (!row.email) frappe.model.set_value(cdt, cdn, "email", (u.email || "").trim().toLowerCase());
                    }
                }
            );
        }
    }
});