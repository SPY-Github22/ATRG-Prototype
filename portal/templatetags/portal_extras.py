from django import template

from core.models import Notification

from portal.services import get_customer_for_user

register = template.Library()


@register.filter(name='unread_notification_count')
def unread_notification_count(user):
    """
    Usage:

        {% load portal_extras %}
        {{ request.user|unread_notification_count }}
    """
    customer = get_customer_for_user(user)

    if not customer:
        return 0

    return Notification.objects.filter(
        customer=customer,
        read_at__isnull=True,
    ).count()
