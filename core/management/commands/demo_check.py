from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.db import OperationalError

from core.models import (
    Customer,
    CustomerAlias,
    Job,
    Measurement,
    Result,
    Report,
)


class Command(BaseCommand):
    help = 'Checks whether the demo environment is ready.'

    def handle(self, *args, **options):
        errors = []
        warnings = []
        ok = []

        try:
            # Groups
            required_groups = [
                'Customer',
                'Engineer',
                'Quality',
                'HOD',
                'Admin',
            ]

            for group_name in required_groups:
                if Group.objects.filter(name=group_name).exists():
                    ok.append(f'Group exists: {group_name}')
                else:
                    errors.append(f'Missing group: {group_name}')

            # Users
            required_users = [
                'admin',
                'engineer1',
                'engineer2',
                'quality1',
                'hod1',
                'customer1',
            ]

            for username in required_users:
                if User.objects.filter(username=username).exists():
                    ok.append(f'User exists: {username}')
                else:
                    errors.append(f'Missing user: {username}')

            # Customer
            customer = Customer.objects.filter(
                legal_name__icontains='A.P. Transformers'
            ).first()

            if customer:
                ok.append(f'Customer exists: {customer.legal_name}')
            else:
                errors.append('Missing customer: A.P. Transformers')

            # Customer aliases
            alias_count = CustomerAlias.objects.count()

            if alias_count > 0:
                ok.append(f'Customer aliases seeded: {alias_count}')
            else:
                warnings.append('No customer aliases found. Run seed.')

            # Sample job
            job = Job.objects.filter(
                test_series_no='CPRIBLRSCL25T1654'
            ).first()

            if job:
                ok.append(f'Sample job exists: {job.test_series_no}')

                if hasattr(job, 'sample'):
                    ok.append(f'Sample exists: {job.sample.sample_code}')
                else:
                    errors.append('Sample missing for job 25T1654.')

                test_count = job.tests.count()

                if test_count > 0:
                    ok.append(f'Tests seeded: {test_count}')
                else:
                    errors.append('No tests found for sample job.')

                measurement_count = Measurement.objects.filter(
                    test__job=job
                ).count()

                if measurement_count > 0:
                    ok.append(f'Measurements seeded: {measurement_count}')
                else:
                    warnings.append('No measurements found for sample job.')

                result_count = Result.objects.filter(job=job).count()

                if result_count > 0:
                    ok.append(f'Results computed: {result_count}')
                else:
                    warnings.append('No results computed for sample job.')

                report = Report.objects.filter(job=job).first()

                if report:
                    ok.append(f'Report exists: version {report.version}')
                else:
                    warnings.append('No report generated yet for sample job.')

            else:
                errors.append(
                    'Missing sample job CPRIBLRSCL25T1654. Run: python manage.py seed'
                )

            # Customer profile
            try:
                from portal.models import CustomerProfile

                customer_user = User.objects.filter(username='customer1').first()

                if customer_user:
                    profile = CustomerProfile.objects.filter(user=customer_user).first()

                    if profile:
                        ok.append(
                            f'Customer portal profile exists: '
                            f'{customer_user.username} → {profile.customer.legal_name}'
                        )
                    else:
                        errors.append(
                            'Customer portal profile missing. '
                            'Run: python manage.py setup_customer_profiles'
                        )

            except ImportError:
                warnings.append('Portal app not available. Customer profile check skipped.')

        except OperationalError:
            self.stderr.write(
                self.style.ERROR(
                    'Database not migrated. Run: python manage.py migrate'
                )
            )
            return

        # Optional dependencies
        try:
            import weasyprint
            ok.append('WeasyPrint installed.')
        except ImportError:
            warnings.append(
                'WeasyPrint not installed. Report will fallback to HTML storage.'
            )

        try:
            import pytesseract
            ok.append('pytesseract installed.')
        except ImportError:
            warnings.append(
                'pytesseract not installed. OCR will use manual-assist mode.'
            )

        # Output
        self.stdout.write(self.style.SUCCESS('\nDemo readiness check\n'))

        if ok:
            self.stdout.write(self.style.SUCCESS('OK:'))
            for item in ok:
                self.stdout.write(f'  ✓ {item}')

        if warnings:
            self.stdout.write(self.style.WARNING('\nWarnings:'))
            for item in warnings:
                self.stdout.write(self.style.WARNING(f'  ! {item}'))

        if errors:
            self.stdout.write(self.style.ERROR('\nErrors:'))
            for item in errors:
                self.stdout.write(self.style.ERROR(f'  ✗ {item}'))

            self.stdout.write(self.style.ERROR('\nDemo is NOT ready.'))
        else:
            self.stdout.write(self.style.SUCCESS('\nDemo is ready.'))
