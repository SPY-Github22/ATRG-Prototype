"""
Portal services.

Contains:
  - customer ownership helpers
  - customer notifications
  - job progress summary
  - dashboard task helpers
"""

from django.utils import timezone

from core.models import (
    Notification,
    NotificationKind,
    Job,
    JobStatus,
)

from review.services import get_user_roles


# ─── Customer ownership ──────────────────────────────────────────────────────

def get_customer_for_user(user):
    """
    Return the Customer entity linked to this login user, if any.
    """
    if not user or not user.is_authenticated:
        return None

    profile = getattr(user, 'customer_profile', None)

    if not profile:
        return None

    return profile.customer


# ─── Notifications ───────────────────────────────────────────────────────────

def create_notification(customer, job, message, kind=NotificationKind.STATUS):
    """
    Create a customer notification.
    """
    return Notification.objects.create(
        customer=customer,
        job=job,
        message=message,
        kind=kind,
    )


def notify_all_tests_complete(job):
    """
    Notify customer when all tests are marked complete.
    Avoids duplicate notifications using exact message match.
    """
    message = f'All tests for {job.test_series_no} are complete.'

    exists = Notification.objects.filter(
        customer=job.customer,
        job=job,
        kind=NotificationKind.STATUS,
        message=message,
    ).exists()

    if not exists:
        create_notification(
            customer=job.customer,
            job=job,
            message=message,
            kind=NotificationKind.STATUS,
        )


def notify_transition(job, action):
    """
    Create customer notifications for selected workflow actions.
    """
    if action == 'testing_done':
        notify_all_tests_complete(job)

    elif action == 'release':
        create_notification(
            customer=job.customer,
            job=job,
            message=(
                f'Test report for {job.test_series_no} has been released '
                f'and is available for download.'
            ),
            kind=NotificationKind.REPORT_READY,
        )


# ─── Customer progress ───────────────────────────────────────────────────────

def progress_summary(job):
    """
    Customer-facing progress summary.

    Example:
        3 of 5 tests complete · 1 in progress
    """
    tests = job.tests.all()

    total = tests.count()
    completed = tests.filter(completed_at__isnull=False).count()

    in_progress_qs = tests.filter(
        started_at__isnull=False,
        completed_at__isnull=True,
    ).order_by('started_at')

    in_progress = in_progress_qs.count()
    current_test = in_progress_qs.first()

    percent = int((completed / total) * 100) if total else 0

    return {
        'total': total,
        'completed': completed,
        'in_progress': in_progress,
        'current_test': current_test,
        'percent': percent,
    }


# ─── Dashboard task panel ────────────────────────────────────────────────────

def my_tasks(user):
    """
    Role-based task panel for the internal dashboard.
    """
    roles = get_user_roles(user)
    tasks = []

    now = timezone.now()

    if any(role in ('Engineer', 'Admin') for role in roles):
        active_count = Job.objects.filter(
            status__in=[
                JobStatus.IN_PROGRESS,
                JobStatus.TESTING_DONE,
                JobStatus.REPORT_DRAFT,
            ]
        ).count()

        tasks.append({
            'label': 'Active engineering jobs',
            'count': active_count,
            'url': '/?status=IN_PROGRESS',
            'color': 'primary',
        })

    if any(role in ('Quality', 'Admin') for role in roles):
        quality_count = Job.objects.filter(
            status=JobStatus.QUALITY_REVIEW
        ).count()

        tasks.append({
            'label': 'Awaiting quality review',
            'count': quality_count,
            'url': '/?status=QUALITY_REVIEW',
            'color': 'warning',
        })

    if any(role in ('HOD', 'Admin') for role in roles):
        hod_count = Job.objects.filter(
            status=JobStatus.HOD_SIGNED
        ).count()

        tasks.append({
            'label': 'Awaiting HOD signature',
            'count': hod_count,
            'url': '/?status=HOD_SIGNED',
            'color': 'dark',
        })

    if any(role in ('Admin', 'Quality', 'HOD') for role in roles):
        overdue_count = Job.objects.filter(
            promised_at__lt=now
        ).exclude(
            status__in=[
                JobStatus.LOCKED,
                JobStatus.RELEASED,
            ]
        ).count()

        tasks.append({
            'label': 'Overdue jobs',
            'count': overdue_count,
            'url': '/?overdue=1',
            'color': 'danger',
        })

    return tasks
