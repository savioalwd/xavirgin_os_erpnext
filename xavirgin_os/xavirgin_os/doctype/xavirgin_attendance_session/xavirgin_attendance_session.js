frappe.ui.form.on("Xavirgin Attendance Session", {
    setup(frm) {
        frm.add_fetch("employee", "employee_name", "employee_name");
        frm.add_fetch("employee", "department", "department");
        frm.add_fetch("employee", "designation", "designation");
        frm.add_fetch("employee", "custom_team_lead", "team_lead");
    },

    employee(frm) {
        if (frm.doc.employee && !frm.doc.employee_name) {
            frappe.db.get_value(
                "Employee",
                frm.doc.employee,
                ["employee_name", "department", "designation", "custom_team_lead"],
                (r) => {
                    if (r) {
                        frm.set_value("employee_name", r.employee_name);
                        frm.set_value("department", r.department);
                        frm.set_value("designation", r.designation);
                        frm.set_value("team_lead", r.custom_team_lead);
                    }
                }
            );
        }
    },

    refresh(frm) {
        frm.add_custom_button(__("📈 Attendance Analytics"), () => {
            frappe.set_route("query-report", "Xavirgin Attendance Analytics");
        });

        if (frm.doc.status === "Working" && !frm.is_new()) {
            frm.add_custom_button(__("🔴 Stop Session & Log Tasks"), () => {
                let d = new frappe.ui.Dialog({
                    title: __("Check Out of Session #{0}", [frm.doc.daily_session_number || 1]),
                    fields: [
                        {
                            fieldname: "work_log",
                            label: __("Session Work Summary / Tasks Completed (Min 20 characters)"),
                            fieldtype: "Small Text",
                            reqd: 1,
                            default: frm.doc.work_log || "",
                        },
                    ],
                    primary_action_label: __("Submit Work Log & Check Out"),
                    primary_action: function(values) {
                        let log = (values.work_log || "").trim();
                        if (log.length < 20) {
                            frappe.msgprint({
                                title: __("Work Summary Too Short"),
                                message: __("Please enter at least <b>20 characters</b>. Currently: <b>{0} characters</b>.", [log.length]),
                                indicator: "red"
                            });
                            return;
                        }
                        d.hide();
                        frappe.call({
                            method: "xavirgin_os.xavirgin_os.doctype.xavirgin_attendance_session.xavirgin_attendance_session.stop_session",
                            args: {
                                work_log: log,
                                target_employee: frm.doc.employee,
                                session_name: frm.doc.name,
                            },
                            freeze: true,
                            freeze_message: __("Stopping session..."),
                            callback(r) {
                                if (r.message) {
                                    frappe.show_alert({ message: r.message.message, indicator: "blue" });
                                    frm.reload_doc();
                                }
                            },
                        });
                    }
                });
                d.show();
            }).addClass("btn-danger");
        }
    },
});