"""
CSV import services.

Supported CSV shape: long-format measurement rows.

Example:

    parameter_code,stage,tap_position,phase,value
    NLL_W,BT,,,908
    I_NL_A,BT,,,1.689
    RATIO_ERR_PCT,BT,1,R,0.02

The importer maps CSV columns to these system fields:

    parameter_code
    value
    stage
    tap_position
    phase

This keeps the importer generic and avoids hard-coding lab sheet layouts.
"""

import csv
import io
import json

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Parameter,
    Measurement,
    MeasurementSource,
    AuditLog,
    AuditAction,
)

from testing.services import evaluate_all_rules_for_job
from review.services import guard_locked_write


# ─── File reading ────────────────────────────────────────────────────────────

def read_csv_text(batch):
    if not batch.file:
        raise ValidationError('No file attached to this import batch.')

    try:
        with batch.file.open('rb') as fh:
            raw = fh.read()
    except Exception as exc:
        raise ValidationError(f'Could not open uploaded file: {exc}')

    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValidationError(f'Could not decode file as UTF-8 CSV: {exc}')


def read_csv_headers(batch):
    text = read_csv_text(batch)

    reader = csv.reader(io.StringIO(text))

    try:
        headers = next(reader)
    except StopIteration:
        return []

    return [h.strip() for h in headers if h and h.strip()]


# ─── Mapping helpers ─────────────────────────────────────────────────────────

def guess_mapping(headers):
    """
    Try to automatically map common column names.
    """
    aliases = {
        'parameter_code_column': [
            'parameter_code',
            'parameter',
            'code',
            'field',
            'field_code',
            'measurement_code',
        ],
        'value_column': [
            'value',
            'reading',
            'measured',
            'measured_value',
            'measurement',
            'result',
        ],
        'stage_column': [
            'stage',
            'bt_at',
            'bt/at',
            'before_after',
        ],
        'tap_column': [
            'tap_position',
            'tap',
            'tap_no',
            'tap_number',
        ],
        'phase_column': [
            'phase',
            'ph',
        ],
    }

    mapping = {}

    normalized_headers = {
        header: header.lower().strip().replace(' ', '_')
        for header in headers
    }

    for target, possible_names in aliases.items():
        for header, normalized in normalized_headers.items():
            if normalized in possible_names:
                mapping[target] = header
                break

    return mapping


# ─── Validation / dry-run ────────────────────────────────────────────────────

def validate_batch(batch):
    """
    Parse and validate the uploaded CSV using the saved mapping.

    Returns:
        {
            'rows': [...],
            'total_rows': int,
            'valid_rows': int,
            'error_rows': int,
            'warning_rows': int,
        }
    """
    mapping = batch.mapping_json or {}

    parameter_column = mapping.get('parameter_code_column')
    value_column = mapping.get('value_column')
    stage_column = mapping.get('stage_column') or None
    tap_column = mapping.get('tap_column') or None
    phase_column = mapping.get('phase_column') or None
    default_stage = mapping.get('default_stage', 'BT')

    if not parameter_column:
        raise ValidationError('Mapping is missing the parameter code column.')

    if not value_column:
        raise ValidationError('Mapping is missing the value column.')

    if not batch.test:
        raise ValidationError('Import batch has no target test selected.')

    text = read_csv_text(batch)
    reader = csv.DictReader(io.StringIO(text))

    rows = []

    total_rows = 0
    valid_rows = 0
    error_rows = 0
    warning_rows = 0

    for raw_row in reader:
        line = reader.line_num

        row = {}

        for key, value in raw_row.items():
            if key is None:
                continue

            row[key.strip()] = (value or '').strip()

        # Skip fully blank rows
        if not any(row.values()):
            continue

        total_rows += 1

        messages = []
        has_error = False
        has_warning = False

        # Parameter code
        parameter_code = row.get(parameter_column, '').strip()
        parameter = None

        if not parameter_code:
            messages.append('ERROR: Missing parameter code.')
            has_error = True
        else:
            parameter = Parameter.objects.filter(
                code__iexact=parameter_code
            ).first()

            if not parameter:
                messages.append(f'ERROR: Unknown parameter code "{parameter_code}".')
                has_error = True

        # Value
        value_raw = row.get(value_column, '').strip()
        value = None

        if not value_raw:
            messages.append('ERROR: Missing value.')
            has_error = True
        else:
            try:
                normalized_value = value_raw.replace(',', '')
                value = Decimal(normalized_value)
            except (InvalidOperation, ValueError):
                messages.append(f'ERROR: Value "{value_raw}" is not a valid decimal number.')
                has_error = True

        # Stage
        stage = default_stage

        if stage_column:
            stage_raw = row.get(stage_column, '').strip().upper()

            if stage_raw:
                if stage_raw in ('BT', 'AT'):
                    stage = stage_raw
                else:
                    messages.append(f'ERROR: Stage "{stage_raw}" must be BT or AT.')
                    has_error = True

        # Tap position
        tap_position = None

        if tap_column:
            tap_raw = row.get(tap_column, '').strip()

            if tap_raw:
                try:
                    tap_position = int(tap_raw)

                    if tap_position <= 0:
                        messages.append(f'ERROR: Tap position "{tap_raw}" must be positive.')
                        has_error = True
                except ValueError:
                    messages.append(f'ERROR: Tap position "{tap_raw}" is not an integer.')
                    has_error = True

        # Phase
        phase = None

        if phase_column:
            phase_raw = row.get(phase_column, '').strip().upper()

            if phase_raw:
                if phase_raw in ('R', 'Y', 'B'):
                    phase = phase_raw
                else:
                    messages.append(f'ERROR: Phase "{phase_raw}" must be R, Y, or B.')
                    has_error = True

        # Optional warning: parameter belongs to another test type
        if (
            parameter and
            batch.test and
            parameter.test_type_id and
            parameter.test_type_id != batch.test.test_type_id
        ):
            messages.append(
                f'WARNING: Parameter "{parameter.code}" normally belongs to '
                f'{parameter.test_type.code}, not {batch.test.test_type.code}.'
            )
            has_warning = True

        if has_error:
            status = 'error'
            error_rows += 1
        elif has_warning:
            status = 'warning'
            warning_rows += 1
            valid_rows += 1
        else:
            status = 'ok'
            valid_rows += 1

        rows.append({
            'line': line,
            'parameter_code': parameter_code,
            'parameter_id': parameter.pk if parameter else None,
            'value': str(value) if value is not None else None,
            'stage': stage,
            'tap_position': tap_position,
            'phase': phase,
            'status': status,
            'messages': messages,
            'raw': row,
        })

    return {
        'rows': rows,
        'total_rows': total_rows,
        'valid_rows': valid_rows,
        'error_rows': error_rows,
        'warning_rows': warning_rows,
    }


# ─── Commit / write to database ─────────────────────────────────────────────

@transaction.atomic
def commit_batch(batch, actor):
    """
    Commit valid CSV rows into Measurement rows.

    Uses:
        source = IMPORT

    After commit:
        - AuditLog entries are written
        - rules engine re-evaluates PASS/FAIL
    """
    if batch.status == ImportBatch.Status.COMMITTED:
        raise ValidationError('This import batch has already been committed.')

    if batch.job.is_locked:
        raise ValidationError(
            f'Job {batch.job.test_series_no} is locked. Import is not allowed.'
        )

    if not batch.test:
        raise ValidationError('Import batch has no target test.')

    guard_locked_write(batch.job)

    validation = validate_batch(batch)

    if validation['error_rows'] > 0:
        raise ValidationError('Fix validation errors before committing.')

    if validation['valid_rows'] == 0:
        raise ValidationError('No valid rows found in the CSV file.')

    committed_count = 0
    updated_count = 0

    for row in validation['rows']:
        if row['status'] == 'error':
            continue

        parameter = Parameter.objects.get(pk=row['parameter_id'])
        value = Decimal(row['value'])

        filters = {
            'test': batch.test,
            'parameter': parameter,
            'stage': row['stage'],
            'tap_position': row['tap_position'],
            'phase': row['phase'],
        }

        raw_text = json.dumps(row.get('raw', {}), ensure_ascii=False)

        existing = Measurement.objects.filter(**filters).order_by('-id').first()

        if existing:
            old_value = str(existing.value)

            existing.value = value
            existing.unit = parameter.unit
            existing.source = MeasurementSource.IMPORT
            existing.raw_text = raw_text
            existing.captured_by = actor
            existing.save()

            AuditLog.objects.create(
                actor=actor,
                entity='Measurement',
                entity_id=existing.pk,
                action=AuditAction.UPDATE,
                field=parameter.code,
                old_value=old_value,
                new_value=str(value),
            )

            updated_count += 1

        else:
            measurement = Measurement.objects.create(
                test=batch.test,
                parameter=parameter,
                stage=row['stage'],
                tap_position=row['tap_position'],
                phase=row['phase'],
                value=value,
                unit=parameter.unit,
                raw_text=raw_text,
                source=MeasurementSource.IMPORT,
                captured_by=actor,
            )

            AuditLog.objects.create(
                actor=actor,
                entity='Measurement',
                entity_id=measurement.pk,
                action=AuditAction.CREATE,
                field=parameter.code,
                old_value='',
                new_value=str(value),
            )

            committed_count += 1

    batch.status = ImportBatch.Status.COMMITTED
    batch.total_rows = validation['total_rows']
    batch.valid_rows = validation['valid_rows']
    batch.error_rows = validation['error_rows']
    batch.preview_json = validation['rows'][:200]
    batch.error_log = ''
    batch.save()

    AuditLog.objects.create(
        actor=actor,
        entity='ImportBatch',
        entity_id=batch.pk,
        action=AuditAction.TRANSITION,
        field='status',
        old_value=str(ImportBatch.Status.VALIDATED),
        new_value=str(ImportBatch.Status.COMMITTED),
    )

    # Recompute verdicts once after the whole import
    evaluate_all_rules_for_job(batch.job)

    return {
        'committed': committed_count,
        'updated': updated_count,
        'total': validation['total_rows'],
        'valid': validation['valid_rows'],
    }
