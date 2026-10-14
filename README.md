# BCI Workflow Alerts

Desk-side sound and visual alerts for Customer RFQ Notification Logs.

The app listens for Frappe's realtime `notification` event, fetches the current
user's recent Notification Log entries, and reacts only to entries for the
`Customer RFQ` DocType. The standard notification bell remains unchanged.

## Install

```bash
bench --site erp.bcisaudi.net install-app bci_workflow_alerts
bench build --app bci_workflow_alerts
bench --site erp.bcisaudi.net migrate
```

Reload the Desk with Ctrl+Shift+R after the build. The browser requires a user
gesture before allowing audio; the app unlocks audio on the user's first click
or key press and also provides an Enable sound button on the alert.
