frappe.pages["xavirgin-org-chart"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Team Directory & Org Hierarchy"),
		single_column: true,
	});

	page.main.html(`
		<div class="xav-directory-container" style="max-width: 1400px; margin: 0 auto; padding: 15px 0;">
			<!-- Control Bar -->
			<div class="d-flex align-items-center justify-content-between flex-wrap gap-3 mb-4 p-3 bg-white rounded border shadow-sm">
				<div class="d-flex align-items-center gap-2 flex-grow-1 flex-wrap" style="max-width: 750px;">
					<div class="input-group" style="max-width: 240px;">
						<span class="input-group-text bg-light border-end-0"><i class="fa fa-filter text-muted"></i></span>
						<select id="xav-dept-filter" class="form-control form-select border-start-0">
							<option value="">All Departments</option>
						</select>
					</div>
					<div class="input-group flex-grow-1" style="min-width: 260px;">
						<span class="input-group-text bg-light border-end-0"><i class="fa fa-search text-muted"></i></span>
						<input type="text" id="xav-search-input" class="form-control border-start-0" placeholder="Search by name, role, track, or employee ID..." />
					</div>
				</div>
				<div class="d-flex align-items-center gap-2">
					<span id="xav-member-count" class="badge bg-light text-dark border px-3 py-2 fw-semibold">0 Members</span>
					<button class="btn btn-sm btn-default" id="xav-refresh-btn" title="Reload Directory">
						<i class="fa fa-refresh"></i>
					</button>
				</div>
			</div>

			<!-- Team Grid -->
			<div id="xav-team-grid" class="row g-3">
				<div class="col-12 text-center py-5 text-muted">
					<i class="fa fa-spinner fa-spin fa-2x text-primary"></i>
					<p class="mt-2 font-monospace">Loading verified talent directory...</p>
				</div>
			</div>
		</div>
	`);

	let allEmployees = [];

	function renderCards(list) {
		const $grid = $("#xav-team-grid");
		$grid.empty();
		$("#xav-member-count").text(`${list.length} Members`);

		if (!list.length) {
			$grid.html(`
				<div class="col-12 text-center py-5 bg-white rounded border my-3">
					<div class="text-muted" style="font-size: 42px;">👥</div>
					<h5 class="fw-bold mt-2 text-dark">No Team Members Found</h5>
					<p class="text-muted small">Try refining your search terms or department filter.</p>
				</div>
			`);
			return;
		}

		list.forEach((emp) => {
			const initials = (emp.employee_name || "TM")
				.split(" ")
				.filter(Boolean)
				.map((n) => n[0])
				.slice(0, 2)
				.join("")
				.toUpperCase();

			// Tier styling
			let tierBadgeClass = "bg-secondary";
			let tierIcon = "🥉";
			if (emp.custom_badge_level === "Legend Tier") {
				tierBadgeClass = "bg-danger";
				tierIcon = "🔥";
			} else if (emp.custom_badge_level === "Gold Tier") {
				tierBadgeClass = "bg-warning text-dark";
				tierIcon = "🥇";
			} else if (emp.custom_badge_level === "Silver Tier") {
				tierBadgeClass = "bg-info text-dark";
				tierIcon = "🥈";
			}

			// Role badge
			const roleBadge = emp.custom_is_team_lead
				? `<span class="badge" style="background-color: #4f46e5; color: #fff; font-size: 10px;">★ Lead</span>`
				: emp.custom_is_intern
				? `<span class="badge bg-light text-dark border" style="font-size: 10px;">Intern</span>`
				: `<span class="badge bg-light text-primary border" style="font-size: 10px;">Core Staff</span>`;

			// Full image quality rendering
			const avatarHtml = emp.image
				? `<img src="${emp.image}" 
						alt="${emp.employee_name}" 
						class="rounded-circle xav-avatar-img" 
						style="width: 54px; height: 54px; object-fit: cover; object-position: center top; image-rendering: -webkit-optimize-contrast; cursor: zoom-in; border: 2px solid #e0e7ff;" 
						data-full-img="${emp.image}" 
						title="Click to view full photo" />`
				: `<div class="rounded-circle d-flex align-items-center justify-content-center fw-bold shadow-sm" 
						style="width: 54px; height: 54px; background: linear-gradient(135deg, #1e1b4b 0%, #4338ca 100%); color: #ffffff; font-size: 16px; border: 2px solid #c7d2fe; flex-shrink: 0;">
						${initials}
				   </div>`;

			// Quick action icons
			const emailBtn = emp.display_email
				? `<a href="mailto:${emp.display_email}" class="btn btn-xs btn-light border text-muted" title="${emp.display_email}">
						<i class="fa fa-envelope"></i>
				   </a>`
				: "";

			const githubBtn = emp.clean_github
				? `<a href="https://github.com/${emp.clean_github}" target="_blank" class="btn btn-xs btn-light border text-dark" title="github.com/${emp.clean_github}">
						<i class="fa fa-github"></i>
				   </a>`
				: "";

			const card = `
				<div class="col-xl-3 col-lg-4 col-md-6 col-sm-12">
					<div class="card h-100 border rounded-3 bg-white shadow-sm xav-card-hover" style="transition: all 0.2s ease;">
						<div class="card-body p-3 d-flex flex-column justify-content-between">
							<div>
								<!-- Header: Avatar + Identity -->
								<div class="d-flex align-items-start gap-3 mb-2">
									${avatarHtml}
									<div class="overflow-hidden flex-grow-1">
										<div class="d-flex align-items-center justify-content-between gap-1">
											<span class="fw-bold text-dark text-truncate fs-6" title="${emp.employee_name}">${emp.employee_name}</span>
											${roleBadge}
										</div>
										<div class="text-muted small text-truncate mt-0" title="${emp.designation || 'Specialist'}">
											${emp.designation || 'Specialist'}
										</div>
										<div class="small fw-semibold text-primary text-truncate">
											${emp.department || 'Unassigned'}
										</div>
									</div>
								</div>

								<!-- Key Metrics Section -->
								<div class="bg-light rounded p-2 my-2 border" style="font-size: 11px;">
									<div class="d-flex justify-content-between align-items-center mb-1">
										<span class="text-muted">Skill Track:</span>
										<span class="fw-semibold text-dark text-truncate" style="max-width: 130px;">${emp.custom_skill_area || emp.designation || 'General Tech'}</span>
									</div>
									<div class="d-flex justify-content-between align-items-center mb-1">
										<span class="text-muted">Rank / XP:</span>
										<span class="badge ${tierBadgeClass} font-monospace">${tierIcon} ${emp.custom_xp_points || 0} XP</span>
									</div>
									<div class="d-flex justify-content-between align-items-center">
										<span class="text-muted">Active Days:</span>
										<span class="fw-bold text-dark font-monospace">${emp.custom_active_days_completed || 0} / 90</span>
									</div>
								</div>
							</div>

							<!-- Card Footer -->
							<div class="d-flex align-items-center justify-content-between pt-2 border-top mt-2">
								<div class="d-flex gap-1">
									${emailBtn}
									${githubBtn}
								</div>
								<button class="btn btn-xs btn-outline-primary xav-quick-view-btn" data-id="${emp.name}">
									View Profile →
								</button>
							</div>
						</div>
					</div>
				</div>
			`;
			$grid.append(card);
		});

		// Hover lift animation
		$(".xav-card-hover").hover(
			function () { $(this).css({ transform: "translateY(-3px)", "box-shadow": "0 10px 25px rgba(0,0,0,0.08)" }); },
			function () { $(this).css({ transform: "none", "box-shadow": "" }); }
		);

		// Click-to-enlarge high-res avatar
		$(".xav-avatar-img").on("click", function (e) {
			e.stopPropagation();
			const fullImgUrl = $(this).data("full-img");
			const imgDialog = new frappe.ui.Dialog({
				title: __("Full Resolution Photo"),
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "img_html",
						options: `
							<div class="text-center p-2 bg-dark rounded">
								<img src="${fullImgUrl}" style="max-width: 100%; max-height: 75vh; border-radius: 8px; object-fit: contain;" />
							</div>
						`,
					},
				],
			});
			imgDialog.show();
		});

		// Executive Talent Modal
		$(".xav-quick-view-btn").on("click", function () {
			const empId = $(this).data("id");
			const emp = allEmployees.find((e) => e.name === empId);
			if (emp) showEmployeeModal(emp);
		});
	}

	function showEmployeeModal(emp) {
		const initials = (emp.employee_name || "TM")
			.split(" ")
			.map((n) => n[0])
			.slice(0, 2)
			.join("")
			.toUpperCase();

		const modalAvatar = emp.image
			? `<img src="${emp.image}" class="rounded-circle shadow" style="width: 80px; height: 80px; object-fit: cover; object-position: center top; border: 3px solid #fff;" />`
			: `<div class="rounded-circle d-flex align-items-center justify-content-center fw-bold shadow" 
					style="width: 80px; height: 80px; background: linear-gradient(135deg, #1e1b4b 0%, #4338ca 100%); color: #fff; font-size: 24px; border: 3px solid #fff;">
					${initials}
			   </div>`;

		const d = new frappe.ui.Dialog({
			title: `Employee Profile — ${emp.name}`,
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "profile_html",
					options: `
						<div class="p-1">
							<!-- Profile Header Banner -->
							<div class="d-flex align-items-center gap-3 p-3 rounded" style="background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%); border: 1px solid #e0e7ff;">
								${modalAvatar}
								<div class="flex-grow-1 overflow-hidden">
									<h5 class="mb-0 fw-bold text-dark">${emp.employee_name}</h5>
									<p class="text-muted mb-1 small">${emp.designation || 'Team Member'} &bull; <strong class="text-primary">${emp.department || 'General Tech'}</strong></p>
									<span class="badge bg-light text-secondary border font-monospace">${emp.name}</span>
									<span class="badge bg-primary ms-1">${emp.custom_badge_level || 'Bronze Tier'} (${emp.custom_xp_points || 0} XP)</span>
								</div>
							</div>

							<!-- Detailed Profile Info -->
							<div class="row g-2 mt-3" style="font-size: 13px;">
								<div class="col-sm-6">
									<div class="p-2 border rounded bg-white">
										<span class="text-muted d-block small">Reports To:</span>
										<strong class="text-dark">${emp.manager_name}</strong>
									</div>
								</div>
								<div class="col-sm-6">
									<div class="p-2 border rounded bg-white">
										<span class="text-muted d-block small">Squad Team Lead:</span>
										<strong class="text-dark">${emp.custom_team_lead || 'Direct Hierarchy'}</strong>
									</div>
								</div>
								<div class="col-sm-6">
									<div class="p-2 border rounded bg-white">
										<span class="text-muted d-block small">Primary Skill Track:</span>
										<strong class="text-dark">${emp.custom_skill_area || emp.designation || 'General'}</strong>
									</div>
								</div>
								<div class="col-sm-6">
									<div class="p-2 border rounded bg-white">
										<span class="text-muted d-block small">Active Days Completed:</span>
										<strong class="text-dark">${emp.custom_active_days_completed || 0} / 90 Days</strong>
									</div>
								</div>
								<div class="col-12">
									<div class="p-2 border rounded bg-white">
										<span class="text-muted d-block small">Official Work Email:</span>
										<code class="text-primary">${emp.display_email || 'Not configured'}</code>
									</div>
								</div>
								<div class="col-sm-6">
									<div class="p-2 border rounded bg-white">
										<span class="text-muted d-block small">Phone / Contact:</span>
										<span class="text-dark">${emp.cell_number || 'Confidential'}</span>
									</div>
								</div>
								<div class="col-sm-6">
									<div class="p-2 border rounded bg-white">
										<span class="text-muted d-block small">GitHub Username:</span>
										<span class="text-dark">${emp.clean_github ? `@${emp.clean_github}` : 'Not Linked'}</span>
									</div>
								</div>
							</div>
						</div>
					`,
				},
			],
			primary_action_label: __("Open Full Employee Record"),
			primary_action() {
				frappe.set_route("Form", "Employee", emp.name);
				d.hide();
			},
		});
		d.show();
	}

	function loadDirectory() {
		frappe.call({
			method: "xavirgin_os.xavirgin_os.page.xavirgin_org_chart.xavirgin_org_chart.get_team_directory_nodes",
			callback(r) {
				if (r.message) {
					allEmployees = r.message.employees || [];
					const departments = r.message.departments || [];

					const $select = $("#xav-dept-filter");
					$select.find("option:not(:first)").remove();
					departments.forEach((d) => {
						$select.append(`<option value="${d}">${d}</option>`);
					});

					applyFilters();
				}
			},
		});
	}

	function applyFilters() {
		const selectedDept = $("#xav-dept-filter").val();
		const query = ($("#xav-search-input").val() || "").toLowerCase().trim();

		const filtered = allEmployees.filter((emp) => {
			const matchesDept = !selectedDept || emp.department === selectedDept;
			const matchesSearch =
				!query ||
				(emp.employee_name && emp.employee_name.toLowerCase().includes(query)) ||
				(emp.name && emp.name.toLowerCase().includes(query)) ||
				(emp.designation && emp.designation.toLowerCase().includes(query)) ||
				(emp.custom_skill_area && emp.custom_skill_area.toLowerCase().includes(query)) ||
				(emp.clean_github && emp.clean_github.toLowerCase().includes(query));

			return matchesDept && matchesSearch;
		});

		renderCards(filtered);
	}

	$("#xav-dept-filter").on("change", applyFilters);
	$("#xav-search-input").on("keyup", applyFilters);
	$("#xav-refresh-btn").on("click", loadDirectory);

	loadDirectory();
};