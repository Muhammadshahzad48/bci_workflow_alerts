(function () {
	"use strict";

	if (window.__bci_workflow_alerts_loaded) return;
	window.__bci_workflow_alerts_loaded = true;

	const notificationMethod =
		"frappe.desk.doctype.notification_log.notification_log.get_notification_logs";
	const pendingMarker = "bci_workflow_alert:pending";
	const alertMarker = "bci_workflow_alert:alert";
	const reminderEveryMs = 10 * 1000;
	const handled = new Set();
	const user = frappe.session?.user || "default";
	const handledStorageKey = `bci_workflow_alerts_handled:${user}`;
	const activeDisplayKey = `bci_workflow_alerts_active_display:${user}`;
	const tabId = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
	const alertRouteMap = {
		"Customer RFQ": { module: "selling", route: "customer-rfq" },
		"Material Request": { module: "stock", route: "material-request" },
		"Purchase Order": { module: "buying", route: "purchase-order" },
		"Purchase Receipt": { module: "stock", route: "purchase-receipt" },
		"Sales Order": { module: "selling", route: "sales-order" },
		"Material Transfer Request": { module: "stock", route: "material-transfer-request" },
		Supplier: { module: "buying", route: "supplier" },
		"Delivery Note": { module: "stock", route: "delivery-note" },
		"Purchase Request": { module: "buying", route: "purchase-request" },
		"Expense Sheet": { module: "accounts", route: "expense-sheet" },
		"Transportation Cost Exception": {
			module: "transport",
			route: "transportation-cost-exception",
		},
		"Customer Aging Limit Pass": { module: "selling", route: "customer-aging-limit-pass" },
		"Material Complain": { module: "quality", route: "material-complain" },
		"Customer Price Exception": { module: "selling", route: "customer-price-exception" },
		"Customer Credit Limit Bypass": {
			module: "selling",
			route: "customer-credit-limit-bypass",
		},
		"Technical Visit Request": { module: "apc", route: "technical-visit-request" },
		"Submittal Request": { module: "selling", route: "submittal-request" },
		"Technical Support": { module: "apc", route: "technical-support" },
		"Sample Request": { module: "apc", route: "sample-request" },
		"Request For Job Applicant": { module: "transport", route: "request-for-job-applicant" },
		"Job Applicant": { module: "hr", route: "job-applicant" },
		"Leave Application": { module: "hr", route: "leave-application" },
		"Request For Advance": { module: "hr", route: "request-for-advance" },
		"Vacation Salary Request": { module: "hr", route: "vacation-salary-request" },
		"Employee Incentive": { module: "payroll", route: "employee-incentive" },
		"Full and Final Statement": { module: "hr", route: "full-and-final-statement" },
		"Employee Custody": { module: "hr", route: "employee-custody" },
		"Staff Notes": { module: "apc", route: "staff-notes" },
		"Instruction From Sales Management To Staff": {
			module: "apc",
			route: "instruction-from-sales-management-to-staff",
		},
	};
	let pendingLogs = [];
	let operationalLogs = [];
	let audioContext = null;
	let renderedMenu = null;
	let renderedSignature = "";
	let uiRefreshTimer = null;
	const soundTestRequested =
		new URLSearchParams(window.location.search).get("bci_sound_test") === "1";

	function is_customer_rfq(log) {
		return (
			log &&
			(log.document_type === "Customer RFQ" || /customer rfq/i.test(log.subject || ""))
		);
	}

	function is_pending_alert(log) {
		if (!is_customer_rfq(log)) return false;
		const content = String(log.email_content || "");
		return (
			content.includes(pendingMarker) ||
			(/customer rfq awaiting action:/i.test(log.subject || "") && !Number(log.read))
		);
	}

	function is_operational_alert(log) {
		return String(log?.email_content || "").includes(alertMarker);
	}

	function log_created_at(log) {
		const createdAt = Date.parse(log?.creation || "");
		return Number.isFinite(createdAt) ? createdAt : 0;
	}

	function get_audio_context() {
		const Context = window.AudioContext || window.webkitAudioContext;
		if (!Context) return null;
		if (!audioContext) audioContext = new Context();
		return audioContext;
	}

	function unlock_audio() {
		const context = get_audio_context();
		if (!context || context.state === "running") return;
		context.resume().catch(() => {});
	}

	document.addEventListener("pointerdown", unlock_audio, true);
	document.addEventListener("keydown", unlock_audio, true);

	function play_alarm() {
		const context = get_audio_context();
		if (context && context.state === "running") {
			const start = context.currentTime;
			// A distinct five-second messaging-style chime. Browser and device
			// settings remain the final authority for output volume and silence.
			Array.from({ length: 12 }, (_, index) => index * 0.4).forEach((offset, index) => {
				const oscillator = context.createOscillator();
				const gain = context.createGain();
				const at = start + offset;
				oscillator.type = "sine";
				oscillator.frequency.setValueAtTime(index % 3 === 2 ? 1318 : 1046, at);
				gain.gain.setValueAtTime(0.001, at);
				gain.gain.exponentialRampToValueAtTime(0.72, at + 0.025);
				gain.gain.exponentialRampToValueAtTime(0.001, at + 0.27);
				oscillator.connect(gain).connect(context.destination);
				oscillator.start(at);
				oscillator.stop(at + 0.3);
			});
			return;
		}

		try {
			const audio = new Audio("/assets/frappe/sounds/alert.mp3");
			audio.volume = 1;
			audio.play().catch(() => {});
		} catch (error) {
			// Visual reminders continue when audio is unavailable.
		}
	}

	function fetch_logs() {
		return frappe
			.call({ method: notificationMethod, args: { limit: 500 } })
			.then((response) => response.message?.notification_logs || [])
			.catch(() => []);
	}

	function refresh_handled() {
		try {
			JSON.parse(localStorage.getItem(handledStorageKey) || "[]").forEach((name) =>
				handled.add(name)
			);
		} catch (error) {
			// Alerts still work in the current tab if storage is unavailable.
		}
	}

	function claim_alert(name) {
		if (!name) return false;
		refresh_handled();
		if (handled.has(name)) return false;
		handled.add(name);
		try {
			localStorage.setItem(handledStorageKey, JSON.stringify([...handled].slice(-300)));
		} catch (error) {
			// Retain the in-memory claim.
		}
		return true;
	}

	function is_active_display() {
		return !document.hidden && (typeof document.hasFocus !== "function" || document.hasFocus());
	}

	function claim_active_display() {
		if (!is_active_display()) return false;
		const now = Date.now();
		try {
			const current = JSON.parse(localStorage.getItem(activeDisplayKey) || "null");
			if (current?.expiresAt > now && current.tabId !== tabId) return false;
			localStorage.setItem(activeDisplayKey, JSON.stringify({ tabId, expiresAt: now + 15000 }));
			return JSON.parse(localStorage.getItem(activeDisplayKey) || "null")?.tabId === tabId;
		} catch (error) {
			return true;
		}
	}

	function as_plain_text(value) {
		const node = document.createElement("div");
		node.innerHTML = value == null ? "" : String(value);
		return node.textContent || node.innerText || "";
	}

	function create_container() {
		const container = document.createElement("div");
		container.id = "bci-workflow-alert-container";
		document.body.appendChild(container);
		return container;
	}

	function update_clear_popups_control(container) {
		const cards = container.querySelectorAll("[data-bci-alert-log]");
		let clear = container.querySelector(".bci-workflow-clear-popups");
		if (!cards.length) {
			clear?.remove();
			return;
		}
		if (clear) return;
		clear = document.createElement("button");
		clear.type = "button";
		clear.className = "bci-workflow-clear-popups btn btn-sm btn-secondary";
		clear.textContent = "Clear";
		clear.addEventListener("click", () => {
			const cards = [...container.querySelectorAll("[data-bci-alert-log]")];
			cards.forEach((card, index) => {
				window.setTimeout(() => {
					card.classList.add("bci-workflow-alert-slide-out");
					window.setTimeout(() => {
						card.remove();
						update_clear_popups_control(container);
					}, 220);
				}, index * 55);
			});
		});
		container.append(clear);
	}

	function open_pending_action(log) {
		if (log.document_type && log.document_name) {
			document
				.querySelectorAll(`[data-bci-alert-log="${CSS.escape(String(log.name || ""))}"]`)
				.forEach((card) => card.remove());
			frappe.set_route("Form", log.document_type, log.document_name);
		}
	}

	function current_form_identity() {
		const route = frappe.get_route?.() || [];
		if (String(route[0] || "").toLowerCase() === "form" && route[1] && route[2]) {
			return { doctype: route[1], name: route[2] };
		}
		return null;
	}

	function is_current_form_alert(log) {
		const current = current_form_identity();
		return Boolean(
			current &&
			log.document_type === current.doctype &&
			String(log.document_name) === String(current.name)
		);
	}

	function active_bci_alerts() {
		const unique = new Map();
		[...pendingLogs, ...operationalLogs].forEach((log) => unique.set(log.name, log));
		return [...unique.values()];
	}

	function show_alert(log, reminder = false) {
		const container = document.getElementById("bci-workflow-alert-container") || create_container();
		const existingCard = container.querySelector(
			`[data-bci-alert-log="${CSS.escape(String(log.name || ""))}"]`
		);
		if (existingCard) {
			existingCard.classList.remove("bci-workflow-alert-refresh");
			void existingCard.offsetWidth;
			existingCard.classList.add("bci-workflow-alert-refresh");
			play_alarm();
			return;
		}
		const card = document.createElement("div");
		card.className = "bci-workflow-alert-card";
		card.dataset.bciAlertLog = String(log.name || "");
		card.setAttribute("role", "alertdialog");
		card.setAttribute("aria-live", "assertive");

		const title = document.createElement("div");
		title.className = "bci-workflow-alert-title";
		title.textContent = reminder
			? is_customer_rfq(log)
				? "Customer RFQ — reminder: action required"
				: "BCI ERP — reminder: action required"
			: is_customer_rfq(log)
				? "Customer RFQ — action required"
				: "BCI ERP — notification";

		const subject = document.createElement("div");
		subject.className = "bci-workflow-alert-subject";
		subject.textContent = log.subject || "Customer RFQ pending action";

		const message = document.createElement("div");
		message.className = "bci-workflow-alert-message";
		message.textContent =
			as_plain_text(log.email_content) || "A Customer RFQ requires your attention.";

		const actions = document.createElement("div");
		actions.className = "bci-workflow-alert-actions";
		const dismiss = document.createElement("button");
		dismiss.type = "button";
		dismiss.className = "btn btn-sm btn-secondary";
		dismiss.textContent = "Dismiss";
		dismiss.addEventListener("click", () => {
			card.classList.add("bci-workflow-alert-slide-out");
			window.setTimeout(() => {
				card.remove();
				update_clear_popups_control(container);
			}, 220);
		});
		actions.append(dismiss);

		if (log.document_type && log.document_name) {
			const open = document.createElement("button");
			open.type = "button";
			open.className = "btn btn-sm btn-default";
			open.textContent = "Open pending action";
			open.addEventListener("click", () => open_pending_action(log));
			actions.append(open);
		}

		card.append(title, subject, message, actions);
		container.insertBefore(card, container.querySelector(".bci-workflow-clear-popups"));
		update_clear_popups_control(container);
		play_alarm();
	}

	function sorted_alerts(alerts) {
		return [...alerts].sort((left, right) => {
			const doctype = String(left.document_type || "").localeCompare(
				String(right.document_type || "")
			);
			return doctype || log_created_at(left) - log_created_at(right) || String(left.name).localeCompare(String(right.name));
		});
	}

	function render_pending_bell_list() {
		const menu = document.querySelector(".dropdown-notifications .notifications-list");
		if (!menu) return;
		const alerts = sorted_alerts(active_bci_alerts());
		const signature = alerts.map((log) => log.name).sort().join("|");
		if (menu === renderedMenu && signature === renderedSignature) return;
		renderedMenu = menu;
		renderedSignature = signature;
		const wasBciActive = Boolean(menu.querySelector("#bci-workflow-alert-tab.active"));
		menu.querySelector(".panel-bci-workflow-alerts")?.remove();
		menu.closest(".dropdown-notifications")?.querySelector("#bci-workflow-alert-tab")?.remove();
		if (!alerts.length) {
			const nativeTab = menu.querySelector(".notifications-category#notifications");
			const nativePanel = menu.querySelector(".panel-notifications");
			nativeTab?.classList.add("active");
			if (nativePanel) nativePanel.style.display = "block";
			return;
		}

		const panel = document.createElement("div");
		panel.className = "panel-bci-workflow-alerts";
		const section = document.createElement("div");
		section.id = "bci-workflow-pending-list";
		const heading = document.createElement("div");
		heading.className = "bci-workflow-pending-heading";
		heading.textContent = `BCI alerts requiring action (${alerts.length})`;
		section.append(heading);
		const byDoctype = new Map();
		alerts.forEach((log) => {
			const doctype = log.document_type || "Other";
			if (!byDoctype.has(doctype)) byDoctype.set(doctype, []);
			byDoctype.get(doctype).push(log);
		});
		byDoctype.forEach((doctypeAlerts, doctype) => {
			const group = document.createElement("div");
			group.className = "bci-workflow-pending-doctype";
			const groupHeading = document.createElement("div");
			groupHeading.className = "bci-workflow-pending-doctype-heading";
			groupHeading.textContent = `${doctype} (${doctypeAlerts.length})`;
			group.append(groupHeading);
			doctypeAlerts.forEach((log) => {
				const item = document.createElement("button");
				item.type = "button";
				item.className = "bci-workflow-pending-item";
				item.textContent = log.subject || log.document_name || "Action required";
				item.addEventListener("click", () => open_pending_action(log));
				group.append(item);
			});
			section.append(group);
		});
		panel.append(section);
		const body = menu.querySelector(".notification-list-body") || menu;
		body.prepend(panel);
		add_bci_alert_tab(menu, panel, alerts.length);
		if (!menu.__bciWorkflowMenuInitialized || wasBciActive) {
			menu.__bciWorkflowMenuInitialized = true;
			window.setTimeout(() => activate_bci_alert_tab(menu, panel), 0);
		}
	}

	function activate_bci_alert_tab(menu, panel, flash = false) {
		const tab = menu.querySelector("#bci-workflow-alert-tab");
		if (!tab || !panel) return;
		const body = panel.parentElement;
		menu.querySelectorAll(".notifications-category").forEach((item) => {
			item.classList.toggle("active", item === tab);
		});
		body
			.querySelectorAll(
				".panel-notifications, .panel-events, .panel-changelog-feed, .panel-bci-workflow-alerts"
			)
			.forEach((item) => (item.style.display = item === panel ? "block" : "none"));
		if (flash) {
			panel.classList.remove("bci-workflow-alert-tab-flash");
			void panel.offsetWidth;
			panel.classList.add("bci-workflow-alert-tab-flash");
		}
	}

	function add_bci_alert_tab(menu, panel, count) {
		const tab = document.createElement("li");
		tab.id = "bci-workflow-alert-tab";
		tab.className = "notifications-category bci-workflow-alert-tab";
		tab.textContent = `BCI Alerts (${count})`;
		const showBciAlerts = (event) => {
			event.preventDefault();
			event.stopImmediatePropagation();
			activate_bci_alert_tab(menu, panel, true);
			// Frappe registers tab behavior separately. Re-apply after that handler
			// has run so the BCI tab can never include the native Notifications panel.
			window.setTimeout(() => {
				activate_bci_alert_tab(menu, panel);
			}, 0);
		};
		tab.addEventListener("click", showBciAlerts, true);
		const nativeTabs = menu.querySelector(".notification-item-tabs");
		if (nativeTabs) {
			nativeTabs.prepend(tab);
			nativeTabs.querySelectorAll(".notifications-category:not(#bci-workflow-alert-tab)").forEach(
				(item) => item.addEventListener("click", () => (panel.style.display = "none"))
			);
		} else {
			menu.prepend(tab);
		}
		const dropdown = menu.closest(".dropdown-notifications");
		if (dropdown && !dropdown.__bciWorkflowDefaultTabBound) {
			dropdown.__bciWorkflowDefaultTabBound = true;
			dropdown.addEventListener(
				"click",
				(event) => {
					if (event.target.closest(".notification-list-body, .notification-item-tabs")) return;
					window.setTimeout(() => {
						const currentPanel = menu.querySelector(".panel-bci-workflow-alerts");
						if (currentPanel && active_bci_alerts().length) {
							activate_bci_alert_tab(menu, currentPanel);
						}
					}, 0);
				},
				true
			);
		}
	}

	function set_pending_link_indicator(element, count) {
		const isBreadcrumb = Boolean(
			element.closest(
				".breadcrumbs, .breadcrumb, .breadcrumb-container, #navbar-breadcrumbs"
			)
		);
		const href = element.getAttribute("href") || "";
		const route = href.split("/").filter(Boolean).pop() || element.dataset.route;
		const moduleRoutes = new Set(Object.values(alertRouteMap).map((item) => item.module));
		// In breadcrumbs, hide the workspace/module total but retain the specific
		// doctype badge. Breadcrumbs never receive the workspace highlight.
		if (isBreadcrumb && moduleRoutes.has(route)) {
			const previousBadge = element.__bciWorkflowPendingBadge;
			previousBadge?.remove();
			element.__bciWorkflowPendingBadge = null;
			element.classList.remove("bci-workflow-pending-link");
			return;
		}
		let badge = element.__bciWorkflowPendingBadge;
		if (!count) {
			badge?.remove();
			element.__bciWorkflowPendingBadge = null;
			element.classList.remove("bci-workflow-pending-link");
			return;
		}

		if (!badge || !badge.isConnected) {
			badge = document.createElement("span");
			badge.className = "bci-workflow-inline-badge";
			badge.setAttribute("aria-label", `${count} pending actions`);
			// Keep the badge in the doctype link itself. Workspace rows place
			// siblings on a new line, which is why the old badge appeared below.
			element.append(badge);
			element.__bciWorkflowPendingBadge = badge;
		}
		badge.textContent = count;
		// Highlight only workspace doctype links, never breadcrumbs.
		element.classList.toggle("bci-workflow-pending-link", !isBreadcrumb);
	}

	function set_module_indicator(element, count) {
		if (element.closest(".breadcrumbs, .breadcrumb, .breadcrumb-container, #navbar-breadcrumbs")) {
			element.__bciWorkflowModuleBadge?.remove();
			element.__bciWorkflowModuleBadge = null;
			return;
		}
		let badge = element.__bciWorkflowModuleBadge;
		if (!count) {
			badge?.remove();
			element.__bciWorkflowModuleBadge = null;
			return;
		}
		if (!badge || !badge.isConnected) {
			badge = document.createElement("span");
			badge.className = "bci-workflow-module-badge";
			badge.setAttribute("aria-label", `${count} pending actions`);
			element.append(badge);
			element.__bciWorkflowModuleBadge = badge;
		}
		badge.textContent = count;
	}

	function selector_for_route(route) {
		return `a[href="/app/${route}"], a[href$="/app/${route}"], [data-route="${route}"]`;
	}

	function set_record_indicator(row, count) {
		let badge = row.__bciWorkflowRecordBadge;
		if (!count) {
			badge?.remove();
			row.__bciWorkflowRecordBadge = null;
			return;
		}
		if (!badge || !badge.isConnected) {
			badge = document.createElement("span");
			badge.className = "bci-workflow-record-badge";
			badge.setAttribute("aria-label", `${count} pending action${count === 1 ? "" : "s"}`);
			const checkbox = row.querySelector('input[type="checkbox"]');
			if (checkbox) {
				checkbox.insertAdjacentElement("afterend", badge);
			} else {
				row.prepend(badge);
			}
			row.__bciWorkflowRecordBadge = badge;
		}
		badge.textContent = count;
	}

	function record_serials_by_doctype() {
		const serials = new Map();
		const counters = new Map();
		// A document gets one serial number within its doctype. If it has more
		// than one alert log, every log maps to that same serial.
		sorted_alerts(active_bci_alerts()).forEach((log) => {
			if (!log.document_type || !log.document_name) return;
			const key = `${log.document_type}:${log.document_name}`;
			if (serials.has(key)) return;
			const serial = (counters.get(log.document_type) || 0) + 1;
			counters.set(log.document_type, serial);
			serials.set(key, serial);
		});
		return serials;
	}

	function apply_record_indicators() {
		const recordSerials = record_serials_by_doctype();

		Object.entries(alertRouteMap).forEach(([doctype, mapping]) => {
			const pathPrefix = `/app/${mapping.route}`;
			if (!window.location.pathname.startsWith(pathPrefix)) return;
			const handledRows = new Set();
			document
				.querySelectorAll(`a[href^="/app/${mapping.route}/"]`)
				.forEach((element) => {
					const href = element.getAttribute("href") || "";
					const name = decodeURIComponent(href.split("/").pop() || "").split("?")[0];
					const row = element.closest(".list-row");
					if (!row) return;
					handledRows.add(row);
					set_record_indicator(row, recordSerials.get(`${doctype}:${name}`) || 0);
				});
			// Some list layouts put the document name in a non-link column. Their
			// row still exposes data-name, so badge the checkbox column from that.
			document.querySelectorAll(".list-row[data-name]").forEach((row) => {
				if (handledRows.has(row)) return;
				set_record_indicator(row, recordSerials.get(`${doctype}:${row.dataset.name}`) || 0);
			});
		});
	}

	function alert_counts_by_route() {
		const counts = new Map();
		const activeAlerts = active_bci_alerts();
		activeAlerts.forEach((log) => {
			const mapping = alertRouteMap[log.document_type];
			if (!mapping) return;
			counts.set(mapping.route, (counts.get(mapping.route) || 0) + 1);
		});
		return counts;
	}

	function apply_pending_indicators() {
		const activeAlertCount = pendingLogs.length + operationalLogs.length;
		const hasPending = activeAlertCount > 0;
		const pendingCount = String(activeAlertCount);
		const counts = alert_counts_by_route();
		// Remove legacy breadcrumb highlighting. The current doctype's badge is
		// intentionally retained; only workspace/module breadcrumbs hide badges.
		document
			.querySelectorAll(".bci-workflow-pending-link")
			.forEach((element) => element.classList.remove("bci-workflow-pending-link"));
		document.body.classList.toggle("bci-workflow-has-pending", hasPending);
		document.querySelectorAll(".dropdown-notifications").forEach((element) => {
			element.classList.toggle("bci-workflow-has-pending", hasPending);
			element.setAttribute("data-bci-pending-count", pendingCount);
			element
				.querySelectorAll(".notifications-icon")
				.forEach((icon) => icon.setAttribute("data-bci-pending-count", pendingCount));
		});
		const mappings = Object.values(alertRouteMap);
		const routes = new Set(mappings.map((item) => item.route));
		routes.forEach((route) => {
			const count = counts.get(route) || 0;
			document
				.querySelectorAll(selector_for_route(route))
				.forEach((element) => set_pending_link_indicator(element, count ? String(count) : ""));
		});
		// The left navigation receives only a total badge. It is deliberately not
		// highlighted, while each inside doctype keeps its own individual count.
		const modules = new Set(mappings.map((item) => item.module));
		modules.forEach((module) => {
			const count = mappings
				.filter((item) => item.module === module)
				.reduce((total, item) => total + (counts.get(item.route) || 0), 0);
			document
				.querySelectorAll(selector_for_route(module))
				.forEach((element) => set_module_indicator(element, count ? String(count) : ""));
		});
		apply_record_indicators();
		render_pending_bell_list();
		focus_requested_pending_doctype(counts);
	}

	function request_module_focus(event) {
		const link = event.target.closest("a[href^=\"/app/\"]");
		if (!link) return;
		const route = (link.getAttribute("href") || "").split("/").filter(Boolean).pop();
		if (!route || !Object.values(alertRouteMap).some((item) => item.module === route)) return;
		try {
			sessionStorage.setItem("bci_workflow_alerts_focus_module", route);
		} catch (error) {
			window.__bciWorkflowFocusModule = route;
		}
	}

	function focus_requested_pending_doctype(counts) {
		let module;
		try {
			module = sessionStorage.getItem("bci_workflow_alerts_focus_module");
		} catch (error) {
			module = window.__bciWorkflowFocusModule;
		}
		if (!module || !window.location.pathname.startsWith(`/app/${module}`)) return;
		const mapping = Object.values(alertRouteMap).find(
			(item) => item.module === module && counts.get(item.route)
		);
		if (!mapping) return;
		const target = [...document.querySelectorAll(selector_for_route(mapping.route))].find(
			(element) => !element.closest(".desk-sidebar, .layout-side-section, .standard-sidebar")
		);
		if (!target) return;
		try {
			sessionStorage.removeItem("bci_workflow_alerts_focus_module");
		} catch (error) {
			window.__bciWorkflowFocusModule = null;
		}
		window.setTimeout(() => {
			target.scrollIntoView({ behavior: "smooth", block: "center" });
			target.classList.remove("bci-workflow-focus-target");
			void target.offsetWidth;
			target.classList.add("bci-workflow-focus-target");
			const pointer = document.createElement("span");
			pointer.className = "bci-workflow-focus-pointer";
			pointer.setAttribute("aria-hidden", "true");
			pointer.textContent = "🖱";
			target.append(pointer);
			window.setTimeout(() => {
				target.classList.remove("bci-workflow-focus-target");
				pointer.remove();
			}, 3600);
		}, 180);
	}

	function sync_pending_state(logs) {
		const unique = new Map();
		logs.filter(is_pending_alert).forEach((log) => unique.set(log.name, log));
		pendingLogs = [...unique.values()];
		operationalLogs = logs.filter(
			(log) => is_operational_alert(log) && !Number(log.read)
		);
		const activeNames = new Set(active_bci_alerts().map((log) => String(log.name || "")));
		document.querySelectorAll("[data-bci-alert-log]").forEach((card) => {
			const log = active_bci_alerts().find(
				(item) => String(item.name || "") === card.dataset.bciAlertLog
			);
			if (!activeNames.has(card.dataset.bciAlertLog) || is_current_form_alert(log)) card.remove();
		});
		const container = document.getElementById("bci-workflow-alert-container");
		if (container) update_clear_popups_control(container);
		apply_pending_indicators();
		return active_bci_alerts();
	}

	function check_for_new_notifications() {
		fetch_logs().then((logs) => {
			sync_pending_state(logs);
		});
	}

	function prime_notifications() {
		fetch_logs().then((logs) => {
			refresh_handled();
			sync_pending_state(logs);
		});
	}

	function remind_about_pending_action() {
		fetch_logs().then((logs) => {
			sync_pending_state(logs);
			if (!claim_active_display()) return;
			const reminders = active_bci_alerts().filter((log) => !is_current_form_alert(log));
			// Dismiss or Clear affects only this cycle's cards. The active visible
			// tab receives every unresolved reminder again on the next ten-second cycle.
			reminders.forEach((log) => show_alert(log, true));
		});
	}

	function run_sound_test() {
		show_alert({
			subject: "Sound test",
			email_content:
				"This is a test of the Customer RFQ visual and sound alert. No ERP record was created or changed.",
		});
	}

	if (frappe.realtime && frappe.realtime.on) {
		frappe.realtime.on("notification", check_for_new_notifications);
		frappe.realtime.on("bci_workflow_alerts_pending_update", check_for_new_notifications);
	}
	if (frappe.router && frappe.router.on) frappe.router.on("change", check_for_new_notifications);

	window.addEventListener("focus", check_for_new_notifications);
	document.addEventListener("visibilitychange", () => {
		if (!document.hidden) check_for_new_notifications();
	});
	document.addEventListener("click", request_module_focus, true);
	window.addEventListener("storage", (event) => {
		if (event.key === handledStorageKey) refresh_handled();
	});

	new MutationObserver(() => {
		window.clearTimeout(uiRefreshTimer);
		uiRefreshTimer = window.setTimeout(apply_pending_indicators, 50);
	}).observe(document.body, { childList: true, subtree: true });

	window.setInterval(remind_about_pending_action, reminderEveryMs);
	window.bci_workflow_alerts_test = run_sound_test;

	prime_notifications();
	if (soundTestRequested) window.setTimeout(run_sound_test, 1000);
})();
