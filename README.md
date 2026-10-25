# MedCore HMS — Role-Based Smart Hospital Edition

A full-stack Hospital Management System using React + Vite and Django REST Framework with JWT authentication.

## Product requirements alignment

The supplied **MedCore HMS Product Requirements Document v1.0** guides the care workflows in this existing React and Django application. The appointment flow now allows a patient to request a booking, rejects doctor or patient time conflicts, respects configured doctor availability, and follows `Pending → Confirmed → In Progress → Completed` with cancellation and no-show paths. Administrators can create an encounter record from a confirmed appointment, and doctors advance the encounter's status and notes; the record is linked to that appointment and cannot be edited or deleted through the API. The site exposes booking, availability, status actions, and encounter entry in the role-based pages.

The application now covers the PRD's multi-hospital, nine-role scope: hospital onboarding, nursing vitals, a laboratory queue, pharmacy inventory with FIFO dispensing, itemised billing, insurance claims, revenue analytics, an audit log and OTP verification. It keeps a React + Django architecture rather than the PRD's suggested Next.js/NestJS/Prisma stack. Django REST Framework fills the same roles: permission classes stand in for guards, serializers for DTOs and migrations for Prisma. Historical CSV admissions remain distinct from live care records.

- Architecture, tenancy, concurrency and the role matrix: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- ER diagram and data-model decisions: [docs/ER-DIAGRAM.md](docs/ER-DIAGRAM.md)
- Interactive API documentation (Swagger UI): `http://127.0.0.1:8000/api/docs/` (OpenAPI schema at `/api/schema/`)

## Roles and demo logins

| Role | What they work on |
| --- | --- |
| Super Admin | Hospital onboarding and verification, platform analytics, audit log |
| Hospital Admin | Everything in their hospital: staff accounts, departments, records, pharmacy, finance |
| Doctor | Appointments, encounter status and notes, lab orders and approvals, viewing prescriptions, availability |
| Nurse | Vitals and medication-administration notes (append-only), beds, admitted patients |
| Receptionist | Registration, scheduling, invoice creation |
| Lab Technician | Sample → processing → result entry; a different technician or doctor approves |
| Pharmacist | Medicines, batches, expiry quarantine, FIFO dispensing, stock alerts |
| Accountant | Invoice line items, insurance (TPA) claims, revenue analytics |
| Patient | Own appointments, records, approved lab results, bills and payments |

To create invented demo data (2 hospitals, 8 doctors, 30 patients, two weeks of appointments) in a **demo database only**:

```powershell
cd backend
.\.venv\Scripts\python.exe manage.py seed_prd_demo --yes
```

Every role then has a login named `demo_<role>`, for example `demo_admin`, `demo_doctor`, `demo_nurse`, `demo_lab_tech`, `demo_pharmacist`, `demo_accountant`, `demo_receptionist`, `demo_super_admin` and `demo_patient`. All demo logins use the password `Demo@12345`.

## Tests

```powershell
cd backend; .\.venv\Scripts\python.exe manage.py test api      # 65 tests, ~86% coverage
cd frontend; npm test                                          # Vitest component tests
cd frontend; npx playwright install chromium; npm run e2e      # 6 end-to-end browser journeys
```

The Playwright suite starts its own backend on port 8001, with a throwaway seeded database (`backend/e2e.sqlite3`), and a frontend on port 5175. It never touches `db.sqlite3`. It covers six journeys:

- registration, sign-in and sign-out
- booking an appointment
- the admin command centre
- pharmacist FIFO dispensing
- invoice total versus its line items
- the printable prescription report

The PRD's mandatory scenarios are in `backend/api/test_operations.py`:

- tenancy isolation
- a patient cannot read another patient's records
- concurrent booking of the same slot
- refresh-token reuse after rotation
- refusing to dispense expired medicine
- invoice total equals the sum of its line items
- the Stripe webhook signature check

CI (`.github/workflows/ci.yml`) runs on PostgreSQL. It fails if backend coverage drops below 70%, and it publishes the coverage report and the OpenAPI schema as build artifacts.

## Security summary

- **Tokens:** 15-minute access tokens. The refresh token lives only in an **httpOnly, SameSite=Strict cookie** scoped to `/api/`, which page scripts cannot read. It is rotated on use and blacklisted after rotation and on logout.
- **Encryption at rest:** diagnosis, symptoms, treatment, notes, adverse reactions and nursing medication notes are encrypted per column with Fernet (`FIELD_ENCRYPTION_KEY`; production refuses to start without it). Keep the key with your other secrets: if it is lost, those fields can't be read.
- **Virus scanning:** when `CLAMAV_HOST` is set, every upload is streamed to ClamAV. Infected files are rejected, and uploads pause if the scanner is unreachable.
- **Passwords:** bcrypt with cost 12. Existing PBKDF2 hashes upgrade on the next login.
- **Rate limiting:** 100 requests per 15 minutes on authentication endpoints, 1000 requests per minute on the rest of the API.
- **CORS and headers:** CORS uses a strict allow-list (`CORS_ALLOWED_ORIGINS`). Responses send `nosniff`, `DENY` framing and a same-origin referrer policy. HTTPS and HSTS are enforced in production and at Nginx.
- **Audit log:** every create, update and delete is recorded with the user, IP address and time.
- **OTP:** 6-digit codes for email or SMS verification. Only their hashes are stored, and they expire after 10 minutes with 5 attempts allowed.
- **Uploads:** checked by file signature and size.
- **Payments:** confirmed only through signed provider webhooks.

Deliberate differences from the PRD:

- Live updates use 15-second polling plus in-app notifications rather than Socket.IO.
- API responses use DRF's standard shapes rather than the `{success, data}` envelope, so existing clients keep working.
- The SameSite=Strict refresh cookie requires the frontend and API on the same site, as in the Docker/Nginx setup. Hosting the frontend on a different domain (for example Vercel) needs `SameSite=None; Secure` and CSRF protection instead.

## Docker deployment

```powershell
copy .env.example .env      # then fill in secrets
docker compose up --build   # https://localhost
```

The Compose stack runs PostgreSQL 16, Redis 7, the API (gunicorn), a scheduler (reminders every 15 minutes, a nightly pharmacy report), the frontend and an Nginx edge with TLS. Put `fullchain.pem` and `privkey.pem` in `nginx/certs/`; see [DEPLOYMENT.md](DEPLOYMENT.md).

## Historical healthcare dataset

The supplied `healthcare_dataset.csv` remains stored as imported visits in the backend. Administrators and receptionists can search and page through registered patient profiles and imported visits in one **Patients** table. The table includes the union of fields from both sources, with unavailable values marked **Not provided**. Each row has a stable Record ID; imported visits do not have registered patient IDs, phone numbers or login credentials.

To import or resume an import into another database after running migrations:

```powershell
cd backend
python manage.py import_healthcare "C:\path\to\healthcare_dataset.csv"
```

The command uses CSV row numbers to skip rows already imported, so rerunning it does not duplicate records.

The imported CSV rows remain available in the database for archival or export use. Showing them in the Patients table does not turn them into registered patient accounts.

Patient records cannot be deleted from the Patients page, patient API, Django admin or application ORM. Removing a linked login account leaves its patient profile intact. Staff can still update registered profile details when needed.

## Copy application data to MongoDB Atlas

The `export_to_mongodb` command copies every `api` model, including users, live hospital records, and historical admissions, into MongoDB collections named after their Django tables. It keeps each SQL primary key as MongoDB `_id` and upserts records, so a repeat export does not duplicate them. Django continues to use the configured SQLite or MySQL database for the website; rerun the command to copy later changes.

```powershell
cd backend
pip install -r requirements.txt
$env:MONGODB_URI = 'mongodb+srv://YOUR_USER:YOUR_PASSWORD@YOUR_CLUSTER.mongodb.net/?appName=Cluster0'
$env:MONGODB_DB_NAME = 'medcore_hms'
python manage.py export_to_mongodb --dry-run
python manage.py export_to_mongodb
```

Set `MONGODB_URI` and `MONGODB_DB_NAME` in your shell or in the ignored `backend/services.local.json` configuration file, which the backend loads automatically. MongoDB Atlas must allow your network address and grant the database user write access. Do not commit credentials to the repository.

## Live data

MedCore reads and writes hospital records through the Django API and database; the frontend has no dashboard fixture data. Changes made by another staff member are shown automatically within 15 seconds, or immediately with **Refresh**.

Create staff users and their linked Doctor/Patient profiles through Django admin or your organisation's onboarding process. `seed_demo.py` is only for local UI experimentation—do not run it against a real database.

## Role-based live data

`GET /api/dashboard/` is authenticated and returns a different live response for each signed-in role. The backend enforces these rules, so changing a page in the browser cannot expose another person's data.

| Signed-in role | Dashboard data returned |
| --- | --- |
| Administrator | Hospital-wide patients, doctors, revenue, beds, departments and appointments. |
| Doctor | Only the doctor's assigned patients, appointments, availability and emergency cases. |
| Patient | Only the patient's own appointments, medical records, prescriptions and bills. |

The same restrictions apply to `/api/patients/`, `/api/appointments/`, `/api/medical-records/`, `/api/prescriptions/`, `/api/bills/` and `/api/timeline/`. A patient's token cannot access bed occupancy or another patient's timeline.

Only administrators can create medical records from confirmed appointments and add prescriptions to those records. Doctors and patients can view the records available to their accounts without **New medical record** or **New prescription** actions. Existing patient-submitted entries remain visible and labeled **Patient submitted**.

## Included modules
- Role-specific dashboards for all nine roles listed above
- Departments, doctors, patients and appointments stored in the configured database
- Medical-history records and prescriptions
- Paid, pending and cancelled bills
- Appointment reminders and payment notifications
- Appointment calendar/date/status/search filters
- Doctor availability slots for appointment planning
- Patient medical-history timeline API
- Bed/ward availability tracker
- Emergency patient priority tracking
- Dashboard workload/status/revenue/capacity cards and charts
- Search by patient ID, phone, doctor or appointment date
- Invoice print / browser PDF workflow
- Dark mode and responsive mobile layout
- Backend role-based permissions and queryset filtering

## Backend setup

### Care portal additions

The signed-out homepage lists registered doctors and configured departments. Hospital administrators can edit department assignments, qualifications, languages, biography, fees and availability from **Doctors → Manage profile**. Doctor accounts show their assigned department on their dashboard. Imported doctor names are historical references: missing qualifications, departments, experience and availability are not inferred. Imported patient visits have stable `VISIT-` record IDs and are not registered patient accounts; absent fields display **Not provided**.

**Documents** accepts PDF, PNG and JPEG files up to 5 MB. Files are stored privately in the database and are downloaded only through authenticated, patient-scoped API requests. Patients can access their own documents; doctors can access documents for patients linked through their appointments or records; administrators can access all documents. Uploads are labeled by source, not represented as verified clinical findings. Include document content when backing up the database. File signatures are checked; this does not replace a malware-scanning service for a production deployment.

**Appointments → Request new time** checks published doctor availability, patient/doctor conflicts, and future dates. Only pending or confirmed visits can be rescheduled; they return to Pending and create in-app notifications for the patient and doctor.

**Laboratory** allows administrators to configure tests and record sample/processing updates. Administrators and doctors can order tests for accessible clinical records. Results progress through Ordered → Sample collected → Processing → Review → Approved. Doctors or administrators approve results, and patients see only their own approved results. These workflow states do not certify medical accuracy.

**Forgot password** uses a one-hour, single-use reset link. Resetting a password invalidates existing JWTs. Sign in again after deploying this update, since older tokens do not contain the password-revocation claim.

### Email and reminders

Email is prepared for configuration. By default it writes development messages into the ignored `backend/private-outbox/` directory; it does **not** send messages to patients. See `backend/email-settings.example.ps1` for SMTP variables. Set them in the shell that launches Django and restart the server. No `.env` loader is configured. Keep SMTP passwords private; use your provider's verified sender address. `FRONTEND_URL` must point to the real patient portal when deployed.

From `backend`, preview tomorrow's reminders without creating or sending anything:

```powershell
.\.venv\Scripts\python.exe manage.py send_appointment_reminders --dry-run
```

Run `send_appointment_reminders` to create in-app reminders. Add `--email --sms` for configured external providers and opted-in patients. The command skips previously processed appointments and flags uncertain submissions for review. The Windows task `MedCore-HMS-Calendar-Reminders` is registered on this workstation to run every 15 minutes while this user is logged in. Other deployments must install their own scheduled job. See [SERVICE_SETUP.md](SERVICE_SETUP.md) for configuration and verification.

Secure care-team messaging is available in **Messages**. Razorpay payment links, server-side payment verification, signed webhooks, and opt-in Twilio SMS reminders are implemented. External payments and SMS default to disabled until credentials are configured. **Service Setup** shows configuration status to administrators. No live provider verification is implied by local tests. Copy `backend/services.example.json` to the ignored `backend/services.local.json` for private configuration shared by the API and scheduler. Environment variables take precedence.

```powershell
cd backend
# activate your existing virtual environment first
pip install -r requirements.txt
python manage.py makemigrations api
python manage.py migrate
python manage.py runserver
```

Backend API: `http://127.0.0.1:8000/api/`

## Starting the installed project

From the project folder, run `powershell -File .\Start-MedCore.ps1`. This starts the backend and frontend in the background, checks that both respond, and opens the site in your default browser. Run it again after restarting Windows. Startup errors are saved in `backend-active.err.log` and `frontend-active.err.log`. Initial dependency installation is still required.

## Frontend setup
```powershell
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173/`

## Notes
- Production settings, backup/restore commands, and external deployment prerequisites are documented in [DEPLOYMENT.md](DEPLOYMENT.md). Production configuration is opt-in and does not change the local demo.
- Patient and doctor data is filtered by role on the backend, not only hidden in the UI.
- Receptionists can coordinate front-office workflows but do not receive administrator-only destructive management permissions.
- The invoice button opens a print-ready invoice; choose **Save as PDF** in the browser print dialog.
