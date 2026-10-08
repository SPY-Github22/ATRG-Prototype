from django.db import models
from django.contrib.auth.models import User

from core.models import Job, Test


class ImportBatch(models.Model):
    """
    Tracks one CSV import session.

    Flow:
        PENDING -> MAPPED -> VALIDATED -> COMMITTED
    """

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        MAPPED = 'MAPPED', 'Column Mapping Done'
        VALIDATED = 'VALIDATED', 'Dry-run Passed'
        COMMITTED = 'COMMITTED', 'Committed'
        FAILED = 'FAILED', 'Failed'

    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name='import_batches',
    )

    test = models.ForeignKey(
        Test,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='import_batches',
    )

    file = models.FileField(
        upload_to='imports/',
        null=True,
        blank=True,
    )

    filename = models.CharField(max_length=255)

    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='import_batches_uploaded',
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    mapping_json = models.JSONField(default=dict, blank=True)
    header_json = models.JSONField(default=list, blank=True)
    preview_json = models.JSONField(default=list, blank=True)

    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)

    error_log = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name_plural = 'Import batches'

    def __str__(self):
        return f'Import {self.filename} → {self.job.test_series_no}'


class OCRQueueItem(models.Model):
    """
    Scan -> OCR -> human-confirm queue.

    AI Touch #1 from the solution plan.

    The engineer remains responsible for confirming every value.
    OCR only assists.
    """

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending OCR'
        EXTRACTED = 'EXTRACTED', 'Extracted — Needs Review'
        CONFIRMED = 'CONFIRMED', 'Confirmed by Engineer'
        REJECTED = 'REJECTED', 'Rejected'

    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name='ocr_items',
    )

    test = models.ForeignKey(
        Test,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ocr_items',
    )

    image = models.ImageField(
        upload_to='ocr_uploads/',
        null=True,
        blank=True,
    )

    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ocr_items_uploaded',
    )

    extracted_text = models.TextField(blank=True, default='')
    confidence = models.FloatField(null=True, blank=True)

    proposal_json = models.JSONField(
        default=list,
        blank=True,
        help_text='Proposed measurement rows extracted from OCR text.',
    )

    error_log = models.TextField(blank=True, default='')

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ocr_items_reviewed',
    )

    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'OCR #{self.pk} — {self.job.test_series_no} [{self.status}]'
