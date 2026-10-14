app_name = "bci_workflow_alerts"
app_title = "BCI Workflow Alerts"
app_publisher = "BCI ERP"
app_description = "Visual and sound alerts for Customer RFQ workflow notifications"
app_email = "info@bcisaudi.com"
app_license = "MIT"

app_include_js = "/assets/bci_workflow_alerts/js/bci_workflow_alerts.js?v=20261014.16"
app_include_css = "/assets/bci_workflow_alerts/css/bci_workflow_alerts.css?v=20261014.16"

after_migrate = "bci_workflow_alerts.events.provision_workflow_recipient_fields"
after_install = "bci_workflow_alerts.events.provision_workflow_recipient_fields"

# Notify the roles allowed to take the next action for the current workflow
# state. The role lookup happens at run time, so later workflow-role changes
# require no code or recipient-list changes.
doc_events = {
	"*": {
		"on_update": "bci_workflow_alerts.events.resolve_alert_after_status_change",
	},
	"Customer RFQ": {
		"after_insert": "bci_workflow_alerts.events.notify_pending_workflow_roles",
		"on_update": "bci_workflow_alerts.events.notify_when_workflow_state_changes",
	},
	"Material Request": {
		"after_insert": "bci_workflow_alerts.events.notify_material_request",
	},
	"Sales Order": {
		"on_submit": "bci_workflow_alerts.events.notify_sales_order",
	},
	"Material Transfer Request": {
		"on_submit": "bci_workflow_alerts.events.notify_material_transfer_request",
		"on_update": "bci_workflow_alerts.events.notify_reviewed_material_transfer_request",
	},
	"Supplier": {
		"after_insert": "bci_workflow_alerts.events.notify_supplier_review",
		"on_update": "bci_workflow_alerts.events.resolve_supplier_enabled_alert",
	},
	"Delivery Note": {
		"after_insert": "bci_workflow_alerts.events.notify_delivery_note",
	},
	"Purchase Request": {
		"after_insert": "bci_workflow_alerts.events.notify_procurement_request",
	},
	"Expense Sheet": {
		"after_insert": "bci_workflow_alerts.events.notify_procurement_request",
	},
	"Purchase Order": {
		"on_update": "bci_workflow_alerts.events.notify_purchase_order_state",
	},
	"Purchase Receipt": {
		"after_insert": "bci_workflow_alerts.events.notify_purchase_receipt",
	},
	"Request For Job Applicant": {
		"after_insert": "bci_workflow_alerts.events.notify_recruitment_request",
	},
	"Job Applicant": {
		"after_insert": "bci_workflow_alerts.events.notify_recruitment_request",
	},
	"Leave Application": {
		"after_insert": "bci_workflow_alerts.events.notify_hr_request",
	},
	"Request For Advance": {
		"after_insert": "bci_workflow_alerts.events.notify_hr_request",
	},
	"Vacation Salary Request": {
		"after_insert": "bci_workflow_alerts.events.notify_hr_request",
	},
	"Employee Incentive": {
		"after_insert": "bci_workflow_alerts.events.notify_hr_request",
	},
	"Full and Final Statement": {
		"after_insert": "bci_workflow_alerts.events.notify_hr_request",
	},
	"Employee Custody": {
		"after_insert": "bci_workflow_alerts.events.notify_hr_request",
	},
	"Staff Notes": {
		"after_insert": "bci_workflow_alerts.events.notify_selected_employee",
	},
	"Instruction From Sales Management To Staff": {
		"after_insert": "bci_workflow_alerts.events.notify_selected_employee",
	},
	"Transportation Cost Exception": {
		"after_insert": "bci_workflow_alerts.events.notify_muhed_review",
	},
	"Customer Aging Limit Pass": {
		"after_insert": "bci_workflow_alerts.events.notify_muhed_review",
	},
	"Material Complain": {
		"after_insert": "bci_workflow_alerts.events.notify_muhed_review",
	},
	"Customer Price Exception": {
		"after_insert": "bci_workflow_alerts.events.notify_muhed_review",
	},
	"Customer Credit Limit Bypass": {
		"after_insert": "bci_workflow_alerts.events.notify_muhed_review",
	},
	"Technical Visit Request": {
		"after_insert": "bci_workflow_alerts.events.notify_technical_visit_request",
	},
	"Submittal Request": {
		"after_insert": "bci_workflow_alerts.events.notify_asim_request",
	},
	"Technical Support": {
		"after_insert": "bci_workflow_alerts.events.notify_asim_request",
	},
	"Sample Request": {
		"after_insert": "bci_workflow_alerts.events.notify_sample_request",
	},
	"Workflow": {
		"on_update": "bci_workflow_alerts.events.reconcile_workflow_recipient_alerts",
	},
}
