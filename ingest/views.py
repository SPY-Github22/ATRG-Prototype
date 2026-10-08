from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.utils import role_required
from core.models import Parameter, MeasurementSource

from testing.services import save_measurement

from .models import ImportBatch, OCRQueueItem
from .forms import ImportStartForm, MappingForm, OCRUploadForm
from . import services as ingest_services
from . import ocr as ocr_services


# ─────────────────────────────────────────────────────────────────────────────
# CSV IMPORT
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_required('Engineer', 'Quality', 'Admin')
def import_batch_list(request):
    batches = ImportBatch.objects.select_related(
        'job',
        'test',
        'uploaded_by',
    ).order_by('-uploaded_at')[:100]

    context = {
        'batches': batches,
    }

    return render(request, 'ingest/import_batch_list.html', context)


@login_required
@role_required('Engineer', 'Admin')
def import_start(request):
    if request.method == 'POST':
        form = ImportStartForm(request.POST, request.FILES)

        if form.is_valid():
            test = form.cleaned_data['test']
            uploaded = form.cleaned_data['file']

            batch = ImportBatch.objects.create(
                job=test.job,
                test=test,
                filename=uploaded.name,
                uploaded_by=request.user,
                status=ImportBatch.Status.PENDING,
            )

            batch.file.save(uploaded.name, uploaded, save=True)

            try:
                headers = ingest_services.read_csv_headers(batch)

                if not headers:
                    batch.status = ImportBatch.Status.FAILED
                    batch.error_log = 'CSV file appears to be empty.'
                    batch.save()

                    messages.error(
                        request,
                        'CSV file appears to be empty.'
                    )

                    return redirect('ingest:import_start')

                batch.header_json = headers
                batch.mapping_json = ingest_services.guess_mapping(headers)
                batch.status = ImportBatch.Status.PENDING
                batch.save()

                return redirect('ingest:import_mapping', batch_id=batch.pk)

            except ValidationError as exc:
                batch.status = ImportBatch.Status.FAILED
                batch.error_log = str(exc)
                batch.save()

                messages.error(request, str(exc))
                return redirect('ingest:import_start')

    else:
        form = ImportStartForm()

    context = {
        'form': form,
    }

    return render(request, 'ingest/import_start.html', context)


@login_required
@role_required('Engineer', 'Admin')
def import_mapping(request, batch_id):
    batch = get_object_or_404(ImportBatch, pk=batch_id)

    if not batch.header_json:
        messages.error(request, 'This import batch has no CSV headers.')
        return redirect('ingest:import_start')

    initial_mapping = batch.mapping_json or ingest_services.guess_mapping(batch.header_json)

    if request.method == 'POST':
        form = MappingForm(
            request.POST,
            headers=batch.header_json,
            initial_mapping=initial_mapping,
        )

        if form.is_valid():
            batch.mapping_json = {
                'parameter_code_column': form.cleaned_data['parameter_code_column'],
                'value_column': form.cleaned_data['value_column'],
                'stage_column': form.cleaned_data.get('stage_column') or '',
                'tap_column': form.cleaned_data.get('tap_column') or '',
                'phase_column': form.cleaned_data.get('phase_column') or '',
                'default_stage': form.cleaned_data.get('default_stage', 'BT'),
            }

            batch.status = ImportBatch.Status.MAPPED
            batch.save()

            return redirect('ingest:import_preview', batch_id=batch.pk)

    else:
        form = MappingForm(
            headers=batch.header_json,
            initial_mapping=initial_mapping,
        )

    context = {
        'batch': batch,
        'form': form,
    }

    return render(request, 'ingest/import_mapping.html', context)


@login_required
@role_required('Engineer', 'Admin')
def import_preview(request, batch_id):
    batch = get_object_or_404(ImportBatch, pk=batch_id)

    try:
        validation = ingest_services.validate_batch(batch)

    except ValidationError as exc:
        messages.error(request, str(exc))
        return redirect('ingest:import_mapping', batch_id=batch.pk)

    batch.total_rows = validation['total_rows']
    batch.valid_rows = validation['valid_rows']
    batch.error_rows = validation['error_rows']
    batch.preview_json = validation['rows'][:200]

    if validation['error_rows'] == 0 and validation['valid_rows'] > 0:
        batch.status = ImportBatch.Status.VALIDATED
    else:
        batch.status = ImportBatch.Status.FAILED

    batch.save()

    can_commit = (
        batch.status == ImportBatch.Status.VALIDATED and
        not batch.job.is_locked
    )

    context = {
        'batch': batch,
        'rows': validation['rows'][:200],
        'summary': validation,
        'can_commit': can_commit,
    }

    return render(request, 'ingest/import_preview.html', context)


@login_required
@role_required('Engineer', 'Admin')
def import_commit(request, batch_id):
    if request.method != 'POST':
        return redirect('ingest:import_preview', batch_id=batch_id)

    batch = get_object_or_404(ImportBatch, pk=batch_id)

    try:
        result = ingest_services.commit_batch(batch, request.user)

        messages.success(
            request,
            f'Import complete. '
            f'{result["committed"]} new measurement(s), '
            f'{result["updated"]} updated measurement(s).'
        )

        return redirect('portal:job_detail', job_id=batch.job_id)

    except ValidationError as exc:
        messages.error(request, str(exc))
        return redirect('ingest:import_preview', batch_id=batch.pk)


# ─────────────────────────────────────────────────────────────────────────────
# OCR QUEUE
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@role_required('Engineer', 'Admin')
def ocr_list(request):
    items = OCRQueueItem.objects.select_related(
        'job',
        'test',
        'uploaded_by',
        'reviewed_by',
    ).order_by('-created_at')[:100]

    context = {
        'items': items,
    }

    return render(request, 'ingest/ocr_list.html', context)


@login_required
@role_required('Engineer', 'Admin')
def ocr_upload(request):
    if request.method == 'POST':
        form = OCRUploadForm(request.POST, request.FILES)

        if form.is_valid():
            test = form.cleaned_data['test']
            uploaded = form.cleaned_data['image']

            item = OCRQueueItem.objects.create(
                job=test.job,
                test=test,
                uploaded_by=request.user,
                status=OCRQueueItem.Status.PENDING,
            )

            item.image.save(uploaded.name, uploaded, save=True)

            ocr_services.run_ocr(item)

            if item.error_log:
                messages.warning(request, item.error_log)
            else:
                messages.success(request, 'OCR processing completed.')

            return redirect('ingest:ocr_review', item_id=item.pk)

    else:
        form = OCRUploadForm()

    context = {
        'form': form,
    }

    return render(request, 'ingest/ocr_upload.html', context)


@login_required
@role_required('Engineer', 'Admin')
def ocr_review(request, item_id):
    item = get_object_or_404(
        OCRQueueItem.objects.select_related('job', 'test'),
        pk=item_id,
    )

    parameters = Parameter.objects.all().order_by('code')

    if request.method == 'POST':

        # Run OCR again
        if 'run_ocr' in request.POST:
            ocr_services.run_ocr(item)

            if item.error_log:
                messages.warning(request, item.error_log)
            else:
                messages.success(request, 'OCR run completed.')

            return redirect('ingest:ocr_review', item_id=item.pk)

        # Re-parse edited text
        if 'reparse' in request.POST:
            item.extracted_text = request.POST.get('extracted_text', '')
            item.proposal_json = ocr_services.parse_ocr_text(
                item.extracted_text,
                item.confidence,
            )

            if item.status == OCRQueueItem.Status.PENDING:
                item.status = OCRQueueItem.Status.EXTRACTED

            item.save()

            messages.success(
                request,
                f'Re-parsed text. Found {len(item.proposal_json)} proposed row(s).'
            )

            return redirect('ingest:ocr_review', item_id=item.pk)

        # Reject OCR item
        if 'reject' in request.POST:
            item.status = OCRQueueItem.Status.REJECTED
            item.reviewed_by = request.user
            item.reviewed_at = timezone.now()
            item.save()

            messages.info(request, 'OCR item rejected.')

            return redirect('ingest:ocr_list')

        # Save one confirmed proposal row
        if 'save_row' in request.POST:
            try:
                row_index = int(request.POST.get('save_row'))
            except (TypeError, ValueError):
                messages.error(request, 'Invalid row index.')
                return redirect('ingest:ocr_review', item_id=item.pk)

            proposal = item.proposal_json or []

            if row_index < 0 or row_index >= len(proposal):
                messages.error(request, 'Invalid proposal row.')
                return redirect('ingest:ocr_review', item_id=item.pk)

            if not item.test:
                messages.error(request, 'This OCR item has no target test.')
                return redirect('ingest:ocr_review', item_id=item.pk)

            row = proposal[row_index]

            parameter_id = request.POST.get(f'row_{row_index}_parameter')
            value_raw = request.POST.get(f'row_{row_index}_value', '').strip()
            stage = request.POST.get(f'row_{row_index}_stage', 'BT')
            tap_raw = request.POST.get(f'row_{row_index}_tap', '').strip()
            phase = request.POST.get(f'row_{row_index}_phase', '').strip() or None
            confidence_raw = request.POST.get(f'row_{row_index}_confidence', '').strip()
            raw_text = request.POST.get(
                f'row_{row_index}_raw_text',
                row.get('raw_text', ''),
            )

            try:
                parameter = Parameter.objects.get(pk=parameter_id)
            except (Parameter.DoesNotExist, ValueError, TypeError):
                messages.error(request, 'Please select a valid parameter.')
                return redirect('ingest:ocr_review', item_id=item.pk)

            try:
                value = Decimal(value_raw)
            except (InvalidOperation, ValueError):
                messages.error(request, f'Value "{value_raw}" is not a valid decimal number.')
                return redirect('ingest:ocr_review', item_id=item.pk)

            tap_position = None

            if tap_raw:
                try:
                    tap_position = int(tap_raw)
                except ValueError:
                    messages.error(request, f'Tap position "{tap_raw}" is not valid.')
                    return redirect('ingest:ocr_review', item_id=item.pk)

            confidence = None

            if confidence_raw:
                try:
                    confidence = float(confidence_raw)

                    if confidence > 1.0 and confidence <= 100.0:
                        confidence = confidence / 100.0

                    confidence = max(0.0, min(1.0, confidence))

                except ValueError:
                    confidence = None

            try:
                save_measurement(
                    actor=request.user,
                    test=item.test,
                    parameter=parameter,
                    value=value,
                    stage=stage,
                    tap_position=tap_position,
                    phase=phase,
                    source=MeasurementSource.OCR,
                    raw_text=raw_text,
                    confidence=confidence,
                )

            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect('ingest:ocr_review', item_id=item.pk)

            # Update proposal row
            row['parameter_code'] = parameter.code
            row['parameter_id'] = parameter.pk
            row['value'] = str(value)
            row['stage'] = stage
            row['tap_position'] = tap_position
            row['phase'] = phase
            row['confidence'] = confidence
            row['raw_text'] = raw_text
            row['confirmed'] = True
            row['saved_by'] = request.user.username
            row['saved_at'] = timezone.now().isoformat()

            proposal[row_index] = row
            item.proposal_json = proposal

            item.reviewed_by = request.user
            item.reviewed_at = timezone.now()

            if proposal and all(r.get('confirmed') for r in proposal):
                item.status = OCRQueueItem.Status.CONFIRMED
            else:
                item.status = OCRQueueItem.Status.EXTRACTED

            item.save()

            messages.success(
                request,
                f'Saved OCR measurement: {parameter.code} = {value}.'
            )

            return redirect('ingest:ocr_review', item_id=item.pk)

    context = {
        'item': item,
        'parameters': parameters,
    }

    return render(request, 'ingest/ocr_review.html', context)
