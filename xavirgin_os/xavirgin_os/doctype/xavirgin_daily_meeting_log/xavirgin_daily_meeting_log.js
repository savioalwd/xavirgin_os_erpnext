frappe.ui.form.on("Xavirgin Daily Meeting Log", {
    setup(frm) {
        frm.add_fetch("department", "department_name", "department");
    },

    onload(frm) {
        // Automatically pre-populate all active employees when creating a new record
        if (frm.is_new() && (!frm.doc.entries || frm.doc.entries.length === 0)) {
            frm.trigger("load_active_participants");
        }
    },

    department(frm) {
        // When department filter changes, offer to re-populate
        if (frm.doc.entries && frm.doc.entries.length > 0) {
            frappe.confirm(
                __("Department changed. Do you want to reload the team members for this department?"),
                () => {
                    frm.trigger("load_active_participants");
                }
            );
        } else {
            frm.trigger("load_active_participants");
        }
    },

    load_active_participants(frm) {
        frappe.call({
            doc: frm.doc,
            method: "populate_active_interns",
            freeze: true,
            freeze_message: __("Loading all active team members..."),
            callback(r) {
                if (r.message) {
                    frm.refresh_field("entries");
                    frm.trigger("recalculate_tallies");
                    frappe.show_alert({
                        message: __("{0} active team members loaded. All marked Present.", [r.message]),
                        indicator: "green",
                    });
                }
            },
        });
    },

    recalculate_tallies(frm) {
        let present = 0;
        let absent = 0;
        let excused = 0;

        (frm.doc.entries || []).forEach((row) => {
            if (row.status === "Present") present++;
            else if (row.status === "Absent") absent++;
            else if (row.status === "Excused (Approved Meeting Leave)") excused++;
        });

        frm.set_value("present_count", present);
        frm.set_value("absent_count", absent);
        frm.set_value("excused_count", excused);
        frm.set_value("total_participants", (frm.doc.entries || []).length);
    },

    refresh(frm) {
        // Admin Quick Action: Mark All Present
        frm.add_custom_button(__("✅ Mark All Present"), () => {
            (frm.doc.entries || []).forEach((row) => {
                if (row.status !== "Excused (Approved Meeting Leave)") {
                    frappe.model.set_value(row.doctype, row.name, "status", "Present");
                }
            });
            frm.trigger("recalculate_tallies");
            frappe.show_alert({ message: __("All team members set to Present."), indicator: "green" });
        }, __("Quick Attendance"));

        // Admin Quick Action: Mark All Absent
        frm.add_custom_button(__("❌ Mark All Absent"), () => {
            (frm.doc.entries || []).forEach((row) => {
                if (row.status !== "Excused (Approved Meeting Leave)") {
                    frappe.model.set_value(row.doctype, row.name, "status", "Absent");
                }
            });
            frm.trigger("recalculate_tallies");
            frappe.show_alert({ message: __("All team members set to Absent."), indicator: "orange" });
        }, __("Quick Attendance"));

        // Reload/Generate list button
        frm.add_custom_button(__("⚡ Reload Team Members"), () => {
            frm.trigger("load_active_participants");
        });

        if (frm.doc.meeting_url) {
            frm.add_custom_button(__("🔗 Open Google Meet"), () => {
                window.open(frm.doc.meeting_url, "_blank");
            });
        }
    },
});

frappe.ui.form.on("Xavirgin Daily Meeting Entry", {
    employee(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row.employee) return;

        // Disallow duplicate employee selection in child table
        let duplicates = (frm.doc.entries || []).filter(r => r.employee === row.employee);
        if (duplicates.length > 1) {
            frappe.msgprint({
                title: __("Duplicate Entry"),
                message: __("<b>{0}</b> is already present in this meeting list. Duplicate entries are not allowed.", [row.employee]),
                indicator: "red"
            });
            frappe.model.set_value(cdt, cdn, "employee", "");
            frappe.model.set_value(cdt, cdn, "employee_name", "");
            return;
        }

        // Default new manual rows to Present
        if (!row.status) {
            frappe.model.set_value(cdt, cdn, "status", "Present");
        }
        frm.trigger("recalculate_tallies");
    },

    status(frm) {
        frm.trigger("recalculate_tallies");
    },

    entries_remove(frm) {
        frm.trigger("recalculate_tallies");
    }
});