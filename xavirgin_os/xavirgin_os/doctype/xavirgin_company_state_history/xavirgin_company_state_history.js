frappe.ui.form.on("Xavirgin Company State History", {
    refresh(frm) {
        if (frm.doc.approval_status === "Pending Approval") {
            frm.add_custom_button(__("✅ Approve & Apply to Company State"), () => {
                frappe.confirm(
                    __("Are you sure you want to merge these AI proposed updates into the active Company State?"),
                    () => {
                        frappe.call({
                            method: "xavirgin_os.company_state.apply_proposed_state_updates",
                            args: { history_name: frm.doc.name },
                            freeze: true,
                            freeze_message: __("Updating persistent company state..."),
                            callback(r) {
                                if (!r.exc) {
                                    frappe.show_alert({ message: __("Company State successfully updated!"), indicator: "green" });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                ).addClass("btn-primary");
            });

            frm.add_custom_button(__("❌ Reject"), () => {
                frm.set_value("approval_status", "Rejected");
                frm.save();
            }).addClass("btn-danger");
        }
    }
});