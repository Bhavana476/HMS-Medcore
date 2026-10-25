# Deployment preparation

Local development continues to use `medcore.settings`. Production must use `DJANGO_SETTINGS_MODULE=medcore.production`; it refuses to start without a strong secret, explicit hosts and an HTTPS frontend URL.

Set secrets through the hosting provider's private environment settings:

```text
DJANGO_SETTINGS_MODULE=medcore.production
SECRET_KEY=<unique random secret of at least 50 characters>
ALLOWED_HOSTS=api.your-hospital-domain.example
FRONTEND_URL=https://your-hospital-domain.example
```

Build the frontend with `VITE_API_URL=https://api.your-hospital-domain.example/api` set before `npm run build`. Publish `frontend/dist` as static assets with all frontend routes falling back to `index.html`. Never place secret credentials in Vite variables.

The backend needs a production WSGI server pointing to `medcore.wsgi:application`, persistent database storage and a reverse proxy providing valid HTTPS. Do not expose Django's development server. Install the chosen hosting platform's WSGI server, then run migrations and collect static files with the production settings. Serve collected static files through the web server. Enable `TRUST_PROXY_HTTPS=True` only if the private reverse proxy overwrites `X-Forwarded-Proto` and the backend cannot be reached directly.

Before publishing, run `python manage.py check --deploy --fail-level WARNING` with production environment variables. The settings follow the [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/). HSTS covers subdomains: ensure every subdomain supports HTTPS before enabling this configuration on the real domain.

## Docker Compose (PostgreSQL, Redis, Nginx, TLS)

1. Copy `.env.example` to `.env` and set `SECRET_KEY`, `DB_PASSWORD`, `ALLOWED_HOSTS`, `FRONTEND_URL` and `CORS_ALLOWED_ORIGINS`.
2. Add the TLS certificate and key as `nginx/certs/fullchain.pem` and `nginx/certs/privkey.pem`. For a local trial, generate a self-signed pair:
   `openssl req -x509 -nodes -newkey rsa:2048 -days 365 -keyout nginx/certs/privkey.pem -out nginx/certs/fullchain.pem -subj "/CN=localhost"`
   For a real domain, use Let's Encrypt (certbot) and mount its live directory instead.
3. Run `docker compose up --build -d`. The API container applies migrations on start.
4. Create the first super admin: `docker compose exec api python manage.py createsuperuser`, then set the role in Django admin.

The `scheduler` service runs appointment reminders every 15 minutes and the pharmacy expiry report once a day, so no Windows scheduled task is needed in Docker.

**Hosting options from the PRD.**

- Run this Compose stack on AWS EC2 and point `DB_HOST` at RDS PostgreSQL. Alternatively, use Neon or Supabase for the database and Upstash for `REDIS_URL`.
- To host the frontend on Vercel instead, deploy `frontend/` with `VITE_API_URL=https://<api-domain>/api` and add the Vercel URL to `CORS_ALLOWED_ORIGINS`.
- Set `SENTRY_DSN` to enable error tracking.
- Point the Stripe webhook at `/api/payments/webhook/stripe/` and the Razorpay webhook at `/api/webhooks/razorpay/`.

## Backups and restore

For the current SQLite installation, run `python manage.py backup_database`. The command uses SQLite's backup API and checks the snapshot's integrity. Backups go to ignored `backend/private-backups/`; patient documents are stored in the database and included. This directory contains sensitive clinical data: keep access restricted and copy backups to encrypted storage with a hospital-approved retention policy. A backup on the same disk does not protect against disk failure. Provider credentials are not included; retain them separately in a secret manager.

To restore, stop the API and reminder scheduler, retain the current database as a separate rollback copy, and restore a selected verified snapshot to `backend/db.sqlite3`. Run migrations using the matching application version, verify login and representative records, then restart the API and scheduler. Never restore over a running database. Use provider-managed backups for MySQL.

## Outstanding external setup

Choose hosting and domain, configure DNS and TLS, configure private email/payment/SMS credentials as described in SERVICE_SETUP.md, and install the reminder job on the production host. Verify delivery using designated test recipients and Razorpay test mode before enabling live transactions. Populate doctor details only from hospital-approved information. Local automated checks do not verify these external services.
