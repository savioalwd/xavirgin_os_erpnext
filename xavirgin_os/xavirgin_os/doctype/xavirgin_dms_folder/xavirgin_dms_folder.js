frappe.ui.form.on("Xavirgin DMS Folder", {
    refresh(frm) {
        if (frm.is_new()) return;

        // 1. Quick Upload File Button
        frm.add_custom_button(__("📎 Upload File"), () => {
            let d = new frappe.ui.Dialog({
                title: __("Upload Document to {0}", [frm.doc.folder_name]),
                fields: [
                    {
                        fieldname: "title",
                        label: __("Document Title / Name"),
                        fieldtype: "Data",
                        reqd: 1
                    },
                    {
                        fieldname: "file_attachment",
                        label: __("Select File (Private)"),
                        fieldtype: "Attach",
                        reqd: 1
                    },
                    {
                        fieldname: "notes",
                        label: __("Description / Notes"),
                        fieldtype: "Small Text"
                    }
                ],
                primary_action_label: __("Save & Upload"),
                primary_action(values) {
                    frm.add_child("files", {
                        item_type: "File Attachment",
                        title: values.title,
                        file_attachment: values.file_attachment,
                        folder: frm.doc.name,
                        notes: values.notes || ""
                    });
                    frm.refresh_field("files");
                    frm.save();
                    d.hide();
                    frappe.show_alert({ message: __("File added to folder queue. Click Save."), indicator: "green" });
                }
            });
            d.show();
        }).addClass("btn-primary");

        // 2. Quick Add Login Credential Button
        frm.add_custom_button(__("🔑 Add Secure Credential"), () => {
            let d = new frappe.ui.Dialog({
                title: __("Add Portal Credential to {0}", [frm.doc.folder_name]),
                fields: [
                    {
                        fieldname: "title",
                        label: __("Service Name (e.g. AWS Production)"),
                        fieldtype: "Data",
                        reqd: 1
                    },
                    {
                        fieldname: "credential_url",
                        label: __("Portal URL"),
                        fieldtype: "Data"
                    },
                    {
                        fieldname: "credential_username",
                        label: __("Username / Email"),
                        fieldtype: "Data",
                        reqd: 1
                    },
                    {
                        fieldname: "credential_password",
                        label: __("Password / Secret Key"),
                        fieldtype: "Password",
                        reqd: 1
                    },
                    {
                        fieldname: "notes",
                        label: __("Access Notes"),
                        fieldtype: "Small Text"
                    }
                ],
                primary_action_label: __("Save Credential"),
                primary_action(values) {
                    frm.add_child("files", {
                        item_type: "Login Credential",
                        title: values.title,
                        credential_url: values.credential_url,
                        credential_username: values.credential_username,
                        credential_password: values.credential_password,
                        folder: frm.doc.name,
                        notes: values.notes || ""
                    });
                    frm.refresh_field("files");
                    frm.save();
                    d.hide();
                    frappe.show_alert({ message: __("Credential added. Click Save."), indicator: "green" });
                }
            });
            d.show();
        });

        // 3. Export Folder ZIP Archive
        frm.add_custom_button(__("📦 Export Folder ZIP"), () => {
            window.open(`/api/method/xavirgin_os.xavirgin_os.doctype.xavirgin_dms_folder.xavirgin_dms_folder.export_folder_zip?folder_name=${frm.doc.name}`);
        }, __("Actions"));
    },
});