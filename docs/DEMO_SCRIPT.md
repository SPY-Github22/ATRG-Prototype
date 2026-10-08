# ATRG Demo Script — 5 Minutes

## Demo Goal

Show one job moving from customer request to released report with:

- typed data entry
- CSV import
- OCR-assisted entry
- automatic PASS/FAIL
- approval chain
- locking
- audit trail
- customer notification

---

## Pre-Demo Checks

Run:

```bash
python manage.py demo_check
python manage.py runserver
```

Open browser tabs:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/admin/
```

Keep these users ready:

```text
customer1 / atrg123
engineer1 / atrg123
quality1  / atrg123
hod1      / atrg123
```

---

## 0:00–0:45 — Customer submits request

Login:

```text
customer1 / atrg123
```

Click:

```text
New Test Request
```

Fill:

```text
Request Type: Type Test
Equipment: Transformer
Standard: IS 1180
EEL: EEL-1
Rating: 250
HV: 11000
LV: 433
Frequency: 50
Vector Group: Dyn11
Serial: 1098
```

Submit.

Say:

> The customer request enters the lab workflow directly. No re-typing by lab staff.

---

## 0:45–2:00 — Engineer enters routine data

Logout.

Login:

```text
engineer1 / atrg123
```

Open dashboard.

Open:

```text
CPRIBLRSCL25T1654
```

Open Routine Test.

Show:

- dropdown parameters
- units enforced
- BT/AT stage
- tap position
- phase
- ratio grid

Enter one invalid value and show validation.

Then enter valid values.

Say:

> Data is typed once, validated immediately, and stored with user, timestamp, and source.

---

## 2:00–2:45 — CSV import and auto-verdicts

Go to:

```text
Import CSV
```

Select:

```text
CPRIBLRSCL25T1654 / Loss Measurement
```

Upload:

```text
sample_data/loss_import_25T1654.csv
```

Show mapping.

Show dry-run preview.

Commit.

Return to job detail.

Show auto-verdicts:

```text
No-load loss PASS
Total loss PASS
```

Say:

> The rules engine checks values against IS 1180 EEL-1 limits and cites the clause.

---

## 2:45–4:15 — Report, approval, lock

Click:

```text
Generate Draft Report
```

Click:

```text
Submit for Quality Review
```

Logout.

Login:

```text
quality1 / atrg123
```

Open job.

Click:

```text
Quality Approve
```

Logout.

Login:

```text
hod1 / atrg123
```

Click:

```text
HOD Sign & Lock
```

Show:

```text
Job locked
SHA-256 displayed
```

Then login as engineer and try to edit.

Show error:

```text
Job is locked. Measurements cannot be modified.
```

Say:

> After HOD sign, nobody can silently modify the data. Every attempt is controlled and auditable.

---

## 4:15–5:00 — Customer notification and download

Login:

```text
hod1 / atrg123
```

Click:

```text
Release to Customer
```

Logout.

Login:

```text
customer1 / atrg123
```

Show notification:

```text
Report released and available for download.
```

Download report.

Say:

> The customer sees only what they are allowed to see: progress, notifications, and released report.

---

## Backup Topics

If asked about AI:

- show OCR queue
- show confidence field
- show raw OCR text
- show human confirmation

If asked about corrections:

- open audit trail
- filter by `Measurement`
- show old value/new value

If asked about report authenticity:

- click verify integrity
- show SHA-256 match
```

---

# 10. Create presentation outline

Create:

