frappe.pages["xavirgin-org-chart"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Xavirgin Organizational Hierarchy"),
		single_column: true,
	});

	let dept_field = page.add_field({
		fieldname: "department",
		label: __("Department"),
		fieldtype: "Link",
		options: "Department",
		change() {
			render_chart();
		},
	});

	let search_field = page.add_field({
		fieldname: "search",
		label: __("Search Employee / Role"),
		fieldtype: "Data",
		change() {
			render_chart();
		},
	});

	page.set_secondary_action(__("Refresh"), () => render_chart());

	const $container = $(`<div class="p-4" style="overflow-x:auto;"></div>`).appendTo(page.main);

	function build_tree(nodes) {
		const by_id = {};
		const roots = [];
		nodes.forEach((n) => {
			by_id[n.name] = { ...n, children: [] };
		});
		nodes.forEach((n) => {
			if (n.reports_to && by_id[n.reports_to]) {
				by_id[n.reports_to].children.push(by_id[n.name]);
			} else {
				roots.push(by_id[n.name]);
			}
		});
		return roots;
	}

	function render_node(node) {
		const lead_badge = node.custom_is_team_lead
			? `<span class="badge badge-primary ml-1" style="background:#7c3aed;color:#fff;">Team Lead</span>`
			: "";
		const cat_badge =
			node.custom_employment_category === "Intern"
				? `<span class="badge badge-info ml-1">Intern</span>`
				: `<span class="badge badge-success ml-1">Core</span>`;

		let children_html = "";
		if (node.children && node.children.length) {
			children_html = `<div class="ml-4 pl-3 mt-2" style="border-left: 2px solid #7c3aed;">
				${node.children.map((c) => render_node(c)).join("")}
			</div>`;
		}

		return `
			<div class="mb-2">
				<div class="d-inline-flex align-items-center p-2 rounded shadow-sm"
					style="background:#1e1b4b; color:#f8fafc; border:1px solid #4c1d95; min-width:270px; cursor:pointer;"
					onclick="frappe.set_route('Form', 'Employee', '${node.name}')">
					<div class="mr-3">
						${frappe.avatar(null, "avatar-medium", node.employee_name)}
					</div>
					<div>
						<div class="font-weight-bold" style="color:#e9d5ff;">
							${frappe.utils.escape_html(node.employee_name)} ${lead_badge} ${cat_badge}
						</div>
						<div class="small" style="color:#38bdf8;">
							${frappe.utils.escape_html(node.designation || "Team Member")} — ${frappe.utils.escape_html(node.department || "")}
						</div>
					</div>
				</div>
				${children_html}
			</div>
		`;
	}

	function render_chart() {
		frappe.call({
			method: "xavirgin_os.xavirgin_os.page.xavirgin_org_chart.xavirgin_org_chart.get_org_chart_nodes",
			args: {
				department: dept_field.get_value(),
				search: search_field.get_value(),
			},
			callback(r) {
				const nodes = r.message || [];
				if (!nodes.length) {
					$container.html(`<div class="text-muted p-4">${__("No active employees found matching criteria.")}</div>`);
					return;
				}
				const roots = build_tree(nodes);
				$container.html(roots.map((root) => render_node(root)).join(""));
			},
		});
	}

	render_chart();
};