# MedCore HMS entity-relationship diagram

This diagram is generated from `backend/api/models.py`. Imported CSV admissions (`ImportedAdmission`) are a standalone historical table, with only an optional link to a doctor.

```mermaid
erDiagram
  HOSPITAL ||--o{ USER : employs
  HOSPITAL ||--o{ DEPARTMENT : has
  HOSPITAL ||--o{ PATIENT : registers
  USER ||--o| DOCTOR : "profile"
  USER ||--o| PATIENT : "profile"
  DEPARTMENT ||--o{ DOCTOR : contains
  DOCTOR ||--o{ DOCTOR_AVAILABILITY : publishes
  DOCTOR ||--o{ APPOINTMENT : attends
  PATIENT ||--o{ APPOINTMENT : books
  APPOINTMENT ||--o| MEDICAL_RECORD : "encounter (unique)"
  PATIENT ||--o{ MEDICAL_RECORD : has
  MEDICAL_RECORD ||--o{ PRESCRIPTION : issues
  PRESCRIPTION ||--o{ PRESCRIPTION_ITEM : lists
  MEDICINE ||--o{ PRESCRIPTION_ITEM : "dispensed as"
  MEDICINE ||--o{ MEDICINE_BATCH : "stocked in"
  MEDICAL_RECORD ||--o{ LAB_ORDER : orders
  LAB_TEST ||--o{ LAB_ORDER : "type of"
  PATIENT ||--o{ BILL : owes
  APPOINTMENT ||--o{ BILL : "billed for"
  BILL ||--o{ BILL_ITEM : "line items"
  BILL ||--o{ PAYMENT : "paid by"
  BILL ||--o| PAYMENT_CHECKOUT : "online checkout"
  BILL ||--o{ INSURANCE_CLAIM : "claimed via"
  PATIENT ||--o{ VITALS_ENTRY : "observed"
  PATIENT ||--o{ PATIENT_DOCUMENT : uploads
  PATIENT ||--o{ BED : occupies
  PATIENT ||--o{ CARE_THREAD : messages
  DOCTOR ||--o{ CARE_THREAD : messages
  CARE_THREAD ||--o{ CARE_MESSAGE : contains
  USER ||--o{ NOTIFICATION : receives
  USER ||--o{ AUDIT_LOG : "performed"
  USER ||--o{ VERIFICATION_CODE : "OTP"
  APPOINTMENT ||--o{ APPOINTMENT_REMINDER : "24H / 1H"

  APPOINTMENT {
    date date
    time time
    string status "Pending→Confirmed→In Progress→Completed | Cancelled | No Show"
    bool is_emergency
  }
  MEDICAL_RECORD {
    text diagnosis
    string icd10_code
    string blood_pressure
    int pulse
    decimal temperature
    int spo2
    decimal height_cm
    decimal weight_kg
    json vaccination_history
    json family_history
  }
  MEDICINE_BATCH {
    string batch_number
    date expiry_date "FIFO order"
    int quantity
    bool quarantined
  }
  BILL {
    decimal total "= sum of BILL_ITEM amounts"
    string status
  }
```

## Key decisions

- **Doctor availability**: dated time windows (`DoctorAvailability`) rather than a repeating weekly rule. This is simple to query and makes one-off leave easy, at the cost of publishing each day.
- **Prescription ↔ medicine**: `PrescriptionItem` holds the per-item dosage, frequency and duration, plus how much was dispensed and when.
- **Lab results**: hybrid. A structured value is compared automatically against the test's `low-high` reference range, with free-text notes and an optional report URL alongside it.
- **Soft deletes and retention**: `Patient`, `Doctor` and `Appointment` have `deleted_at`. Patients, medical records and vitals cannot be deleted at all (`pre_delete` raises `ProtectedError`).
- **Indexes**: foreign keys (hospital, patient, doctor) are indexed by Django. `Appointment(date, time)`, `MedicineBatch.expiry_date` and `ImportedAdmission.admission_date` are indexed explicitly.
