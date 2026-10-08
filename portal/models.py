from django.db import models
from django.contrib.auth.models import User

from core.models import Customer


class CustomerProfile(models.Model):
    """
    Links a Django login user to a Customer entity.

    This enables:
      - customer ownership of jobs
      - customer-only notifications
      - customer-only released report download
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='customer_profile',
    )

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='portal_profiles',
    )

    is_primary = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Customer Portal Profile'
        verbose_name_plural = 'Customer Portal Profiles'

    def __str__(self):
        return f'{self.user.username} → {self.customer.legal_name}'
