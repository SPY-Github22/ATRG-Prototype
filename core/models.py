"""
Core data model — designed directly from job 25T1654.
Naming follows CPRI forms so the lab recognises their own world.
Every entity uses strict types: Decimal(12,4) for measurements,
Enum for states, FK for relations (never free text).
"""
from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


# ─── Enums ───────────────────────────────────────────────────────────────────

class RequestType(models.TextChoices):
    TYPE = 'TYPE', 'Type Test'
    ROUTINE = 'ROUTINE', 'Routine Test'
    SPECIAL = 'SPECIAL', 'Special Test'


class JobStatus(models.TextChoices):
    REQUESTED = 'REQUESTED', 'Requested'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    TESTING_DONE = 'TESTING_DONE', 'Testing Done'
    REPORT_DRAFT = 'REPORT_DRAFT', 'Report Draft'
    QUALITY_REVIEW = 'QUALITY_REVIEW', 'Quality Review'
    HOD_SIGNED = 'HOD_SIGNED', 'HOD Signed'
    LOCKED = 'LOCKED', 'Locked'
    RELEASED = 'RELEASED', 'Released'
    ON_HOLD = 'ON_HOLD', 'On Hold'


class EquipmentType(models.TextChoices):
    TRANSFORMER = 'TRANSFORMER', 'Transformer'
    SWITCHGEAR = 'SWITCHGEAR', 'Switchgear'
    CABLE = 'CABLE', 'Cable'
    INSULATOR = 'INSULATOR', 'Insulator'
    OTHER = 'OTHER', 'Other'


class MeasurementStage(models.TextChoices):
    BT = 'BT', 'Before Test'
    AT = 'AT', 'After Test'


class Phase(models.TextChoices):
    R = 'R', 'R Phase'
    Y = 'Y', 'Y Phase'
    B = 'B', 'B Phase'


class MeasurementSource(models.TextChoices):
    MANUAL = 'MANUAL', 'Manual Entry'
    IMPORT = 'IMPORT', 'CSV/Excel Import'
    OCR = 'OCR', 'OCR Scan'


class Comparator(models.TextChoices):
    LE = 'LE', '≤ (less than or equal)'
    LT = 'LT', '< (less than)'
    GE = 'GE', '≥ (greater than or equal)'
    GT = 'GT', '> (greater than)'
    WITHIN = 'WITHIN', 'Within range'


class Verdict(models.TextChoices):
    PASS = 'PASS', 'Pass'
    FAIL = 'FAIL', 'Fail'
    NA = 'NA', 'Not Applicable'


class ReportState(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    QUALITY_OK = 'QUALITY_OK', 'Quality Verified'
    SIGNED = 'SIGNED', 'HOD Signed'
    LOCKED = 'LOCKED', 'Locked'
    RELEASED = 'RELEASED', 'Released'


class ApprovalStep(models.TextChoices):
    SUBMIT = 'SUBMIT', 'Submit'
    QUALITY_VERIFY = 'QUALITY_VERIFY', 'Quality Verify'
    HOD_SIGN = 'HOD_SIGN', 'HOD Sign'
    REJECT = 'REJECT', 'Reject'


class AuditAction(models.TextChoices):
    CREATE = 'CREATE', 'Create'
    UPDATE = 'UPDATE', 'Update'
    DELETE = 'DELETE', 'Delete'
    TRANSITION = 'TRANSITION', 'State Transition'


class NotificationKind(models.TextChoices):
    STATUS = 'STATUS', 'Status Update'
    REPORT_READY = 'REPORT_READY', 'Report Ready'
    ACTION_REQUIRED = 'ACTION_REQUIRED', 'Action Required'


# ─── Customer & Aliases ─────────────────────────────────────────────────────

class Customer(models.Model):
    """One canonical row per customer entity. FK everywhere, never free text."""
    legal_name = models.CharField(max_length=255, unique=True)
    address = models.TextField(blank=True, default='')
    contact_person = models.CharField(max_length=255, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['legal_name']

    def __str__(self):
        return self.legal_name


class CustomerAlias(models.Model):
    """Canonicalises the 5+ spelling variants seen in scans → one Customer row."""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='aliases')
    alias = models.CharField(max_length=255, unique=True)

    class Meta:
        verbose_name_plural = 'Customer aliases'

    def __str__(self):
        return f'{self.alias} → {self.customer.legal_name}'


# ─── Job (the single source of truth per test series) ───────────────────────

class Job(models.Model):
    """One entity per test series. test_series_no is THE identifier."""
    test_series_no = models.CharField(
        max_length=50, unique=True,
        help_text='e.g. CPRIBLRSCL25T1654 or short form 25T1654'
    )
    file_no = models.CharField(max_length=100, blank=True, default='')
    request_type = models.CharField(max_length=10, choices=RequestType.choices, default=RequestType.TYPE)
    standard = models.CharField(max_length=100, blank=True, default='', help_text='e.g. IS 1180')
    eel_level = models.CharField(max_length=20, blank=True, default='', help_text='e.g. EEL-1')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='jobs')
    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.REQUESTED)
    received_at = models.DateTimeField(default=timezone.now)
    promised_at = models.DateTimeField(null=True, blank=True, help_text='received_at + 10 days SLA')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_jobs')
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-received_at']

    def __str__(self):
        return f'{self.test_series_no} ({self.customer.legal_name})'

    @property
    def is_locked(self):
        return self.status in (JobStatus.LOCKED, JobStatus.RELEASED)

    def save(self, *args, **kwargs):
        # Auto-compute SLA if not set
        if self.promised_at is None and self.received_at:
            from datetime import timedelta
            self.promised_at = self.received_at + timedelta(days=10)
        super().save(*args, **kwargs)


# ─── Sample (equipment under test) ──────────────────────────────────────────

class Sample(models.Model):
    """One sample per job. Fields mirror the Proforma (Sec 12)."""
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name='sample')
    sample_code = models.CharField(max_length=50, unique=True, help_text='e.g. HVD25S0847')
    equipment_type = models.CharField(max_length=20, choices=EquipmentType.choices, default=EquipmentType.TRANSFORMER)
    serial_no = models.CharField(max_length=100, blank=True, default='')
    rating_kva = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    vector_group = models.CharField(max_length=20, blank=True, default='', help_text='e.g. Dyn11')
    hv_v = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='HV voltage (V)')
    lv_v = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='LV voltage (V)')
    frequency_hz = models.DecimalField(max_digits=6, decimal_places=1, default=50.0)
    cooling = models.CharField(max_length=20, blank=True, default='', help_text='e.g. ONAN')
    oil_volume_l = models.DecimalField(max_digits=8, decimal_places=1, null=True, blank=True)
    bil_hv_kv = models.DecimalField(max_digits=8, decimal_places=1, null=True, blank=True)
    bil_lv_kv = models.DecimalField(max_digits=8, decimal_places=1, null=True, blank=True)
    tap_min_pct = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    tap_max_pct = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    tap_steps = models.IntegerField(null=True, blank=True)
    manufacturer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='manufactured_samples'
    )
    manufactured_on = models.DateField(null=True, blank=True)
    specs_json = models.JSONField(default=dict, blank=True, help_text='Additional structured data')

    class Meta:
        ordering = ['sample_code']

    def __str__(self):
        return f'{self.sample_code} — {self.rating_kva} kVA {self.equipment_type}'


# ─── Test Types (dictionary of CPRI forms) ──────────────────────────────────

class TestType(models.Model):
    """Dictionary row: ROUTINE/Sec45, SC/Sec55, LOSS/Sec56, TEMP/Sec44, etc."""
    code = models.CharField(max_length=30, unique=True, help_text='e.g. ROUTINE, SC, LOSS, TEMP, OIL')
    name = models.CharField(max_length=100, help_text='e.g. Routine Tests')
    section_no = models.CharField(max_length=20, blank=True, default='', help_text='e.g. Sec 45')
    form_no = models.CharField(max_length=50, blank=True, default='', help_text='e.g. CPRI/QAF/02')

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} — {self.name} ({self.section_no})'


# ─── Test (an instance of a TestType performed on a Job) ────────────────────

class Test(models.Model):
    """One test execution within a job, in a specific bay."""
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='tests')
    test_type = models.ForeignKey(TestType, on_delete=models.PROTECT, related_name='tests')
    bay = models.CharField(max_length=50, blank=True, default='')
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='performed_tests')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['job', 'test_type']
        unique_together = ['job', 'test_type']

    def __str__(self):
        return f'{self.job.test_series_no} / {self.test_type.code}'


# ─── Parameter (dictionary of measurable quantities) ────────────────────────

class Parameter(models.Model):
    """Dictionary: NLL_W, LLC_W75, R_HV_OHM, I_NL_A, ISC_KA, TOP_OIL_C, RATIO_ERR_PCT…"""
    code = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=200)
    unit = models.CharField(max_length=20, blank=True, default='')
    data_type = models.CharField(max_length=20, default='DECIMAL', help_text='DECIMAL, INTEGER, TEXT, BOOLEAN')
    min_val = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    max_val = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    test_type = models.ForeignKey(TestType, on_delete=models.CASCADE, related_name='parameters', null=True, blank=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} ({self.unit})'


# ─── Measurement (the atomic reading) ───────────────────────────────────────

class Measurement(models.Model):
    """One reading. BT/AT stage, tap position, phase — all typed, never free text."""
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='measurements')
    parameter = models.ForeignKey(Parameter, on_delete=models.PROTECT, related_name='measurements')
    stage = models.CharField(max_length=2, choices=MeasurementStage.choices, default=MeasurementStage.BT)
    tap_position = models.IntegerField(null=True, blank=True)
    phase = models.CharField(max_length=1, choices=Phase.choices, null=True, blank=True)
    value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    unit = models.CharField(max_length=20, blank=True, default='')
    raw_text = models.TextField(null=True, blank=True, help_text='Original text if OCR/import')
    source = models.CharField(max_length=10, choices=MeasurementSource.choices, default=MeasurementSource.MANUAL)
    confidence = models.FloatField(null=True, blank=True, help_text='OCR confidence 0-1')
    captured_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['test', 'parameter', 'stage', 'tap_position', 'phase']

    def __str__(self):
        loc = f' tap={self.tap_position}' if self.tap_position else ''
        ph = f' ph={self.phase}' if self.phase else ''
        return f'{self.parameter.code} [{self.stage}]{loc}{ph} = {self.value} {self.unit}'


# ─── Limit Rules (standard clauses encoded) ─────────────────────────────────

class LimitRule(models.Model):
    """Encodes IS 1180 / IEC limits: e.g. total loss ≤ 980W @50%, ≤ 2930W @100%."""
    code = models.CharField(max_length=50, unique=True)
    standard = models.CharField(max_length=50, help_text='e.g. IS 1180')
    clause = models.CharField(max_length=100, blank=True, default='')
    parameter = models.ForeignKey(Parameter, on_delete=models.CASCADE, related_name='limit_rules')
    applies_when = models.CharField(max_length=200, blank=True, default='', help_text='e.g. EEL-1, 250 kVA')
    limit_value = models.DecimalField(max_digits=12, decimal_places=4)
    comparator = models.CharField(max_length=6, choices=Comparator.choices, default=Comparator.LE)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code}: {self.parameter.code} {self.get_comparator_display()} {self.limit_value}'


# ─── Result (snapshot of rule evaluation) ────────────────────────────────────

class Result(models.Model):
    """Snapshot: recomputed on data change. PASS/FAIL with clause traceability."""
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='results')
    rule = models.ForeignKey(LimitRule, on_delete=models.CASCADE, related_name='results')
    measured = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    limit = models.DecimalField(max_digits=12, decimal_places=4)
    verdict = models.CharField(max_length=4, choices=Verdict.choices)
    evaluated_at = models.DateTimeField(auto_now=True)
    note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['job', 'rule']

    def __str__(self):
        return f'{self.rule.code}: {self.measured} → {self.verdict}'


# ─── Documents ──────────────────────────────────────────────────────────────

class DocumentType(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Document(models.Model):
    """Uploaded files: scans, generated PDFs, etc."""
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT)
    form_no = models.CharField(max_length=50, blank=True, default='')
    revision = models.CharField(max_length=20, blank=True, default='')
    file = models.FileField(upload_to='documents/')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.doc_type.code} — {self.job.test_series_no}'


# ─── Report ─────────────────────────────────────────────────────────────────

class Report(models.Model):
    """The generated test report. Immutable once LOCKED."""
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='reports')
    version = models.PositiveIntegerField(default=1)
    state = models.CharField(max_length=20, choices=ReportState.choices, default=ReportState.DRAFT)
    generated_at = models.DateTimeField(auto_now_add=True)
    pdf = models.ForeignKey(Document, on_delete=models.SET_NULL, null=True, blank=True, related_name='report_refs')
    sha256 = models.CharField(max_length=64, blank=True, default='')
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-version']
        unique_together = ['job', 'version']

    def __str__(self):
        return f'Report v{self.version} — {self.job.test_series_no} [{self.state}]'


# ─── Approvals ──────────────────────────────────────────────────────────────

class Approval(models.Model):
    """Each step in the Engineer → Quality → HOD chain."""
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='approvals')
    step = models.CharField(max_length=20, choices=ApprovalStep.choices)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['at']

    def __str__(self):
        return f'{self.step} by {self.actor} on {self.report}'


# ─── Audit Log (append-only — no UPDATE/DELETE grants) ──────────────────────

class AuditLog(models.Model):
    """Append-only trail: who/what/when/from→to. Exactly as the Joint Director asked."""
    at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    entity = models.CharField(max_length=100, help_text='Model name e.g. Measurement')
    entity_id = models.PositiveIntegerField()
    action = models.CharField(max_length=10, choices=AuditAction.choices)
    field = models.CharField(max_length=100, blank=True, default='')
    old_value = models.TextField(blank=True, default='')
    new_value = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-at']
        # Append-only: in production, revoke UPDATE/DELETE on this table

    def __str__(self):
        return f'[{self.action}] {self.entity}#{self.entity_id} by {self.actor}'


# ─── Notifications ──────────────────────────────────────────────────────────

class Notification(models.Model):
    """Customer-facing notifications: progress, report ready, etc."""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='notifications')
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    message = models.TextField()
    kind = models.CharField(max_length=20, choices=NotificationKind.choices, default=NotificationKind.STATUS)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.kind}: {self.message[:50]}'
