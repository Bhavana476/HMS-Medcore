# MedCore service setup

Messaging, reminder preferences, scheduled reminders and Razorpay checkout are implemented. Live email, SMS and payments require your own provider accounts. Do not paste passwords or API secrets into chat or commit them.

## Private configuration

Copy `backend/services.example.json` to `backend/services.local.json` and fill in the appropriate values locally. The local file is ignored by Git. Django and scheduled reminder commands both load it. Environment variables take precedence. Restart Django after changes. Never expose this configuration file through a web server.

The administrator's **Service Setup** page shows configuration flags, the last scheduler heartbeat and counts of reminders/payments needing review. It never returns credentials. Configured does not mean a provider connection has been tested successfully.

## SMTP email

Set `EMAIL_BACKEND` to `django.core.mail.backends.smtp.EmailBackend`, fill in your SMTP host/user/password and verified `DEFAULT_FROM_EMAIL`, and use your provider's port/TLS settings. Set `FRONTEND_URL` to the actual patient portal URL so password-reset links go to the correct website.

Until configured, password-reset messages are written to `backend/private-outbox/` for local development only. Appointment emails are not submitted to the development file backend. Test with an account and address you control before enabling delivery to patients.

## Twilio SMS

Set `SMS_ENABLED` to `True`, then set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and `TWILIO_FROM_NUMBER`. Phone numbers must use international E.164 format, such as `+91` followed by the national number. Configure the sender and destination permissions required by your Twilio account and country before testing.

Patients opt in or out through **Notifications → Appointment reminders**. Email and SMS are off by default for each patient. Reminder messages contain only appointment date/time and a prompt to sign in, not medical findings or prescriptions.

External submissions are recorded as `SUBMITTED`, not claimed as delivered. A timeout or uncertain submission becomes `UNKNOWN` and is not automatically retried: check the provider first to avoid duplicate messages. This release does not track carrier delivery receipts.

Reference: [Twilio message API](https://www.twilio.com/docs/messaging/api/message-resource).

## Razorpay payments

Start with test credentials. Set `PAYMENTS_ENABLED` to `True`, `PAYMENT_MODE` to `test`, and supply `RAZORPAY_KEY_ID` (beginning `rzp_test_`) and `RAZORPAY_KEY_SECRET`. Use only test bills/accounts during provider testing. Switch to `live` and `rzp_live_` credentials only after verifying the full flow against your own Razorpay account. Do not switch modes with unresolved checkouts.

Patients can choose **My Bills → Prepare payment**, then **Continue to Razorpay**. The amount is taken from the database, not the browser. The hosted checkout handles payment details; MedCore does not store card information. Patient names, phone numbers and diagnoses are not sent when creating a payment link. Provider email/SMS notifications are disabled because reminders are managed separately.

After payment, **Check payment status** fetches the link directly from Razorpay. A bill becomes Paid only when the provider reports the exact amount, currency, reference and paid status. A repeated check cannot create a duplicate payment entry. Invoices with a checkout cannot be edited through the API.

For automatic confirmation, configure a Razorpay webhook for `payment_link.paid` at:

`https://YOUR-API-HOST/api/webhooks/razorpay/`

Set the same dedicated secret in `RAZORPAY_WEBHOOK_SECRET`. The endpoint verifies the raw request signature, then independently fetches the payment status from Razorpay. Browser callbacks cannot mark bills paid. Localhost needs a provider-supported public test endpoint; do not expose real patient data just to test webhooks.

If a checkout submission times out, it enters REVIEW rather than creating a second link. Billing staff must inspect the provider dashboard. Use `python manage.py reconcile_checkout --bill BILL_ID --provider-id plink_ID` to attach and reconcile a link only after its unique reference matches the pending checkout. The command verifies the bill amount, currency and reference. Expired links, refunds and disputes require billing staff handling in this release; refunds are not initiated by MedCore.

References: [Create a payment link](https://razorpay.com/docs/api/payments/payment-links/create-standard/), [Fetch link status](https://razorpay.com/docs/api/payments/payment-links/fetch-id-standard), [Validate webhooks](https://razorpay.com/docs/webhooks/validate-test/).

## Scheduled reminders

Windows task name: `MedCore-HMS-Calendar-Reminders`. It invokes the project's virtual-environment Python directly every 15 minutes and processes tomorrow's pending/confirmed appointments. It runs with the current user's limited privileges while that user is logged in. The computer must be on. External channels require both provider configuration and patient opt-in; the task does not bypass those checks.

Check it in Windows Task Scheduler, or with `Get-ScheduledTask -TaskName MedCore-HMS-Calendar-Reminders` and `Get-ScheduledTaskInfo -TaskName MedCore-HMS-Calendar-Reminders`. The installer is `backend/install-reminder-task.ps1`; it refuses to overwrite an unrelated task of the same name. No PowerShell execution-policy setting is changed.

For a non-Windows deployment, schedule `python manage.py send_appointment_reminders --email --sms` at least once daily in the hospital's configured time zone. Run `--dry-run` first. Do not run concurrent schedulers against different copies of the database. Back up the database and reminder ledger together.

## Secure conversations

**Messages** is available to patients, doctors and administrators. A patient/doctor conversation can be started only when an appointment or medical record links the pair. Patients see their own threads; doctors see their own; administrators can access threads for hospital operations. Sender identity is set on the server. Messages have a 4,000-character limit and are paginated. There are no edit/delete actions. These are authenticated application messages, not end-to-end encrypted messages. Deploy behind HTTPS and protect database backups.

The interface explains that conversations are for non-urgent questions and are not continuously monitored. The hospital must establish response ownership and staffing before using this operationally.

## Verification boundaries

Automated tests exercise real Django endpoints and mock external provider responses. They do not establish that your provider credentials, approved sender, live payment account or webhook routing work. Frontend build and server-render smoke checks are separate from browser end-to-end testing. A connected browser is required for the remaining visual and interactive review.
