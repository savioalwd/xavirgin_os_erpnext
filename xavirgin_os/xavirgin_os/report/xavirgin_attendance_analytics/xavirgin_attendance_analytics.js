frappe.query_reports["Xavirgin Attendance Analytics"] = {
	filters: [
		{
			fieldname: "month_date",
			label: __("Reference Date (Month)"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "employment_category",
			label: __("Category"),
			fieldtype: "Select",
			options: "\nIntern\nRegular Employee",
			default: "Intern",
		},
		{
			fieldname: "leaderboard_mode",
			label: __("Leaderboard Filter"),
			fieldtype: "Select",
			options: "\nAll Active\nTop 5 Performers\nNeeds Improvement (Bottom 5)",
			default: "All Active",
		},
	],
};