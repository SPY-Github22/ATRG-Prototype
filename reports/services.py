"""
Report Generation Engine.

Jinja/Django HTML template -> WeasyPrint PDF.

For the prototype:
  - report sections are populated from database rows
  - SHA-256 hash is computed
  - report versions are preserved
  - integrity can be re-verified
"""

import hashlib

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone

from core.models import (
    Job,
    Report,
    ReportState,
    Document,
    DocumentType,
    AuditLog,
    AuditAction,
)


def generate_report_pdf(job: Job, generated_by):
    """
    Generate a new report version for a job.
    """
    if job.is_locked:
        raise ValidationError('Job is locked. Cannot regenerate report.')

    existing = Report.objects.filter(job=job).order_by('-version').first()
    version = (existing.version + 1) if existing else 1

    context = build_report_context(job)
    html_content = render_to_string('reports/test_certificate.html', context)

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_content).write_pdf()
        extension = '.pdf'
    except ImportError:
        # Fallback for machines where WeasyPrint system dependencies are missing.
        # The report is still generated and stored, but as HTML content.
        pdf_bytes = html_content.encode('utf-8')
        extension = '.html'

    sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    doc_type, _ = DocumentType.objects.get_or_create(
        code='REPORT',
        defaults={'name': 'Test Report'},
    )

    document = Document.objects.create(
        job=job,
        doc_type=doc_type,
        form_no='TC',
        revision=str(version),
        uploaded_by=generated_by,
    )

    filename = f'{job.test_series_no}_report_v{version}{extension}'
    document.file.save(filename, ContentFile(pdf_bytes), save=True)

    report = Report.objects.create(
        job=job,
        version=version,
        state=ReportState.DRAFT,
        pdf=document,
        sha256=sha256,
        generated_by=generated_by,
    )

    AuditLog.objects.create(
        actor=generated_by,
        entity='Report',
        entity_id=report.pk,
        action=AuditAction.CREATE,
        field='version',
        old_value='',
        new_value=str(version),
    )

    return report


def verify_report_integrity(report: Report) -> bool:
    """
    Re-hash stored report file and compare with stored SHA-256.
    """
    if not report.pdf or not report.sha256:
        return False

    try:
        with report.pdf.file.open('rb') as fh:
            content = fh.read()
    except Exception:
        return False

    computed = hashlib.sha256(content).hexdigest()
    return computed == report.sha256


def build_report_context(job: Job):
    """
    Assemble data for the report template.
    """
    sample = getattr(job, 'sample', None)

    tests = job.tests.select_related('test_type').prefetch_related(
        'measurements__parameter'
    ).order_by('test_type__code')

    results = job.results.select_related(
        'rule',
        'rule__parameter',
    ).order_by('rule__code')

    report = job.reports.order_by('-version').first()

    return {
        'job': job,
        'sample': sample,
        'customer': job.customer,
        'tests': tests,
        'results': results,
        'report': report,
        'generated_at': timezone.now(),
        'report_no': f'{job.test_series_no}/TC',
    }
