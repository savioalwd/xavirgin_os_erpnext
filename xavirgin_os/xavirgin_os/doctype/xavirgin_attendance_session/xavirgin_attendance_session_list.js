frappe.listview_settings["Xavirgin Attendance Session"] = {
    onload(listview) {
        function mount_top_left_analytics_button() {
            let $title_area = listview.page.wrapper.find(".page-head .page-title");
            if ($title_area.length && !$title_area.find(".btn-xav-top-analytics").length) {
                let $btn_analytics = $(`
                    <button class="btn btn-primary btn-sm btn-xav-top-analytics" style="margin-left: 12px; font-weight: 600; background-color: #0066cc; border: none; padding: 4px 10px; vertical-align: middle; box-shadow: 0 1px 3px rgba(0,0,0,0.15); display: inline-flex; align-items: center; gap: 4px;">
                        <span>📈</span> <span>${__("Attendance Analytics & Leaderboard")}</span>
                    </button>
                `);
                $btn_analytics.on("click", (e) => {
                    e.preventDefault();
                    frappe.set_route("query-report", "Xavirgin Attendance Analytics");
                });
                $title_area.append($btn_analytics);
            }
        }

        mount_top_left_analytics_button();

        listview.refresh_session_buttons = function() {
            frappe.call({
                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session.get_today_session_status",
                callback(r) {
                    const info = r.message || {};
                    if (!info.has_employee) return;

                    mount_top_left_analytics_button();
                    listview.page.clear_inner_toolbar();

                    listview.page.add_inner_button(
                        __("📊 Today: {0} Check-Ins ({1}h)", [info.today_checkin_count || 0, info.today_completed_hours || 0]),
                        () => {
                            listview.refresh();
                            listview.refresh_session_buttons();
                        }
                    );

                    if (!info.active_session) {
                        let $btn_in = listview.page.add_inner_button(__("🟢 CHECK IN (Session #{0})", [(info.today_checkin_count || 0) + 1]), () => {
                            frappe.call({
                                method: "xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session.start_session",
                                args: { target_employee: info.employee },
                                freeze: true,
                                freeze_message: __("Starting session..."),
                                callback(res) {
                                    if (res.message) {
                                        frappe.show_alert({ message: res.message.message, indicator: "green" });
                                        listview.refresh();
                                        listview.refresh_session_buttons();
                                    }
                                },
                            });
                        });
                        $btn_in.css({ "background-color": "#16a34a", color: "#fff", "font-weight": "bold" });
                    } else {
                        let $btn_out = listview.page.add_inner_button(__("🔴 CHECK OUT ({0})", [info.active_session]), () => {
                            let d = new frappe.ui.Dialog({
                                title: __("Check Out of Session #{0}", [info.today_checkin_count || 1]),
                                fields: [
                                    {
                                        fieldname: "work_log",
                                        label: __("Session Work Summary / Tasks Completed (Min 20 characters)"),
                                        fieldtype: "Small Text",
                                        reqd: 1,
                                        description: __("Describe the tasks completed during this work session in detail.")
                                    }
                                ],
                                primary_action_label: __("Submit Work Log & Check Out"),
                                primary_action: function(values) {
                                    let log = (values.work_log || "").trim();
                                    if (log.length < 20) {
                                        frappe.msgprint({
                                            title: __("Work Summary Too Short"),
                                            message: __("Please enter at least <b>20 characters</b> describing your completed work. Currently: <b>{0} characters</b>.", [log.length]),
                                            indicator: "red"
                                        });
                                        return;
                                    }
                                    d.hide();
                                    frappe.call({
                                        method: "xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session.stop_session",
                                        args: {
                                            work_log: log,
                                            target_employee: info.employee,
                                            session_name: info.active_session
                                        },
                                        freeze: true,
                                        freeze_message: __("Submitting Work Log & Closing Session..."),
                                        callback(res) {
                                            if (res.message) {
                                                frappe.show_alert({ message: res.message.message, indicator: "blue" });
                                                listview.refresh();
                                                listview.refresh_session_buttons();
                                            }
                                        },
                                    });
                                }
                            });
                            d.show();
                        });
                        $btn_out.css({ "background-color": "#dc2626", color: "#fff", "font-weight": "bold" });
                    }

                    listview.page.add_inner_button(__("🏆 XP & Rules"), () => {
                        frappe.msgprint({
                            title: __("🏆 Multi-Session Attendance & Gamification Rules"),
                            message: `
                                <div style="line-height:1.6;">
                                    <p><b>🔄 Multi-Session Support:</b> You can Check In and Check Out multiple times per day.</p>
                                    <p><b>🟢 Daily Check-In Reward:</b> +10 XP on your 1st Check-In of the day.</p>
                                    <p><b>⏳ Cumulative Hours >= 1h:</b> +5 Bonus XP</p>
                                    <p><b>🔥 Cumulative Hours >= 4h:</b> +20 Total Bonus XP + Counts as 1 Active Working Day toward your 90-Day Certificate!</p>
                                </div>
                            `,
                            indicator: "purple",
                        });
                    });
                },
            });
        };

        listview.refresh_session_buttons();
    },
};