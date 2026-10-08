from django import template
from django.utils import timezone

register = template.Library()


@register.filter(name='has_group')
def has_group(user, groups_csv):
    """
    Usage in template:

        {% load core_extras %}
        {% if request.user|has_group:"Engineer,Admin" %}
            ...
        {% endif %}
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    wanted_groups = [g.strip() for g in groups_csv.split(',') if g.strip()]

    return user.groups.filter(name__in=wanted_groups).exists()


@register.filter(name='days_left')
def days_left(value):
    """
    Returns integer days left until the given datetime/date.

    Negative means overdue.
    """
    if not value:
        return None

    if hasattr(value, 'date'):
        value_date = value.date()
    else:
        value_date = value

    return (value_date - timezone.localdate()).days


@register.filter(name='abs_value')
def abs_value(value):
    """
    Absolute value for template use.
    """
    try:
        return abs(int(value))
    except (TypeError, ValueError):
        return 0


@register.filter(name='is_overdue')
def is_overdue(job):
    """
    Returns True if job is overdue and not closed.
    """
    if not job.promised_at:
        return False

    if job.status in ('LOCKED', 'RELEASED'):
        return False

    return job.promised_at < timezone.now()


@register.filter(name='status_badge_class')
def status_badge_class(status):
    """
    Bootstrap badge color for job status.
    """
    mapping = {
        'REQUESTED': 'secondary',
        'IN_PROGRESS': 'primary',
        'TESTING_DONE': 'info',
        'REPORT_DRAFT': 'info',
        'QUALITY_REVIEW': 'warning',
        'HOD_SIGNED': 'primary',
        'LOCKED': 'dark',
        'RELEASED': 'success',
        'ON_HOLD': 'secondary',
    }

    return mapping.get(status, 'secondary')
