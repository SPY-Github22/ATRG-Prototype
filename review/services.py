"""
Workflow state machine.

One service function `transition()` owns every state change.
It checks:
  - valid current status + action
  - user role
  - report existence where needed
  - lock protection

It writes:
  - Job status update
  - Approval row
  - AuditLog row

Once LOCKED, no engineer/quality/admin can silently modify data.
"""

from django.db import transaction
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from core.models import (
    Job,
    JobStatus,
    Report,
    ReportState,
    Approval,
    ApprovalStep,
    AuditLog,
    AuditAction,
)


# ─── Valid state transitions ─────────────────────────────────────────────────

TRANSITIONS = {
    (JobStatus.REQUESTED, 'start'): JobStatus.IN_PROGRESS,

    (JobStatus.IN_PROGRESS, 'testing_done'): JobStatus.TESTING_DONE,
    (JobStatus.IN_PROGRESS, 'draft_report'): JobStatus.REPORT_DRAFT,

    (JobStatus.TESTING_DONE, 'draft_report'): JobStatus.REPORT_DRAFT,

    (JobStatus.REPORT_DRAFT, 'submit'): JobStatus.QUALITY_REVIEW,

    (JobStatus.QUALITY_REVIEW, 'quality_verify'): JobStatus.HOD_SIGNED,
    (JobStatus.QUALITY_REVIEW, 'reject'): JobStatus.REPORT_DRAFT,

    (JobStatus.HOD_SIGNED, 'hod_sign'): JobStatus.LOCKED,

    (JobStatus.LOCKED, 'release'): JobStatus.RELEASED,

    (JobStatus.IN_PROGRESS, 'hold'): JobStatus.ON_HOLD,
    (JobStatus.ON_HOLD, 'resume'): JobStatus.IN_PROGRESS,
}


# ─── Role permissions for actions ────────────────────────────────────────────

ACTION_ROLES = {
    'start': ['Engineer', 'Admin'],
    'testing_done': ['Engineer', 'Admin'],
    'draft_report': ['Engineer', 'Admin'],

    'submit': ['Engineer', 'Admin'],

    'quality_verify': ['Quality', 'Admin'],
    'reject': ['Quality', 'Admin'],

    'hod_sign': ['HOD', 'Admin'],
    'release': ['HOD', 'Admin'],

    'hold': ['Engineer', 'Quality', 'HOD', 'Admin'],
    'resume': ['Engineer', 'Quality', 'HOD', 'Admin'],
}


ACTION_LABELS = {
    'start': 'Start Job',
    'testing_done': 'Mark Testing Done',
    'draft_report': 'Create Report Draft',
    'submit': 'Submit for Quality Review',
    'quality_verify': 'Quality Approve',
    'reject': 'Reject to Draft',
    'hod_sign': 'HOD Sign & Lock',
    'release': 'Release to Customer',
    'hold': 'Put On Hold',
    'resume': 'Resume Job',
}


ACTION_ORDER = [
    'start',
    'testing_done',
    'draft_report',
    'submit',
    'quality_verify',
    'reject',
    'hod_sign',
    'release',
    'hold',
    'resume',
]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_user_roles(user):
    """Return role names for a user."""
    if not user or not user.is_authenticated:
        return []

    if user.is_superuser:
        return ['Admin']

    return list(user.groups.values_list('name', flat=True))


def can_transition(user, action):
    """Check whether user's roles permit this workflow action."""
    roles = get_user_roles(user)
    required_roles = ACTION_ROLES.get(action, [])
    return any(role in required_roles for role in roles)


def get_available_actions(user, job):
    """
    Return workflow actions available to this user for this job.
    """
    actions = []

    for (status, action), next_status in TRANSITIONS.items():
        if status == job.status and can_transition(user, action):
            actions.append(
                {
                    'action': action,
                    'next_status': next_status,
                    'label': ACTION_LABELS.get(action, action.replace('_', ' ').title()),
                }
            )

    actions.sort(
        key=lambda item: ACTION_ORDER.index(item['action'])
        if item['action'] in ACTION_ORDER
        else 99
    )

    return actions


def guard_locked_write(job):
    """
    Call before any write to Job/Sample/Measurement/Result.

    Once locked/released, no modification is permitted.
    """
    if job.is_locked:
        raise ValidationError(
            f'Job {job.test_series_no} is LOCKED/RELEASED. '
            f'No modifications are permitted.'
        )


# ─── Main transition service ─────────────────────────────────────────────────

@transaction.atomic
def transition(actor, job, action, comment=''):
    """
    The only permitted way to change job/report workflow state.
    """
    # Terminal protection
    if job.status == JobStatus.RELEASED:
        raise ValidationError('Job is RELEASED. This is a terminal state.')

    if job.status == JobStatus.LOCKED and action != 'release':
        raise ValidationError('Job is LOCKED. Only release is permitted.')

    # Valid transition?
    key = (job.status, action)

    if key not in TRANSITIONS:
        raise ValidationError(
            f'Invalid transition: cannot perform "{action}" from status "{job.status}".'
        )

    # Role allowed?
    if not can_transition(actor, action):
        raise PermissionDenied(
            f'User "{actor.username}" does not have permission for action "{action}".'
        )

    report = job.reports.order_by('-version').first()

    # Some actions require a report
    if action in ('submit', 'quality_verify', 'hod_sign', 'reject') and not report:
        raise ValidationError('Generate a report before performing this action.')

    old_status = job.status
    new_status = TRANSITIONS[key]

    job.status = new_status

    if new_status == JobStatus.LOCKED:
        job.locked_at = timezone.now()

    job.save()

    # Audit trail
    AuditLog.objects.create(
        actor=actor,
        entity='Job',
        entity_id=job.pk,
        action=AuditAction.TRANSITION,
        field='status',
        old_value=str(old_status),
        new_value=str(new_status),
    )

    # Report approval/state updates
    if report:
        step_map = {
            'submit': ApprovalStep.SUBMIT,
            'quality_verify': ApprovalStep.QUALITY_VERIFY,
            'hod_sign': ApprovalStep.HOD_SIGN,
            'reject': ApprovalStep.REJECT,
        }

        if action in step_map:
            Approval.objects.create(
                report=report,
                step=step_map[action],
                actor=actor,
                comment=comment,
            )

            state_map = {
                'submit': ReportState.SUBMITTED,
                'quality_verify': ReportState.QUALITY_OK,
                'hod_sign': ReportState.LOCKED,
                'reject': ReportState.DRAFT,
            }

            report.state = state_map[action]
            report.save()

        elif action == 'release':
            report.state = ReportState.RELEASED
            report.save()

    return job
