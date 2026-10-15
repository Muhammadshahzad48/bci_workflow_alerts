"""BCI workflow and operational notification helpers."""

import frappe


PENDING_MARKER = "bci_workflow_alert:pending"
ALERT_MARKER = "bci_workflow_alert:alert"

# Operational alerts are addressed directly to ERP User accounts.  They do not
# depend on membership in a notification-only role.
PROCUREMENT_USERS = (
	"sawsanalsaaidah456@gmail.com",
	"sunil@bcisaudi.com",
	"raza.zafar15@gmail.com",
)
PO_CHECK_USERS = ("muhed@arpioneer.net",)
PO_APPROVAL_USERS = ("adnan@bcisaudi.com",)
RECRUITMENT_USERS = ("ramy_tiger5000@yahoo.com", "neel@bcisaudi.com")
HR_REQUEST_USERS = ("marwannasir175@gmail.com", "asmafawzi455@gmail.com")
SALES_ORDER_USERS = (
	"nazish@bcisaudi.com",
	"smartjms786@gmail.com",
	"mahmoudelyazeed2023@gmail.com",
	"furqankhanzaida091@gmail.com",
)
SALES_ORDER_RIYADH_USERS = SALES_ORDER_USERS[:3] + ("rshdynsar385@gmail.com",)
SALES_ORDER_JEDDAH_USERS = SALES_ORDER_USERS[:3] + ("aadeel60@gmail.com",)
SALES_ORDER_JIZAN_USERS = SALES_ORDER_USERS[:3] + ("naveedshahbaz134@gmail.com",)
MATERIAL_TRANSFER_USERS = SALES_ORDER_USERS[:3]
SUPPLIER_REVIEW_USERS = (
	"venkatesan801@gmail.com",
	"shoaibmsa333@gmail.com",
	*PROCUREMENT_USERS,
	"nazish@bcisaudi.com",
)
DELIVERY_NOTE_USERS = ("mahmoudelyazeed2023@gmail.com", "nazish@bcisaudi.com")
MUHED_USERS = ("muhed@arpioneer.net",)
TECHNICAL_VISIT_USERS = (
	"venkatesan801@gmail.com",
	"shoaibmsa333@gmail.com",
	"asimbilal861@gmail.com",
)
ASIM_USERS = ("asimbilal861@gmail.com",)
SAMPLE_REQUEST_USERS = (
	"smartjms786@gmail.com",
	"furqankhanzaida091@gmail.com",
	"nazish@bcisaudi.com",
)
CUSTOMER_RFQ_CREATED_USERS = ("biobojonathan@gmail.com", "kclyn.moralde21@gmail.com")
CUSTOMER_RFQ_IN_PROGRESS_USERS = ("kclyn.moralde21@gmail.com",)

def notify_pending_workflow_roles(doc, method=None):
	"""Notify only the users or roles configured on the current transition."""
	users = _transition_alert_users(doc)
	if not users:
		return

	state = doc.get("workflow_state") or "Created"
	payload = {
		"type": "Alert",
		"document_type": doc.doctype,
		"document_name": doc.name,
		"subject": f"Customer RFQ awaiting action: {doc.name}",
		"from_user": doc.modified_by or doc.owner,
		"email_content": (
			f"Customer RFQ {doc.name} is pending in {state}. "
			f"Please take the next workflow action.<!-- {PENDING_MARKER} -->"
		),
	}
	# Insert synchronously so a rapid transition cannot leave an old queued
	# notification behind after its workflow action has already been completed.
	for user in users:
		_create_notification(user, payload)


def notify_when_workflow_state_changes(doc, method=None):
	"""Only notify on an actual workflow-state transition, not ordinary saves."""
	if doc.has_value_changed("workflow_state"):
		resolve_completed_workflow_notifications(doc)
		notify_pending_workflow_roles(doc, method)


def resolve_completed_workflow_notifications(doc):
	"""Resolve the prior role's alerts only after its workflow action is taken."""
	logs = frappe.get_all(
		"Notification Log",
		filters={"document_type": doc.doctype, "document_name": doc.name},
		fields=["name", "for_user", "subject", "email_content"],
	)
	updated_users = set()
	for log in logs:
		content = log.email_content or ""
		if PENDING_MARKER not in content and not (log.subject or "").startswith(
			"Customer RFQ awaiting action:"
		):
			continue
		frappe.db.set_value(
			"Notification Log",
			log.name,
			{
				"read": 1,
				"subject": f"Customer RFQ action completed: {doc.name}",
				"email_content": f"Customer RFQ {doc.name} has moved to its next workflow state.",
			},
			update_modified=False,
		)
		updated_users.add(log.for_user)

	for user in updated_users:
		frappe.publish_realtime("bci_workflow_alerts_pending_update", user=user, after_commit=True)


def reconcile_workflow_recipient_alerts(workflow, method=None):
	"""Synchronize existing workflow alerts after Alert Users/Roles are edited."""
	doctype = workflow.get("document_type")
	if not doctype:
		return
	frappe.clear_cache(doctype="Workflow")
	logs = frappe.get_all(
		"Notification Log",
		filters={"document_type": doctype, "read": 0},
		fields=["name", "document_name", "for_user", "subject", "email_content"],
	)
	by_document = {}
	for log in logs:
		if PENDING_MARKER in (log.email_content or ""):
			by_document.setdefault(log.document_name, []).append(log)

	for name, document_logs in by_document.items():
		if not frappe.db.exists(doctype, name):
			continue
		doc = frappe.get_doc(doctype, name)
		configured, recipients = _transition_alert_recipients(doc)
		# A blank Alert Users/Roles configuration is intentional: no one remains
		# assigned to the current alert state until a user or role is added again.
		recipients = set(recipients) if configured else set()
		current_users = set()
		for log in document_logs:
			if log.for_user in recipients:
				current_users.add(log.for_user)
				continue
			frappe.db.set_value("Notification Log", log.name, {"read": 1}, update_modified=False)
			frappe.publish_realtime("bci_workflow_alerts_pending_update", user=log.for_user, after_commit=True)

		state = doc.get("workflow_state") or "Created"
		for user in recipients - current_users:
			_create_notification(
				user,
				{
					"type": "Alert",
					"document_type": doc.doctype,
					"document_name": doc.name,
					"subject": f"Customer RFQ awaiting action: {doc.name}",
					"from_user": doc.modified_by or doc.owner,
					"email_content": (
						f"Customer RFQ {doc.name} is pending in {state}. "
						f"Please take the next workflow action.<!-- {PENDING_MARKER} -->"
					),
				},
			)


def reconcile_all_workflow_recipient_alerts():
	"""Apply the current Workflow Alert Users/Roles to already-open alerts."""
	for name in frappe.get_all("Workflow", filters={"is_active": 1}, pluck="name"):
		reconcile_workflow_recipient_alerts(frappe.get_doc("Workflow", name))


def resolve_supplier_enabled_alert(doc, method=None):
	"""A Supplier review is complete once the Supplier is enabled."""
	if not doc.meta.get_field("disabled") or not doc.has_value_changed("disabled"):
		return
	if not doc.get("disabled"):
		resolve_completed_operational_notifications(doc)


def _next_action_roles(doc):
	workflow_name = frappe.db.get_value(
		"Workflow", {"document_type": doc.doctype, "is_active": 1}, "name"
	)
	if not workflow_name:
		return set()

	workflow = frappe.get_cached_doc("Workflow", workflow_name)
	# `All` is Frappe's global role and would notify every system user. It is
	# intentionally excluded; alerts begin automatically when a named role is
	# assigned to the transition.
	return {
		transition.allowed
		for transition in workflow.transitions
		if transition.state == doc.get("workflow_state")
		and transition.allowed
		and transition.allowed != "All"
	}


def _active_users_with_any_role(roles):
	users = frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User"},
		pluck="name",
	)
	return [user for user in users if roles.intersection(frappe.get_roles(user))]


def _next_action_users(doc):
	"""Resolve the workflow's current action to its individual ERP users."""
	return _active_users_with_any_role(_next_action_roles(doc))


def _split_alert_values(value):
	"""Accept comma- or line-separated values entered in a workflow grid cell."""
	return {
		item.strip()
		for item in (value or "").replace("\n", ",").split(",")
		if item.strip()
	}


def _transition_alert_recipients(doc, state=None):
	"""Resolve the direct users and roles configured for a workflow state.

	The workflow's ``Allowed`` field is deliberately not used as a recipient
	list.  Alerts go only to entries explicitly maintained in Alert Users and
	Alert Roles, so the global ``All`` role can never broadcast an alert.
	"""
	workflow_name = frappe.db.get_value(
		"Workflow", {"document_type": doc.doctype, "is_active": 1}, "name"
	)
	if not workflow_name:
		return False, []

	workflow = frappe.get_cached_doc("Workflow", workflow_name)
	current_state = state or doc.get("workflow_state")
	direct_users = set()
	roles = set()
	configured = False
	for transition in workflow.transitions:
		if transition.state != current_state:
			continue
		transition_users = _split_alert_values(transition.get("bci_alert_users"))
		transition_roles = _split_alert_values(transition.get("bci_alert_roles"))
		if transition_users or transition_roles:
			configured = True
			direct_users.update(transition_users)
			roles.update(transition_roles)

	users = [user for user in direct_users if _is_enabled_system_user(user)]
	users.extend(_active_users_with_any_role(roles))
	return configured, list(dict.fromkeys(users))


def _transition_alert_users(doc, state=None):
	"""Return only the explicitly-configured users for a workflow state."""
	return _transition_alert_recipients(doc, state)[1]


def _recipients_for_workflow_or_default(doc, fallback, state=None):
	"""Use a transition configuration when present, otherwise the requested default."""
	configured, users = _transition_alert_recipients(doc, state)
	return users if configured else list(fallback)


def notify_material_request(doc, method=None):
	"""Ask procurement users to create a Purchase Order for a new request."""
	_notify_users(
		_recipients_for_workflow_or_default(doc, PROCUREMENT_USERS),
		doc,
		f"Material Request awaiting Purchase Order: {doc.name}",
		f"Material Request {doc.name} was created. Please take action and create the Purchase Order.",
	)


def notify_purchase_order_state(doc, method=None):
	"""Close the prior PO alert, then alert only the next workflow recipient."""
	if not doc.has_value_changed("workflow_state"):
		return

	# A transition is the completion of the prior user's action.  Mark every
	# prior custom alert for this PO as read before creating the next one.
	# This removes it from the former recipient's bell, badges and reminders.
	resolve_completed_operational_notifications(doc)
	state = doc.get("workflow_state")
	if state == "To be Checked":
		_notify_users(
			_recipients_for_workflow_or_default(doc, PO_CHECK_USERS, state),
			doc,
			f"Purchase Order requires checking: {doc.name}",
			f"Purchase Order {doc.name} is now To be Checked. Please complete the check action.",
		)
	elif state == "Checked":
		_notify_users(
			_recipients_for_workflow_or_default(doc, PO_APPROVAL_USERS, state),
			doc,
			f"Purchase Order requires approval: {doc.name}",
			f"Purchase Order {doc.name} has been checked. Please complete the approval action.",
		)


def resolve_completed_operational_notifications(doc):
	"""Close active custom alerts for a document after its action is completed."""
	logs = frappe.get_all(
		"Notification Log",
		filters={"document_type": doc.doctype, "document_name": doc.name, "read": 0},
		fields=["name", "for_user", "email_content"],
	)
	updated_users = set()
	for log in logs:
		if ALERT_MARKER not in (log.email_content or ""):
			continue
		frappe.db.set_value(
			"Notification Log",
			log.name,
			{"read": 1},
			update_modified=False,
		)
		updated_users.add(log.for_user)
	for user in updated_users:
		frappe.publish_realtime("bci_workflow_alerts_pending_update", user=user, after_commit=True)


def resolve_alert_after_status_change(doc, method=None):
	"""Close the acting user's direct alert after they change a document state."""
	state_fields = ("workflow_state", "status", "approval_status")
	if not any(doc.meta.get_field(field) and doc.has_value_changed(field) for field in state_fields):
		return

	user = frappe.session.user
	logs = frappe.get_all(
		"Notification Log",
		filters={
			"document_type": doc.doctype,
			"document_name": doc.name,
			"for_user": user,
			"read": 0,
		},
		fields=["name", "email_content"],
	)
	updated = False
	for log in logs:
		if ALERT_MARKER not in (log.email_content or ""):
			continue
		frappe.db.set_value("Notification Log", log.name, {"read": 1}, update_modified=False)
		updated = True
	if updated:
		frappe.publish_realtime("bci_workflow_alerts_pending_update", user=user, after_commit=True)


def reconcile_terminal_operational_alerts():
	"""Close historic custom alerts where their record is already terminal."""
	terminal_states = {"approved", "completed", "closed", "cancelled", "rejected"}
	logs = frappe.get_all(
		"Notification Log",
		filters={"read": 0},
		fields=["name", "document_type", "document_name", "for_user", "email_content"],
	)
	by_document = {}
	for log in logs:
		if ALERT_MARKER in (log.email_content or "") and log.document_type and log.document_name:
			by_document.setdefault((log.document_type, log.document_name), []).append(log)

	for (doctype, name), document_logs in by_document.items():
		try:
			meta = frappe.get_meta(doctype)
			fields = [field for field in ("status", "workflow_state", "approval_status") if meta.get_field(field)]
			values = frappe.db.get_value(doctype, name, fields, as_dict=True) if fields else None
		except Exception:
			continue
		if not values or not any(str(value or "").casefold() in terminal_states for value in values.values()):
			continue
		for log in document_logs:
			frappe.db.set_value("Notification Log", log.name, {"read": 1}, update_modified=False)
			frappe.publish_realtime("bci_workflow_alerts_pending_update", user=log.for_user)


def reconcile_open_purchase_order_alerts():
	"""Repair stale PO alerts created before transition cleanup was introduced.

	Only Purchase Orders that already have an unread BCI alert are examined. A
	completed checker alert is closed and, when needed, the current approver gets
	the correct active alert. Historical PO records without custom alerts are not
	changed or newly notified.
	"""
	logs = frappe.get_all(
		"Notification Log",
		filters={"document_type": "Purchase Order", "read": 0},
		fields=["name", "document_name", "for_user", "subject", "email_content"],
	)
	by_document = {}
	for log in logs:
		if ALERT_MARKER in (log.email_content or ""):
			by_document.setdefault(log.document_name, []).append(log)

	for name, document_logs in by_document.items():
		state = frappe.db.get_value("Purchase Order", name, "workflow_state")
		if state == "To be Checked":
			wanted_prefix = "Purchase Order requires checking:"
			wanted_users = _recipients_for_workflow_or_default(
				frappe.get_doc("Purchase Order", name), PO_CHECK_USERS, state
			)
		elif state == "Checked":
			wanted_prefix = "Purchase Order requires approval:"
			wanted_users = _recipients_for_workflow_or_default(
				frappe.get_doc("Purchase Order", name), PO_APPROVAL_USERS, state
			)
		else:
			wanted_prefix = None
			wanted_users = []

		active_users = set()
		for log in document_logs:
			if wanted_prefix and (log.subject or "").startswith(wanted_prefix):
				active_users.add(log.for_user)
				continue
			frappe.db.set_value(
				"Notification Log", log.name, {"read": 1}, update_modified=False
			)
			frappe.publish_realtime("bci_workflow_alerts_pending_update", user=log.for_user)

		if wanted_prefix and not active_users:
			doc = frappe.get_doc("Purchase Order", name)
			message = (
				f"Purchase Order {name} is now To be Checked. Please complete the check action."
				if state == "To be Checked"
				else f"Purchase Order {name} has been checked. Please complete the approval action."
			)
			_notify_users(wanted_users, doc, f"{wanted_prefix} {name}", message)


def notify_purchase_receipt(doc, method=None):
	"""Ask procurement users to issue the Purchase Invoice for a new receipt."""
	_notify_users(
		_recipients_for_workflow_or_default(doc, PROCUREMENT_USERS),
		doc,
		f"Purchase Receipt awaiting Purchase Invoice: {doc.name}",
		f"Purchase Receipt {doc.name} was created. Please issue the Purchase Invoice.",
	)


def notify_recruitment_request(doc, method=None):
	"""Notify recruitment owners about a new applicant or applicant request."""
	_notify_users(
		_recipients_for_workflow_or_default(doc, RECRUITMENT_USERS),
		doc,
		f"New {doc.doctype}: {doc.name}",
		f"A new {doc.doctype} ({doc.name}) was created. Please review and take the required action.",
	)


def notify_hr_request(doc, method=None):
	"""Notify the HR recipients about a newly-created HR request."""
	_notify_users(
		_recipients_for_workflow_or_default(doc, HR_REQUEST_USERS),
		doc,
		f"New {doc.doctype}: {doc.name}",
		f"A new {doc.doctype} ({doc.name}) was created. Please review and take the required action.",
	)


def notify_sales_order(doc, method=None):
	"""Send a Sales Order alert to the base and warehouse-specific teams."""
	users = set(SALES_ORDER_USERS)
	for warehouse in _document_warehouses(doc):
		warehouse_name = warehouse.casefold()
		if "riyadh" in warehouse_name:
			users.update(SALES_ORDER_RIYADH_USERS)
		elif "jeddah" in warehouse_name:
			users.update(SALES_ORDER_JEDDAH_USERS)
		elif "jizan" in warehouse_name:
			users.update(SALES_ORDER_JIZAN_USERS)
	_notify_users(
		_recipients_for_workflow_or_default(doc, users),
		doc,
		f"New Sales Order: {doc.name}",
		f"Sales Order {doc.name} has been issued. Please review the required warehouse action.",
	)


def notify_material_transfer_request(doc, method=None):
	"""Notify the material-transfer team when a transfer request is issued."""
	_notify_users(
		_recipients_for_workflow_or_default(doc, MATERIAL_TRANSFER_USERS),
		doc,
		f"New Material Transfer Request: {doc.name}",
		f"Material Transfer Request {doc.name} has been issued. Please review and take action.",
	)


def notify_reviewed_material_transfer_request(doc, method=None):
	"""Notify only store users associated with the request's warehouses on review."""
	if not doc.has_value_changed("status") or doc.get("status") != "Reviewed":
		return
	users = _recipients_for_workflow_or_default(
		doc, _warehouse_store_users(_document_warehouses(doc))
	)
	_notify_users(
		users,
		doc,
		f"Material Transfer Request reviewed: {doc.name}",
		f"Material Transfer Request {doc.name} is now Reviewed. Please take the warehouse action.",
	)


def notify_supplier_review(doc, method=None):
	_notify_users(
		_recipients_for_workflow_or_default(doc, SUPPLIER_REVIEW_USERS),
		doc,
		f"New Supplier for review: {doc.name}",
		f"Supplier {doc.name} has been registered. Please review it.",
	)


def notify_delivery_note(doc, method=None):
	users = set(DELIVERY_NOTE_USERS)
	users.update(_warehouse_store_users(_document_warehouses(doc)))
	users = _recipients_for_workflow_or_default(doc, users)
	_notify_users(
		users,
		doc,
		f"New Delivery Note: {doc.name}",
		f"Delivery Note {doc.name} has been created. Please review the delivery action.",
	)


def notify_procurement_request(doc, method=None):
	"""Ask procurement to create a PO from a Purchase Request or Expense Sheet."""
	_notify_users(
		_recipients_for_workflow_or_default(doc, PROCUREMENT_USERS),
		doc,
		f"{doc.doctype} awaiting Purchase Order: {doc.name}",
		f"{doc.doctype} {doc.name} was created. Please take action and create the Purchase Order.",
	)


def notify_muhed_review(doc, method=None):
	_notify_users(
		_recipients_for_workflow_or_default(doc, MUHED_USERS),
		doc,
		f"New {doc.doctype}: {doc.name}",
		f"{doc.doctype} {doc.name} was created. Please review and take the required action.",
	)


def notify_technical_visit_request(doc, method=None):
	_notify_users(
		_recipients_for_workflow_or_default(doc, TECHNICAL_VISIT_USERS),
		doc,
		f"New Technical Visit Request: {doc.name}",
		f"Technical Visit Request {doc.name} was created. Please review and take action.",
	)


def notify_asim_request(doc, method=None):
	_notify_users(
		_recipients_for_workflow_or_default(doc, ASIM_USERS),
		doc,
		f"New {doc.doctype}: {doc.name}",
		f"{doc.doctype} {doc.name} was created. Please review and take action.",
	)


def notify_sample_request(doc, method=None):
	_notify_users(
		_recipients_for_workflow_or_default(doc, SAMPLE_REQUEST_USERS),
		doc,
		f"New Sample Request: {doc.name}",
		f"Sample Request {doc.name} was created. Please review and take action.",
	)


def _document_warehouses(doc):
	"""Collect every warehouse referenced by a document or its item rows."""
	warehouses = set()
	for fieldname in (
		"warehouse",
		"set_warehouse",
		"custom_warehouse",
		"custom_from_warehouse",
		"source_warehouse",
		"target_warehouse",
		"s_warehouse",
		"t_warehouse",
	):
		if doc.get(fieldname):
			warehouses.add(doc.get(fieldname))
	for item in doc.get("items") or []:
		for fieldname in ("warehouse", "source_warehouse", "target_warehouse", "s_warehouse", "t_warehouse"):
			if item.get(fieldname):
				warehouses.add(item.get(fieldname))
	return warehouses


def _warehouse_store_users(warehouses):
	"""Find enabled ERP users explicitly assigned to any affected warehouse."""
	warehouses = list(warehouses)
	if not warehouses:
		return []
	users = frappe.get_all(
		"User Permission",
		filters={"allow": "Warehouse", "for_value": ("in", warehouses)},
		pluck="user",
	)
	return [user for user in dict.fromkeys(users) if _is_enabled_system_user(user)]


def notify_selected_employee(doc, method=None):
	"""Notify the system user linked to the employee selected on a staff record."""
	employee = doc.get("employee") or doc.get("employee_name")
	user = _system_user_for_employee(employee)
	if not user:
		# Some legacy Employee records have no ERP account; do not send a private
		# staff item to an unrelated user in that case.
		frappe.log_error(
			title="BCI workflow alert recipient missing",
			message=f"{doc.doctype} {doc.name}: selected employee {employee or '(empty)'} has no enabled System User.",
		)
		return
	_notify_users(
		(user,),
		doc,
		f"New {doc.doctype}: {doc.name}",
		f"You have a new {doc.doctype} ({doc.name}). Please review and take the required action.",
	)


def _system_user_for_employee(employee):
	if not employee:
		return None

	user = frappe.db.get_value("Employee", employee, "user_id")
	if _is_enabled_system_user(user):
		return user

	for field in ("company_email", "personal_email"):
		candidate = frappe.db.get_value("Employee", employee, field)
		if _is_enabled_system_user(candidate):
			return candidate
	return None


def provision_workflow_recipient_fields():
	"""Show recipient users and roles as adjacent Workflow Transition columns."""
	_provision_workflow_transition_text_field(
		"bci_alert_users",
		"Alert Users",
		"allowed",
		"ERP user emails, separated by commas. Only these users receive this state's alert.",
	)
	_provision_workflow_transition_text_field(
		"bci_alert_roles",
		"Alert Roles",
		"bci_alert_users",
		"Role names, separated by commas. Active users in these roles also receive this state's alert.",
	)
	frappe.clear_cache(doctype="Workflow Transition")


def _provision_workflow_transition_text_field(fieldname, label, insert_after, description):
	custom_field_name = f"Workflow Transition-{fieldname}"
	field = frappe.db.exists("Custom Field", custom_field_name)
	values = {
		"label": label,
		"fieldtype": "Small Text",
		"options": None,
		"insert_after": insert_after,
		"in_list_view": 1,
		"description": description,
	}
	if field and frappe.db.get_value("Custom Field", custom_field_name, "fieldtype") != "Small Text":
		# This app previously created an incompatible Table field. Recreate only
		# that app-owned field as text, which is supported in child-table grids.
		frappe.delete_doc("Custom Field", custom_field_name, force=True, ignore_permissions=True)
		field = None
	if field:
		custom_field = frappe.get_doc("Custom Field", custom_field_name)
		custom_field.update(values)
		custom_field.save(ignore_permissions=True)
	else:
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": "Workflow Transition",
				"fieldname": fieldname,
				**values,
			}
		).insert(ignore_permissions=True)


def clear_auto_seeded_workflow_recipients():
	"""Undo only the earlier broad, automatic recipient population.

	This is intentionally a one-time repair command, not part of provisioning.
	It clears the values that this app populated across unrelated workflows.
	"""
	for workflow_name in frappe.get_all("Workflow", pluck="name"):
		workflow = frappe.get_doc("Workflow", workflow_name)
		changed = False
		for transition in workflow.transitions:
			if transition.get("bci_alert_users"):
				transition.bci_alert_users = None
				changed = True
		if changed:
			workflow.save(ignore_permissions=True)


def seed_requested_workflow_recipients():
	"""Seed only the operational document types and recipients requested by BCI.

	Only the business rules requested by BCI are populated. Any unrelated
	workflow remains blank until a user or role is explicitly entered.
	"""
	all_states = {
		"Material Request": PROCUREMENT_USERS,
		"Purchase Receipt": PROCUREMENT_USERS,
		"Request For Job Applicant": RECRUITMENT_USERS,
		"Job Applicant": RECRUITMENT_USERS,
		"Leave Application": HR_REQUEST_USERS,
		"Leave Request": HR_REQUEST_USERS,
		"Leave Requests": HR_REQUEST_USERS,
		"Request For Advance": HR_REQUEST_USERS,
		"Vacation Salary Request": HR_REQUEST_USERS,
		"Salary Increment Request": HR_REQUEST_USERS,
		"Employee Incentive": HR_REQUEST_USERS,
		"Full and Final Statement": HR_REQUEST_USERS,
		"Full and Final Settlement": HR_REQUEST_USERS,
		"Employee Custody": HR_REQUEST_USERS,
		"Purchase Request": PROCUREMENT_USERS,
		"Expense Sheet": PROCUREMENT_USERS,
		"Transportation Cost Exception": MUHED_USERS,
		"Customer Aging Limit Pass": MUHED_USERS,
		"Material Complain": MUHED_USERS,
		"Customer Price Exception": MUHED_USERS,
		"Customer Credit Limit Bypass": MUHED_USERS,
		"Technical Visit Request": TECHNICAL_VISIT_USERS,
		"Submittal Request": ASIM_USERS,
		"Technical Support": ASIM_USERS,
		"Sample Request": SAMPLE_REQUEST_USERS,
	}
	state_specific = {
		("Purchase Order", "To be Checked"): PO_CHECK_USERS,
		("Purchase Order", "Checked"): PO_APPROVAL_USERS,
		("Customer RFQ", "Created"): CUSTOMER_RFQ_CREATED_USERS,
		("Customer RFQ", "In Progress"): CUSTOMER_RFQ_IN_PROGRESS_USERS,
	}
	for workflow_name in frappe.get_all("Workflow", filters={"is_active": 1}, pluck="name"):
		workflow = frappe.get_doc("Workflow", workflow_name)
		changed = False
		for transition in workflow.transitions:
			recipients = state_specific.get((workflow.document_type, transition.state))
			if recipients is None:
				recipients = all_states.get(workflow.document_type)
			if not recipients or transition.get("bci_alert_users"):
				continue
			transition.bci_alert_users = ", ".join(recipients)
			changed = True
		if changed:
			workflow.save(ignore_permissions=True)


def _notify_users(users, doc, subject, message):
	"""Create one immediate, standard ERP alert per eligible recipient."""
	payload = {
		"type": "Alert",
		"document_type": doc.doctype,
		"document_name": doc.name,
		"subject": subject,
		"from_user": doc.modified_by or doc.owner,
		"email_content": f"{message}<!-- {ALERT_MARKER} -->",
	}
	for user in dict.fromkeys(users):
		if _is_enabled_system_user(user):
			_create_notification(user, payload)


def _is_enabled_system_user(user):
	return bool(
		user
		and frappe.db.exists(
			"User", {"name": user, "enabled": 1, "user_type": "System User"}
		)
	)


def _create_notification(user, payload):
	notification = frappe.new_doc("Notification Log")
	notification.update(payload)
	notification.for_user = user
	notification.insert(ignore_permissions=True)
