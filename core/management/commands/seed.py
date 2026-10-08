"""
Seed script: loads the complete sample job 25T1654 (250 kVA transformer).
Values from Problem_Understanding.md §6.

Usage: python manage.py seed
"""
from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.utils import timezone
from core.models import (
    Customer, CustomerAlias, Job, Sample, TestType, Test,
    Parameter, Measurement, LimitRule, Result,
    DocumentType, Report, AuditLog, AuditAction,
    JobStatus, RequestType, EquipmentType, MeasurementStage,
    Phase, MeasurementSource, Comparator, Verdict,
)


class Command(BaseCommand):
    help = 'Seed database with job 25T1654 (250 kVA transformer) and all reference data.'

    def handle(self, *args, **options):
        self.stdout.write('🌱 Seeding ATRG database...')

        # ── 1. Groups (RBAC roles) ──────────────────────────────────────────
        self.stdout.write('  Creating role groups...')
        for role in ['Customer', 'Engineer', 'Quality', 'HOD', 'Admin']:
            Group.objects.get_or_create(name=role)

        # ── 2. Users ────────────────────────────────────────────────────────
        self.stdout.write('  Creating users...')
        users_data = [
            ('admin', 'Admin', 'admin', 'atrg@cpri.res.in'),
            ('engineer1', 'Engineer', 'P. Naveenkumar', 'naveen@cpri.res.in'),
            ('engineer2', 'Engineer', 'Uttej', 'uttej@cpri.res.in'),
            ('quality1', 'Quality', 'Quality Officer', 'quality@cpri.res.in'),
            ('hod1', 'HOD', 'Test In-charge / HOD', 'hod@cpri.res.in'),
            ('customer1', 'Customer', 'A.P. Transformers Rep', 'ap@transformers.com'),
        ]
        users = {}
        for username, role, name, email in users_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': name.split()[0],
                    'last_name': ' '.join(name.split()[1:]) if len(name.split()) > 1 else '',
                    'email': email,
                    'is_staff': role in ('Admin', 'HOD', 'Quality'),
                    'is_superuser': role == 'Admin',
                }
            )
            if created:
                user.set_password('atrg123')
                user.save()
            user.groups.add(Group.objects.get(name=role))
            users[username] = user

        # ── 3. Customer + Aliases ───────────────────────────────────────────
        self.stdout.write('  Creating customer: A.P. Transformers...')
        customer, _ = Customer.objects.get_or_create(
            legal_name='M/s. A.P. Transformers, Chennai',
            defaults={
                'address': 'Chennai, Tamil Nadu',
                'contact_person': 'Mr. Vivekanand Krishna',
                'email': 'ap@transformers.com',
                'phone': '+91-44-XXXX-XXXX',
            }
        )
        # The 5 spelling variants seen in scans → all point to one canonical row
        aliases = [
            'A.P. TRANSFORMERS',
            'AP Transformers',
            'Ap Transformers',
            'm/s A.P. Transformers',
            'M/s. A.P. Transformers, Chennai',
        ]
        for alias in aliases:
            CustomerAlias.objects.get_or_create(customer=customer, alias=alias)

        # ── 4. Test Types (CPRI form dictionary) ────────────────────────────
        self.stdout.write('  Creating test types...')
        test_types_data = [
            ('ROUTINE', 'Routine Tests', 'Sec 45', 'CPRI/QAF/02'),
            ('SC', 'Short Circuit Test', 'Sec 55', ''),
            ('LOSS', 'Loss Measurement', 'Sec 56', ''),
            ('TEMP', 'Temperature Rise Test', 'Sec 44', ''),
            ('OIL', 'Oil & Pressure Test', 'Sec 58', ''),
            ('WI', 'Work Instruction', 'QAF/02', 'CPRI/QAF/02'),
            ('CRF', 'Customer Request Form', 'QAF/01A', 'CPRI/QAF/01A'),
            ('PROFORMA', 'Proforma for Transformers', 'Sec 12', ''),
        ]
        test_types = {}
        for code, name, section, form in test_types_data:
            tt, _ = TestType.objects.get_or_create(
                code=code,
                defaults={'name': name, 'section_no': section, 'form_no': form}
            )
            test_types[code] = tt

        # ── 5. Parameters (measurement dictionary) ──────────────────────────
        self.stdout.write('  Creating parameters...')
        params_data = [
            # (code, label, unit, data_type, test_type_code)
            ('NLL_W', 'No-Load Loss', 'W', 'DECIMAL', 'LOSS'),
            ('NLL_112_W', 'No-Load Loss at 112.5%', 'W', 'DECIMAL', 'LOSS'),
            ('LLC_W', 'Load Loss (corrected)', 'W', 'DECIMAL', 'LOSS'),
            ('LLC_W75', 'Load Loss corrected to 75°C', 'W', 'DECIMAL', 'LOSS'),
            ('TOTAL_LOSS_50', 'Total Loss at 50% load', 'W', 'DECIMAL', 'LOSS'),
            ('TOTAL_LOSS_100', 'Total Loss at 100% load', 'W', 'DECIMAL', 'LOSS'),
            ('I_NL_A', 'No-Load Current', 'A', 'DECIMAL', 'LOSS'),
            ('I_NL_PCT', 'No-Load Current (% rated)', '%', 'DECIMAL', 'LOSS'),
            ('R_HV_OHM', 'HV Winding Resistance', 'Ω', 'DECIMAL', 'LOSS'),
            ('R_LV_OHM', 'LV Winding Resistance', 'Ω', 'DECIMAL', 'LOSS'),
            ('ISC_KA', 'Short Circuit Current', 'kA', 'DECIMAL', 'SC'),
            ('ISC_PEAK_KA', 'Peak Short Circuit Current', 'kA', 'DECIMAL', 'SC'),
            ('APPLIED_KV', 'Applied Voltage', 'kV', 'DECIMAL', 'SC'),
            ('DURATION_S', 'Shot Duration', 's', 'DECIMAL', 'SC'),
            ('RATIO_ERR_PCT', 'Voltage Ratio Error', '%', 'DECIMAL', 'ROUTINE'),
            ('IR_GOHM', 'Insulation Resistance', 'GΩ', 'DECIMAL', 'ROUTINE'),
            ('VECTOR_GROUP', 'Vector Group Verification', '', 'BOOLEAN', 'ROUTINE'),
            ('INDUCED_V', 'Induced Overvoltage', 'V', 'DECIMAL', 'ROUTINE'),
            ('PF_HV_KV', 'Power Frequency Withstand HV', 'kV', 'DECIMAL', 'ROUTINE'),
            ('PF_LV_KV', 'Power Frequency Withstand LV', 'kV', 'DECIMAL', 'ROUTINE'),
            ('TOP_OIL_C', 'Top Oil Temperature', '°C', 'DECIMAL', 'TEMP'),
            ('AMB_C', 'Ambient Temperature', '°C', 'DECIMAL', 'TEMP'),
            ('HV_RISE_C', 'HV Winding Temperature Rise', '°C', 'DECIMAL', 'TEMP'),
            ('LV_RISE_C', 'LV Winding Temperature Rise', '°C', 'DECIMAL', 'TEMP'),
            ('PRESSURE_KPA', 'Test Pressure', 'kPa', 'DECIMAL', 'OIL'),
            ('LEAKAGE', 'Oil Leakage', '', 'BOOLEAN', 'OIL'),
        ]
        params = {}
        for code, label, unit, dtype, tt_code in params_data:
            p, _ = Parameter.objects.get_or_create(
                code=code,
                defaults={
                    'label': label,
                    'unit': unit,
                    'data_type': dtype,
                    'test_type': test_types.get(tt_code),
                }
            )
            params[code] = p

        # ── 6. Limit Rules (IS 1180 EEL-1 for 250 kVA) ──────────────────────
        self.stdout.write('  Creating limit rules...')
        rules_data = [
            # (code, standard, clause, param_code, applies_when, limit, comparator)
            ('NLL_EEL1_250', 'IS 1180', 'EEL-1 Table 1', 'NLL_W', 'EEL-1, 250 kVA', Decimal('980'), 'LE'),
            ('TOTAL_LOSS_50_EEL1', 'IS 1180', 'EEL-1 Table 1', 'TOTAL_LOSS_50', 'EEL-1, 250 kVA', Decimal('980'), 'LE'),
            ('TOTAL_LOSS_100_EEL1', 'IS 1180', 'EEL-1 Table 1', 'TOTAL_LOSS_100', 'EEL-1, 250 kVA', Decimal('2930'), 'LE'),
            ('I_NL_2PCT', 'IS 1180', 'Clause 7.3', 'I_NL_PCT', 'Rated voltage', Decimal('2.0'), 'LE'),
            ('I_NL_5PCT_112', 'IS 1180', 'Clause 7.3', 'I_NL_PCT', '112.5% voltage', Decimal('5.0'), 'LE'),
            ('HV_RISE_40C', 'IS 1180', 'Clause 8.1', 'HV_RISE_C', 'Guarantee 40°C', Decimal('40.0'), 'LE'),
            ('LV_RISE_40C', 'IS 1180', 'Clause 8.1', 'LV_RISE_C', 'Guarantee 40°C', Decimal('40.0'), 'LE'),
            ('TOP_OIL_RISE_35C', 'IS 1180', 'Clause 8.1', 'TOP_OIL_C', 'Guarantee 35°C', Decimal('35.0'), 'LE'),
            ('RATIO_ERR_05PCT', 'IS 1180', 'Clause 6.2', 'RATIO_ERR_PCT', 'All taps', Decimal('0.5'), 'WITHIN'),
        ]
        for code, std, clause, param_code, applies, limit, comp in rules_data:
            LimitRule.objects.get_or_create(
                code=code,
                defaults={
                    'standard': std,
                    'clause': clause,
                    'parameter': params[param_code],
                    'applies_when': applies,
                    'limit_value': limit,
                    'comparator': comp,
                }
            )

        # ── 7. Document Types ───────────────────────────────────────────────
        for code, name in [('CRF', 'Customer Request Form'), ('PROFORMA', 'Proforma'),
                           ('LOGSHEET', 'Log Sheet'), ('REPORT', 'Test Report'),
                           ('WI', 'Work Instruction')]:
            DocumentType.objects.get_or_create(code=code, defaults={'name': name})

        # ── 8. The Job: 25T1654 ─────────────────────────────────────────────
        self.stdout.write('  Creating job 25T1654...')
        received = timezone.make_aware(timezone.datetime(2025, 10, 27))
        job, _ = Job.objects.get_or_create(
            test_series_no='CPRIBLRSCL25T1654',
            defaults={
                'file_no': 'CPRIBLRSCL25T1654',
                'request_type': RequestType.TYPE,
                'standard': 'IS 1180',
                'eel_level': 'EEL-1',
                'customer': customer,
                'status': JobStatus.IN_PROGRESS,
                'received_at': received,
                'promised_at': received + timedelta(days=10),
                'created_by': users['admin'],
            }
        )

        # ── 9. Sample (from Proforma Sec 12) ────────────────────────────────
        self.stdout.write('  Creating sample HVD25S0847...')
        sample, _ = Sample.objects.get_or_create(
            job=job,
            defaults={
                'sample_code': 'HVD25S0847',
                'equipment_type': EquipmentType.TRANSFORMER,
                'serial_no': '1098',
                'rating_kva': Decimal('250.00'),
                'vector_group': 'Dyn11',
                'hv_v': Decimal('11000.00'),
                'lv_v': Decimal('433.00'),
                'frequency_hz': Decimal('50.0'),
                'cooling': 'ONAN',
                'oil_volume_l': Decimal('460.0'),
                'bil_hv_kv': Decimal('75.0'),
                'bil_lv_kv': Decimal('28.0'),
                'tap_min_pct': Decimal('-10.00'),
                'tap_max_pct': Decimal('5.00'),
                'tap_steps': 7,
                'manufacturer': customer,
                'manufactured_on': date(2025, 10, 1),
                'specs_json': {
                    'impedance_pct': 4.50,
                    'winding_material': 'Copper',
                    'construction': 'Oil-immersed, non-sealed, outdoor',
                    'guaranteed_temp_rise': {'hv': 40, 'lv': 40, 'top_oil': 35},
                },
            }
        )

        # ── 10. Tests ───────────────────────────────────────────────────────
        self.stdout.write('  Creating test instances...')
        engineer = users['engineer1']
        tests_created = []
        for tt_code, bay, start_date in [
            ('ROUTINE', 'Bay 1', date(2025, 10, 29)),
            ('LOSS', 'Bay 1', date(2025, 10, 29)),
            ('SC', 'Bay 3', date(2025, 10, 31)),
            ('TEMP', 'Bay 2', date(2025, 11, 9)),
            ('OIL', 'Bay 2', date(2025, 11, 13)),
        ]:
            t, _ = Test.objects.get_or_create(
                job=job,
                test_type=test_types[tt_code],
                defaults={
                    'bay': bay,
                    'performed_by': engineer,
                    'started_at': timezone.make_aware(
                        timezone.datetime(start_date.year, start_date.month, start_date.day, 9, 0)
                    ),
                }
            )
            tests_created.append(t)

        # ── 11. Sample Measurements (from logsheets) ────────────────────────
        self.stdout.write('  Creating measurements...')
        routine_test = tests_created[0]
        loss_test = tests_created[1]

        # Routine: No-load current
        Measurement.objects.get_or_create(
            test=loss_test, parameter=params['I_NL_A'],
            stage=MeasurementStage.BT,
            defaults={
                'value': Decimal('1.6890'),
                'unit': 'A',
                'source': MeasurementSource.MANUAL,
                'captured_by': engineer,
            }
        )
        # No-load loss at 100%
        Measurement.objects.get_or_create(
            test=loss_test, parameter=params['NLL_W'],
            stage=MeasurementStage.BT,
            defaults={
                'value': Decimal('908.0000'),
                'unit': 'W',
                'source': MeasurementSource.MANUAL,
                'captured_by': engineer,
            }
        )
        # Total loss at 100% (from datasheet)
        Measurement.objects.get_or_create(
            test=loss_test, parameter=params['TOTAL_LOSS_100'],
            stage=MeasurementStage.BT,
            defaults={
                'value': Decimal('2486.0000'),
                'unit': 'W',
                'source': MeasurementSource.IMPORT,
                'captured_by': engineer,
            }
        )

        # Temperature rise results
        temp_test = tests_created[3]
        Measurement.objects.get_or_create(
            test=temp_test, parameter=params['HV_RISE_C'],
            stage=MeasurementStage.AT,
            defaults={'value': Decimal('39.7000'), 'unit': '°C', 'source': MeasurementSource.MANUAL, 'captured_by': engineer}
        )
        Measurement.objects.get_or_create(
            test=temp_test, parameter=params['LV_RISE_C'],
            stage=MeasurementStage.AT,
            defaults={'value': Decimal('34.3000'), 'unit': '°C', 'source': MeasurementSource.MANUAL, 'captured_by': engineer}
        )
        Measurement.objects.get_or_create(
            test=temp_test, parameter=params['TOP_OIL_C'],
            stage=MeasurementStage.AT,
            defaults={'value': Decimal('26.1000'), 'unit': '°C', 'source': MeasurementSource.MANUAL, 'captured_by': engineer}
        )

        # ── 12. Evaluate rules → Results ────────────────────────────────────
        self.stdout.write('  Evaluating limit rules...')
        from testing.services import evaluate_all_rules_for_job
        results = evaluate_all_rules_for_job(job)
        for r in results:
            self.stdout.write(f'    {r.rule.code}: {r.measured} → {r.verdict}')

        # ── 13. Audit log entry for seed ────────────────────────────────────
        AuditLog.objects.create(
            actor=users['admin'],
            entity='Job',
            entity_id=job.pk,
            action=AuditAction.CREATE,
            field='*',
            old_value='',
            new_value='Seeded via management command',
        )

        # Customer portal profile (drives the customer progress view)
        from portal.models import CustomerProfile

        CustomerProfile.objects.get_or_create(
            user=users['customer1'],
            defaults={
                'customer': customer,
            }
        )

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Seed complete!\n'
            f'   Job: {job.test_series_no}\n'
            f'   Sample: {sample.sample_code}\n'
            f'   Tests: {len(tests_created)}\n'
            f'   Measurements: {Measurement.objects.count()}\n'
            f'   Rules evaluated: {len(results)}\n'
            f'   Users: {len(users)} (password: atrg123)\n'
        ))
