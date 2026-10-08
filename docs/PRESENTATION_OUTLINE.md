# ATRG Technical Presentation Outline

## Slide 1 — Problem

CPRI SCL generates around 2,000 test reports per year.

Current pain:

- paper logsheets
- repeated re-entry
- calculation outside main data flow
- manual report preparation
- delays beyond 10-day promise
- legal risk from small errors

One-line problem:

> CPRI needs one controlled, auditable digital workflow that collects job data, prevents transcription errors, generates the report automatically, and enforces Engineer → Quality → HOD locking.

---

## Slide 2 — Solution

A web-based LIMS-style prototype.

Core flow:

```text
Customer request
→ Engineer data entry / import / OCR
→ Validation and auto-verdicts
→ PDF report generation
→ Quality approval
→ HOD signature and lock
→ Customer release
```

Key idea:

> One source of truth for every fact.

---

## Slide 3 — Architecture

Modules:

- `core`: typed schema
- `ingest`: CSV and OCR import
- `testing`: validation and rules engine
- `review`: workflow and RBAC
- `reports`: PDF generation and integrity
- `portal`: dashboards and customer portal

Stack:

- Django
- SQLite
- Bootstrap
- WeasyPrint
- optional pytesseract

---

## Slide 4 — Data Integrity

Features:

- customer dropdown, not free text
- customer alias canonicalization
- typed measurement values
- unit dictionary
- Decimal precision
- source tracking:
  - MANUAL
  - IMPORT
  - OCR
- raw text preservation
- confidence for OCR
- append-only audit log

---

## Slide 5 — Workflow and Locking

States:

```text
REQUESTED
IN_PROGRESS
TESTING_DONE
REPORT_DRAFT
QUALITY_REVIEW
HOD_SIGNED
LOCKED
RELEASED
```

Locking:

- after HOD sign, edits are blocked
- report hash displayed
- integrity verification available
- all transitions audited

---

## Slide 6 — Customer Experience

Customer portal:

- submit request
- live progress
- notification bell
- released report download

Rights boundary:

- customer cannot see raw readings
- customer cannot see draft report
- customer can download only released report

---

## Slide 7 — AI Touches

AI is used carefully and transparently:

1. OCR-assisted ingestion with human confirmation
2. deterministic auto-verdicts with clause traceability
3. BT/AT anomaly flags for Quality review

Core principle:

> AI assists. Engineer confirms. System audits.

---

## Slide 8 — Results

Demonstrated:

- sample job 25T1654 seeded
- routine and loss data captured
- CSV import working
- OCR-assisted queue working
- PASS/FAIL computed against IS 1180 limits
- PDF generated
- approval chain enforced
- lock prevents edits
- customer notified and able to download released report

---

## Slide 9 — Roadmap

Future scope:

- real CPRI certificate template
- direct instrument integration
- more equipment types
- real DSC/PAdES signatures
- SMTP/SMS notifications
- PostgreSQL deployment
- advanced OCR layout parsing
- CPRI LIMS integration
```

---

# 11. Run updated system

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py seed
python manage.py setup_customer_profiles
python manage.py demo_check
python manage.py runserver
```

---

# 12. What is now complete

| Area | Status |
|---|---|
| Core schema | Done |
| RBAC | Done |
| Workflow | Done |
| Locking | Done |
| Audit trail | Done |
| Engineer data entry | Done |
| Rules engine | Done |
| Auto-verdicts | Done |
| Report generation | Done |
| SHA-256 integrity | Done |
| CSV import | Done |
| OCR queue | Done |
| Customer portal | Done |
| Notifications | Done |
| Dashboard SLA | Done |
| Overdue highlighting | Done |
| My tasks panel | Done |
| Filters/search | Done |
| Demo check | Done |
| README | Done |
| Architecture doc | Done |
| Demo script | Done |
| Presentation outline | Done |

---

# 13. Remaining useful enhancements

The strongest remaining technical enhancement is:

## Remaining test-type data entry templates

Currently, generic measurement entry supports all seeded test types:

```text
ROUTINE
LOSS
SC
TEMP
OIL
```

But the UI is strongest for:

```text
Routine
Loss
