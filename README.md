# ATRG — Automated Test Report Generation System

ATRG is a web-based prototype for automating test report generation in high-voltage testing laboratories.

It is designed for the CPRI Short Circuit Laboratory problem statement:

> Collect data from customer requests, test logs, measurement records, and laboratory databases; validate it; automatically populate a report template; generate a complete test report with minimal manual intervention.

The prototype demonstrates one complete vertical slice using the real sample job:

```text
Test Series No: CPRIBLRSCL25T1654
Short form: 25T1654
Sample Code: HVD25S0847
Equipment: 250 kVA, 11000/433 V, Dyn11, ONAN transformer
Standard: IS 1180
EEL Level: EEL-1
```

---

## Core Value

The system removes repeated manual re-entry by creating one controlled digital workflow:

```text
Customer request
    ↓
Engineer bay data entry / CSV import / OCR-assisted scan review
    ↓
Typed measurements with units and provenance
    ↓
Automatic PASS/FAIL evaluation against standard clauses
    ↓
PDF report generation
    ↓
Engineer → Quality → HOD approval chain
    ↓
Lock + SHA-256 integrity hash
    ↓
Customer notification and released report download
```

---

## Implemented Modules

### 1. Core Schema and Types

Strict typed database model:

- `Customer`
- `CustomerAlias`
- `Job`
- `Sample`
- `TestType`
- `Test`
- `Parameter`
- `Measurement`
- `LimitRule`
- `Result`
- `Document`
- `Report`
- `Approval`
- `AuditLog`
- `Notification`

Design choices:

- Customer names are foreign keys, not free text.
- Measurements use `Decimal(12,4)`, not floats.
- Units come from the parameter dictionary.
- Every measurement stores source:
  - `MANUAL`
  - `IMPORT`
  - `OCR`
- OCR/import rows store raw text and confidence.
- Audit log records create/update/transition events.

---

### 2. Validation and Rules Engine

The rules engine evaluates measurements against seeded `LimitRule` rows.

Examples:

```text
No-load loss <= 980 W
Total loss at 100% <= 2930 W
No-load current <= 2%
HV winding rise <= 40°C
LV winding rise <= 40°C
Top oil rise <= 35°C
Ratio error within 0.5%
```

Each verdict includes:

```text
Measured value
Limit
PASS/FAIL
Standard clause
```

---

### 3. Workflow State Machine

Job states:

```text
REQUESTED
IN_PROGRESS
TESTING_DONE
REPORT_DRAFT
QUALITY_REVIEW
HOD_SIGNED
LOCKED
RELEASED
ON_HOLD
```

Roles:

| Role | Rights |
|---|---|
| Customer | Submit request, view progress, download released report |
| Engineer | Enter measurements, import CSV, review OCR, generate draft |
| Quality | Approve/reject report |
| HOD | Sign, lock, release |
| Admin | User/data management |

Once a job is locked, measurement entry is blocked.

---

### 4. Report Engine

Reports are generated from database rows into HTML and then converted to PDF using WeasyPrint.

Report features:

- Versioning
- SHA-256 hash
- Integrity verification
- Released-state download control
- Regeneration after rejection creates a new version

---

### 5. CSV Import

CSV import supports long-format measurement files:

```csv
parameter_code,stage,tap_position,phase,value
NLL_W,BT,,,908
I_NL_A,BT,,,1.689
TOTAL_LOSS_100,BT,,,2486
```

Import flow:

```text
Upload CSV
    ↓
Map columns
    ↓
Dry-run validation
    ↓
Commit valid rows
    ↓
Measurements saved with source=IMPORT
```

---

### 6. OCR Review Queue

OCR is human-assisted.

Flow:

```text
Upload scan
    ↓
OCR extraction
    ↓
Proposed measurement rows
    ↓
Engineer confirms each row
    ↓
Saved with source=OCR, raw_text, confidence
```

If Tesseract is not installed, the system supports manual paste-and-parse mode.

---

### 7. Customer Portal

Customer features:

- Submit test request
- View job progress
- See completed/in-progress tests
- Receive notifications
- Download released report only

Customer cannot see:

- raw readings
- internal verdicts
- draft reports
- audit trail

---

## Technology Stack

- Python
- Django 5
- SQLite
- Bootstrap 5
- htmx
- WeasyPrint
- Pillow
- optional pytesseract

The prototype is designed to run offline on one laptop.

---

## Installation

### 1. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

Windows:

```bash
venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. Seed sample job

```bash
python manage.py seed
```

### 5. Link customer portal user

```bash
python manage.py setup_customer_profiles
```

### 6. Check demo readiness

```bash
python manage.py demo_check
```

### 7. Run server

```bash
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

---

## Demo Users

| Username | Role | Password |
|---|---|---|
| admin | Admin | atrg123 |
| engineer1 | Engineer | atrg123 |
| engineer2 | Engineer | atrg123 |
| quality1 | Quality | atrg123 |
| hod1 | HOD | atrg123 |
| customer1 | Customer | atrg123 |

---

## Main Demo Flow

### Customer

1. Login as `customer1`.
2. Submit a new test request.
3. Track progress.
4. Receive notification when report is released.
5. Download released report.

### Engineer

1. Login as `engineer1`.
2. Open job `CPRIBLRSCL25T1654`.
3. Enter routine measurements.
4. Enter loss measurements or import CSV.
5. Mark tests complete.
6. Generate draft report.
7. Submit for quality review.

### Quality

1. Login as `quality1`.
2. Review auto-verdicts.
3. Approve or reject.

### HOD

1. Login as `hod1`.
2. Sign and lock report.
3. Release report to customer.

---

## Important URLs

| URL | Purpose |
|---|---|
| `/` | Internal dashboard |
| `/admin/` | Django admin |
| `/audit/` | Audit trail |
| `/ingest/start/` | CSV import |
| `/ingest/ocr/upload/` | OCR upload |
| `/customer/` | Customer portal |
| `/customer/request/new/` | Customer request form |
| `/customer/notifications/` | Customer notifications |

---

## Sample Files

CSV import sample:

```text
sample_data/loss_import_25T1654.csv
```

OCR manual sample text:

```text
sample_data/ocr_sample_text.txt
```

---

## Optional OCR Setup

Install Tesseract.

Ubuntu/Debian:

```bash
sudo apt install tesseract-ocr
```

macOS:

```bash
brew install tesseract
```

Python package:

```bash
pip install pytesseract
```

If Tesseract is unavailable, OCR review still works in manual-assist mode.

---

## Optional PDF Setup

WeasyPrint may require system libraries.

Ubuntu/Debian:

```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi-dev
```

If WeasyPrint is unavailable, report generation falls back to storing HTML content.

---

## Troubleshooting

### No jobs visible

Run:

```bash
python manage.py seed
```

### Customer login has no portal

Run:

```bash
python manage.py setup_customer_profiles
```

### Report file is HTML instead of PDF

Install WeasyPrint and its system dependencies.

### OCR does not extract text

Install Tesseract and pytesseract, or use manual paste mode.

### Database errors after model changes

Run:

```bash
python manage.py makemigrations
python manage.py migrate
```

---

## Deliverable Mapping

| Problem Statement Requirement | Implemented |
|---|---|
| Import customer request information | Customer portal request form |
| Import laboratory log sheets | CSV import + OCR-assisted scan review |
| Store test results in database | Typed Measurement/Result models |
| Organize and manage test-related data | Core relational schema |
| Retrieval of historical records | Searchable dashboard and admin |
| Automatically populate report template | Report engine bound to database |
| Generate PDF/printable reports | WeasyPrint PDF generation |
| Dashboard | Role-based dashboard with status/search/SLA |
| Data validation | Typed fields, enums, unit dictionary, dry-run import |
| Template mapping | Parameter/report template binding |
| Review and export report | Workflow approval + report download |
```

---

# 8. Create architecture document

Create:

