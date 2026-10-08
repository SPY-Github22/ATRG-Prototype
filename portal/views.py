import os
import uuid

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import FileResponse, Http404
from django.db.models import Q
from django.utils import timezone

from core.models import (
    Job,
    JobStatus,
    Test,
    Parameter,
    AuditLog,
    AuditAction,
    Report,
    ReportState,
    Phase,
    Notification,
    Sample,
)

from core.utils import role_required

from testing.services import (
    save_measurement,
    check_bt_at_anomaly,
)

from review.services import (
    transition,
    get_available_actions,
    get_user_roles,
    can_transition,
    ACTION_LABELS,
    guard_locked_write,
)

from reports.services import (
    generate_report_pdf,
    verify_report_integrity,
    build_report_context,
)

from .forms import (
    MeasurementForm,
    RatioGridForm,
    CustomerRequestForm,
    SCShotForm,
    TempRiseQuickForm,
    OilPressureQuickForm,
)

from .services import (
    get_customer_for_user,
    notify_transition,
    notify_all_tests_complete,
    progress_summary,
)


# ─────────────────────────────────────────────────────────────────────────────
# Internal dashboard
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    roles = get_user_roles(request.user)

    # Customers should not see the internal dashboard
    if 'Customer' in roles and not request.user.is_superuser:
        return redirect('portal:customer_home')

    q = request.GET.get('q', '').strip()

    jobs = Job.objects.select_related(
        'customer',
        'sample',
    ).order_by('-received_at')

    if q:
        jobs = jobs.filter(
            Q(test_series_no__icontains=q) |
            Q(file_no__icontains=q) |
            Q(customer__legal_name__icontains=q) |
            Q(sample__sample_code__icontains=q)
        )

    status_counts = {
        status.value: Job.objects.filter(status=status.value).count()
        for status in JobStatus
    }

    context = {
        'jobs': jobs,
        'status_counts': status_counts,
        'total_jobs': Job.objects.count(),
        'q': q,
        'now': timezone.now(),
    }

    return render(request, 'portal/dashboard.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Internal job detail
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def job_detail(request, job_id):
    roles = get_user_roles(request.user)

    if 'Customer' in roles and not request.user.is_superuser:
        return redirect('portal:customer_job_detail', job_id=job_id)

    job = get_object_or_404(
        Job.objects.select_related('customer', 'sample'),
        pk=job_id,
    )

    tests = job.tests.select_related('test_type').order_by('test_type__code')

    results = job.results.select_related(
        'rule',
        'rule__parameter',
    ).order_by('rule__code')

    report = job.reports.order_by('-version').first()

    anomalies = check_bt_at_anomaly(job)

    actions = get_available_actions(request.user, job)

    # Draft creation is handled by the Generate Report button.
    actions = [a for a in actions if a['action'] != 'draft_report']

    can_generate_report = (
        not job.is_locked and
        job.status in (
            JobStatus.IN_PROGRESS,
            JobStatus.TESTING_DONE,
            JobStatus.REPORT_DRAFT,
        ) and
        (
            request.user.is_superuser or
            any(role in ('Engineer', 'Admin') for role in roles)
        )
    )

    context = {
        'job': job,
        'tests': tests,
        'results': results,
        'report': report,
        'anomalies': anomalies,
        'actions': actions,
        'can_generate_report': can_generate_report,
        'roles': roles,
    }

    return render(request, 'portal/job_detail.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Engineer bay data entry
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_required('Engineer', 'Admin')
@login_required
@role_required('Engineer', 'Admin')
def test_enter(request, test_id):
    test = get_object_or_404(
        Test.objects.select_related(
            'job',
            'test_type',
            'job__sample',
            'job__customer',
        ),
        pk=test_id,
    )

    job = test.job

    if job.is_locked:
        messages.error(request, 'Job is locked. Measurements cannot be modified.')
        return redirect('portal:job_detail', job_id=job.pk)

    taps = 7

    if hasattr(job, 'sample') and job.sample.tap_steps:
        taps = job.sample.tap_steps

    phases = [code for code, _ in Phase.choices]

    test_code = test.test_type.code.upper()

    is_routine = test_code == 'ROUTINE'
    is_sc = test_code == 'SC'
    is_temp = test_code == 'TEMP'
    is_oil = test_code == 'OIL'

    initial_ratio = {}

    if is_routine:
        existing_ratio_values = test.measurements.filter(
            parameter__code='RATIO_ERR_PCT'
        )

        for m in existing_ratio_values:
            if m.tap_position and m.phase:
                initial_ratio[f'ratio_{m.tap_position}_{m.phase}'] = m.value

    def base_forms():
        measurement_form = MeasurementForm(test_type=test.test_type)

        ratio_form = RatioGridForm(
            taps=taps,
            initial=initial_ratio,
        ) if is_routine else None

        sc_form = SCShotForm() if is_sc else None
        temp_form = TempRiseQuickForm() if is_temp else None
        oil_form = OilPressureQuickForm() if is_oil else None

        return measurement_form, ratio_form, sc_form, temp_form, oil_form

    measurement_form, ratio_form, sc_form, temp_form, oil_form = base_forms()

    if request.method == 'POST':

        # ─────────────────────────────────────────────────────────────
        # Generic measurement save
        # ─────────────────────────────────────────────────────────────
        if 'save_measurement' in request.POST:
            form = MeasurementForm(request.POST, test_type=test.test_type)

            if form.is_valid():
                try:
                    save_measurement(
                        actor=request.user,
                        test=test,
                        parameter=form.cleaned_data['parameter'],
                        value=form.cleaned_data['value'],
                        stage=form.cleaned_data['stage'],
                        tap_position=form.cleaned_data.get('tap_position'),
                        phase=form.cleaned_data.get('phase') or None,
                    )

                    messages.success(
                        request,
                        f'Saved {form.cleaned_data["parameter"].code}.'
                    )

                    return redirect('portal:test_enter', test_id=test.pk)

                except (ValidationError, PermissionDenied) as exc:
                    messages.error(request, str(exc))

            measurement_form = form

        # ─────────────────────────────────────────────────────────────
        # Routine ratio grid save
        # ─────────────────────────────────────────────────────────────
        elif 'save_ratio_grid' in request.POST:
            ratio_form = RatioGridForm(request.POST, taps=taps)

            if ratio_form.is_valid():
                ratio_param = Parameter.objects.filter(code='RATIO_ERR_PCT').first()

                if not ratio_param:
                    messages.error(
                        request,
                        'RATIO_ERR_PCT parameter is missing. Run the seed command.'
                    )
                else:
                    stage = ratio_form.cleaned_data.get('stage', 'BT')
                    count = 0

                    try:
                        with transaction.atomic():
                            for key, value in ratio_form.cleaned_data.items():
                                if key.startswith('ratio_') and value is not None:
                                    _, tap, phase_code = key.split('_')

                                    save_measurement(
                                        actor=request.user,
                                        test=test,
                                        parameter=ratio_param,
                                        value=value,
                                        stage=stage,
                                        tap_position=int(tap),
                                        phase=phase_code,
                                    )

                                    count += 1

                        messages.success(
                            request,
                            f'Saved {count} ratio measurement(s).'
                        )

                        return redirect('portal:test_enter', test_id=test.pk)

                    except (ValidationError, PermissionDenied) as exc:
                        messages.error(request, str(exc))

        # ─────────────────────────────────────────────────────────────
        # Short-circuit shot save
        # ─────────────────────────────────────────────────────────────
        elif 'save_sc_shot' in request.POST:
            sc_form = SCShotForm(request.POST)

            if sc_form.is_valid():
                cleaned = sc_form.cleaned_data

                shot_no = cleaned.get('shot_no')
                stage = cleaned.get('stage', 'AT')
                phase = cleaned.get('phase') or None

                field_parameter_map = [
                    ('applied_kv', 'APPLIED_KV'),
                    ('peak_current_ka', 'ISC_PEAK_KA'),
                    ('rms_current_ka', 'ISC_KA'),
                    ('duration_s', 'DURATION_S'),
                ]

                count = 0

                try:
                    with transaction.atomic():
                        for field_name, parameter_code in field_parameter_map:
                            value = cleaned.get(field_name)

                            if value is None:
                                continue

                            parameter = Parameter.objects.filter(
                                code=parameter_code
                            ).first()

                            if not parameter:
                                raise ValidationError(
                                    f'Parameter {parameter_code} is missing. Run seed.'
                                )

                            save_measurement(
                                actor=request.user,
                                test=test,
                                parameter=parameter,
                                value=value,
                                stage=stage,
                                tap_position=shot_no,
                                phase=phase,
                                raw_text=f'SC shot {shot_no}',
                            )

                            count += 1

                    messages.success(
                        request,
                        f'Saved SC shot {shot_no}: {count} measurement(s).'
                    )

                    return redirect('portal:test_enter', test_id=test.pk)

                except (ValidationError, PermissionDenied) as exc:
                    messages.error(request, str(exc))

        # ─────────────────────────────────────────────────────────────
        # Temperature-rise quick save
        # ─────────────────────────────────────────────────────────────
        elif 'save_temp_quick' in request.POST:
            temp_form = TempRiseQuickForm(request.POST)

            if temp_form.is_valid():
                cleaned = temp_form.cleaned_data

                stage = cleaned.get('stage', 'AT')
                hour = cleaned.get('hour')

                field_parameter_map = [
                    ('top_oil_c', 'TOP_OIL_C'),
                    ('ambient_c', 'AMB_C'),
                    ('hv_rise_c', 'HV_RISE_C'),
                    ('lv_rise_c', 'LV_RISE_C'),
                ]

                count = 0

                raw_text = (
                    f'Temperature rise reading {hour}'
                    if hour
                    else 'Temperature rise reading'
                )

                try:
                    with transaction.atomic():
                        for field_name, parameter_code in field_parameter_map:
                            value = cleaned.get(field_name)

                            if value is None:
                                continue

                            parameter = Parameter.objects.filter(
                                code=parameter_code
                            ).first()

                            if not parameter:
                                raise ValidationError(
                                    f'Parameter {parameter_code} is missing. Run seed.'
                                )

                            save_measurement(
                                actor=request.user,
                                test=test,
                                parameter=parameter,
                                value=value,
                                stage=stage,
                                tap_position=hour,
                                phase=None,
                                raw_text=raw_text,
                            )

                            count += 1

                    messages.success(
                        request,
                        f'Saved {count} temperature-rise measurement(s).'
                    )

                    return redirect('portal:test_enter', test_id=test.pk)

                except (ValidationError, PermissionDenied) as exc:
                    messages.error(request, str(exc))

        # ─────────────────────────────────────────────────────────────
        # Oil/pressure quick save
        # ─────────────────────────────────────────────────────────────
        elif 'save_oil_quick' in request.POST:
            oil_form = OilPressureQuickForm(request.POST)

            if oil_form.is_valid():
                cleaned = oil_form.cleaned_data

                stage = cleaned.get('stage', 'AT')
                pressure = cleaned.get('pressure_kpa')
                leakage = cleaned.get('leakage')

                count = 0

                try:
                    with transaction.atomic():
                        if pressure is not None:
                            pressure_parameter = Parameter.objects.filter(
                                code='PRESSURE_KPA'
                            ).first()

                            if not pressure_parameter:
                                raise ValidationError(
                                    'Parameter PRESSURE_KPA is missing. Run seed.'
                                )

                            save_measurement(
                                actor=request.user,
                                test=test,
                                parameter=pressure_parameter,
                                value=pressure,
                                stage=stage,
                                tap_position=None,
                                phase=None,
                                raw_text='Oil pressure test',
                            )

                            count += 1

                        if leakage not in (None, ''):
                            leakage_parameter = Parameter.objects.filter(
                                code='LEAKAGE'
                            ).first()

                            if not leakage_parameter:
                                raise ValidationError(
                                    'Parameter LEAKAGE is missing. Run seed.'
                                )

                            save_measurement(
                                actor=request.user,
                                test=test,
                                parameter=leakage_parameter,
                                value=Decimal(leakage),
                                stage=stage,
                                tap_position=None,
                                phase=None,
                                raw_text='Oil leakage check',
                            )

                            count += 1

                    messages.success(
                        request,
                        f'Saved {count} oil/pressure measurement(s).'
                    )

                    return redirect('portal:test_enter', test_id=test.pk)

                except (ValidationError, PermissionDenied) as exc:
                    messages.error(request, str(exc))

    measurements = test.measurements.select_related(
        'parameter',
        'captured_by',
    ).order_by('parameter__code', 'stage', 'tap_position', 'phase')

    ratio_fields = []

    if is_routine and ratio_form:
        for tap in range(1, taps + 1):
            cells = []

            for phase_code in phases:
                field_name = f'ratio_{tap}_{phase_code}'
                cells.append(ratio_form[field_name])

            ratio_fields.append({
                'tap': tap,
                'cells': cells,
            })

    context = {
        'test': test,
        'job': job,
        'measurement_form': measurement_form,
        'ratio_form': ratio_form,
        'ratio_fields': ratio_fields,
        'measurements': measurements,
        'is_routine': is_routine,
        'is_sc': is_sc,
        'is_temp': is_temp,
        'is_oil': is_oil,
        'sc_form': sc_form,
        'temp_form': temp_form,
        'oil_form': oil_form,
    }

    return render(request, 'portal/test_enter.html', context)

@login_required
@role_required('Engineer', 'Admin')
def test_complete(request, test_id):
    if request.method != 'POST':
        return redirect('portal:dashboard')

    test = get_object_or_404(
        Test.objects.select_related('job'),
        pk=test_id,
    )

    job = test.job

    guard_locked_write(job)

    if not test.completed_at:
        old_value = str(test.completed_at)

        test.completed_at = timezone.now()
        test.save()

        AuditLog.objects.create(
            actor=request.user,
            entity='Test',
            entity_id=test.pk,
            action=AuditAction.UPDATE,
            field='completed_at',
            old_value=old_value,
            new_value=str(test.completed_at),
        )

        messages.success(
            request,
            f'{test.test_type.name} marked complete.'
        )

        # If all tests are complete, notify customer
        if job.tests.exists():
            remaining = job.tests.filter(completed_at__isnull=True).count()

            if remaining == 0:
                notify_all_tests_complete(job)

    else:
        messages.info(request, 'Test is already marked complete.')

    return redirect('portal:job_detail', job_id=job.pk)


# ─────────────────────────────────────────────────────────────────────────────
# Report generation
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_required('Engineer', 'Admin')
def generate_report(request, job_id):
    if request.method != 'POST':
        return redirect('portal:dashboard')

    job = get_object_or_404(Job, pk=job_id)

    if job.is_locked:
        messages.error(request, 'Job is locked. Cannot generate a new report.')
        return redirect('portal:job_detail', job_id=job.pk)

    try:
        report = generate_report_pdf(job, request.user)

        # Move workflow into REPORT_DRAFT if possible.
        if job.status in (JobStatus.IN_PROGRESS, JobStatus.TESTING_DONE):
            if can_transition(request.user, 'draft_report'):
                try:
                    transition(
                        actor=request.user,
                        job=job,
                        action='draft_report',
                        comment='Report generated.',
                    )
                except (PermissionDenied, ValidationError):
                    pass

        messages.success(
            request,
            f'Report version {report.version} generated.'
        )

    except Exception as exc:
        messages.error(request, f'Report generation failed: {exc}')

    return redirect('portal:job_detail', job_id=job.pk)


# ─────────────────────────────────────────────────────────────────────────────
# Report preview/download/verify
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def report_preview(request, job_id):
    job = get_object_or_404(
        Job.objects.select_related('customer', 'sample'),
        pk=job_id,
    )

    roles = get_user_roles(request.user)

    if 'Customer' in roles and job.status != JobStatus.RELEASED:
        raise PermissionDenied('Report is not yet released.')

    context = build_report_context(job)

    return render(request, 'reports/test_certificate.html', context)


@login_required
def report_download(request, report_id):
    report = get_object_or_404(
        Report.objects.select_related('pdf', 'job'),
        pk=report_id,
    )

    roles = get_user_roles(request.user)

    if 'Customer' in roles and report.state != ReportState.RELEASED:
        raise PermissionDenied('Report is not released.')

    if not report.pdf or not report.pdf.file:
        raise Http404('No report file attached.')

    try:
        file_handle = report.pdf.file.open('rb')
    except FileNotFoundError:
        raise Http404('Report file missing from storage.')

    filename = os.path.basename(report.pdf.file.name)

    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=filename,
    )


@login_required
def verify_report(request, report_id):
    report = get_object_or_404(Report, pk=report_id)

    ok = verify_report_integrity(report)

    if ok:
        messages.success(request, 'Report integrity verified. SHA-256 matches.')
    else:
        messages.error(request, 'Report integrity check failed.')

    return redirect('portal:job_detail', job_id=report.job_id)


# ─────────────────────────────────────────────────────────────────────────────
# Workflow transition
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def transition_view(request, job_id, action):
    if request.method != 'POST':
        return redirect('portal:dashboard')

    job = get_object_or_404(Job, pk=job_id)
    comment = request.POST.get('comment', '').strip()

    try:
        transition(
            actor=request.user,
            job=job,
            action=action,
            comment=comment,
        )

        # Customer notifications for selected transitions
        notify_transition(job, action)

        messages.success(
            request,
            f'{ACTION_LABELS.get(action, action)} completed.'
        )

    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, str(exc))

    return redirect('portal:job_detail', job_id=job.pk)


# ─────────────────────────────────────────────────────────────────────────────
# Audit trail
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_required('Quality', 'HOD', 'Admin')
def audit_log(request):
    logs = AuditLog.objects.select_related('actor').order_by('-at')[:500]

    entity = request.GET.get('entity', '').strip()

    if entity:
        logs = logs.filter(entity__icontains=entity)

    context = {
        'logs': logs,
        'entity': entity,
    }

    return render(request, 'portal/audit_log.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Customer portal home
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def customer_home(request):
    customer = get_customer_for_user(request.user)

    if not customer:
        if request.user.is_superuser:
            return redirect('portal:dashboard')

        raise PermissionDenied(
            'This account is not linked to a customer profile. '
            'Run: python manage.py setup_customer_profiles'
        )

    jobs = Job.objects.filter(
        customer=customer
    ).select_related('sample').order_by('-received_at')

    jobs_data = []

    for job in jobs:
        jobs_data.append({
            'job': job,
            'progress': progress_summary(job),
        })

    notifications = Notification.objects.filter(
        customer=customer
    ).select_related('job').order_by('-created_at')[:5]

    context = {
        'customer': customer,
        'jobs_data': jobs_data,
        'notifications': notifications,
    }

    return render(request, 'portal/customer_home.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Customer request submission
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def customer_request_new(request):
    customer = get_customer_for_user(request.user)

    if not customer:
        if request.user.is_superuser:
            messages.error(request, 'Superusers must use Django admin to create jobs.')
            return redirect('portal:dashboard')

        raise PermissionDenied('No customer profile linked to this user.')

    if request.method == 'POST':
        form = CustomerRequestForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                temporary_series = f'REQ-{uuid.uuid4().hex[:8].upper()}'

                job = Job.objects.create(
                    test_series_no=temporary_series,
                    file_no='',
                    request_type=form.cleaned_data['request_type'],
                    standard=form.cleaned_data['standard'],
                    eel_level=form.cleaned_data['eel_level'],
                    customer=customer,
                    status=JobStatus.REQUESTED,
                    received_at=timezone.now(),
                    created_by=request.user,
                )

                # Assign a human-readable provisional series number
                job.test_series_no = f'REQ-{timezone.now().date():%Y%m%d}-{job.pk}'
                job.file_no = job.test_series_no
                job.save()

                sample_code = f'PROV-{job.pk}'

                Sample.objects.create(
                    job=job,
                    sample_code=sample_code,
                    equipment_type=form.cleaned_data['equipment_type'],
                    serial_no=form.cleaned_data['serial_no'],
                    rating_kva=form.cleaned_data['rating_kva'],
                    hv_v=form.cleaned_data['hv_v'],
                    lv_v=form.cleaned_data['lv_v'],
                    frequency_hz=form.cleaned_data['frequency_hz'],
                    vector_group=form.cleaned_data['vector_group'],
                    manufacturer=customer,
                    specs_json={
                        'request_description': form.cleaned_data['description'],
                        'submitted_via': 'customer_portal',
                    },
                )

                AuditLog.objects.create(
                    actor=request.user,
                    entity='Job',
                    entity_id=job.pk,
                    action=AuditAction.CREATE,
                    field='*',
                    old_value='',
                    new_value='Customer portal request',
                )

                Notification.objects.create(
                    customer=customer,
                    job=job,
                    message=(
                        f'Your test request {job.test_series_no} has been submitted '
                        f'and is awaiting lab review.'
                    ),
                    kind='STATUS',
                )

            messages.success(
                request,
                f'Request submitted. Provisional job number: {job.test_series_no}.'
            )

            return redirect('portal:customer_job_detail', job_id=job.pk)

    else:
        form = CustomerRequestForm()

    context = {
        'form': form,
        'customer': customer,
    }

    return render(request, 'portal/customer_request_new.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Customer job progress view
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def customer_job_detail(request, job_id):
    job = get_object_or_404(
        Job.objects.select_related('customer', 'sample'),
        pk=job_id,
    )

    customer = get_customer_for_user(request.user)

    if not request.user.is_superuser:
        if not customer or job.customer_id != customer.id:
            raise PermissionDenied('You do not have access to this job.')

    report = job.reports.order_by('-version').first()

    can_download = bool(
        report and
        report.state == ReportState.RELEASED
    )

    progress = progress_summary(job)

    context = {
        'job': job,
        'report': report,
        'can_download': can_download,
        'progress': progress,
    }

    return render(request, 'portal/customer_job_detail.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Customer notifications
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def customer_notifications(request):
    customer = get_customer_for_user(request.user)

    if not customer:
        if request.user.is_superuser:
            return redirect('portal:dashboard')

        raise PermissionDenied('No customer profile linked to this user.')

    notifications = Notification.objects.filter(
        customer=customer
    ).select_related('job').order_by('-created_at')

    unread_count = notifications.filter(read_at__isnull=True).count()

    context = {
        'notifications': notifications,
        'unread_count': unread_count,
    }

    return render(request, 'portal/customer_notifications.html', context)


@login_required
def notification_mark_read(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id)

    customer = get_customer_for_user(request.user)

    if not request.user.is_superuser:
        if not customer or notification.customer_id != customer.id:
            raise PermissionDenied('You do not have access to this notification.')

    if not notification.read_at:
        notification.read_at = timezone.now()
        notification.save()

    return redirect(request.META.get('HTTP_REFERER', '/customer/notifications/'))


@login_required
def notifications_mark_all_read(request):
    if request.method != 'POST':
        return redirect('portal:customer_notifications')

    customer = get_customer_for_user(request.user)

    if not customer:
        if request.user.is_superuser:
            return redirect('portal:dashboard')

        raise PermissionDenied('No customer profile linked to this user.')

    Notification.objects.filter(
        customer=customer,
        read_at__isnull=True,
    ).update(read_at=timezone.now())

    messages.success(request, 'All notifications marked as read.')

    return redirect('portal:customer_notifications')
