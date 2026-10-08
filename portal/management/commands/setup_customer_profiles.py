from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group

from core.models import Customer

from portal.models import CustomerProfile


class Command(BaseCommand):
    help = 'Create customer portal profiles for seeded users.'

    def handle(self, *args, **options):
        customer = Customer.objects.filter(
            legal_name__icontains='A.P. Transformers'
        ).first()

        if not customer:
            self.stderr.write(
                self.style.ERROR(
                    'Customer not found. Run: python manage.py seed'
                )
            )
            return

        user, created = User.objects.get_or_create(
            username='customer1',
            defaults={
                'email': 'ap@transformers.com',
                'first_name': 'Customer',
                'last_name': 'Representative',
            }
        )

        if created:
            user.set_password('atrg123')
            user.save()

        group, _ = Group.objects.get_or_create(name='Customer')
        user.groups.add(group)

        profile, profile_created = CustomerProfile.objects.get_or_create(
            user=user,
            defaults={
                'customer': customer,
            }
        )

        if profile.customer != customer:
            profile.customer = customer
            profile.save()

        self.stdout.write(
            self.style.SUCCESS(
                f'Customer profile ready: {user.username} → {customer.legal_name}'
            )
        )
