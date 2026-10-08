"""
Validation & Rules Engine.

This module:
  - saves measurements through a controlled service layer
  - writes audit logs
  - evaluates limit rules
  - produces PASS/FAIL results
  - flags BT/AT anomalies
"""

from decimal import Decimal

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import (
    Measurement,
    MeasurementSource,
    LimitRule,
    Result,
    Job,
    Comparator,
    Verdict,
    MeasurementStage,
    AuditLog,
    AuditAction,
)

from review.services import guard_locked_write


# ─── Rule evaluation ─────────────────────────────────────────────────────────

def evaluate_limit_rule(job: Job, rule: LimitRule) -> Result:
    """
    Evaluate one LimitRule against the latest relevant measurement.
    """
    measurements = Measurement.objects.filter(
        test__job=job,
        parameter=rule.parameter,
    ).order_by('-captured_at', '-id')

    if not measurements.exists():
        return Result(
            job=job,
            rule=rule,
            measured=None,
            limit=rule.limit_value,
            verdict=Verdict.NA,
            note='No measurement found for this parameter.',
        )

    measured = measurements.first().value

    if measured is None:
        return Result(
            job=job,
            rule=rule,
            measured=None,
            limit=rule.limit_value,
            verdict=Verdict.NA,
            note='Measurement value is empty.',
        )

    passed = _compare(measured, rule.limit_value, rule.comparator)

    return Result(
        job=job,
        rule=rule,
        measured=measured,
        limit=rule.limit_value,
        verdict=Verdict.PASS if passed else Verdict.FAIL,
        note=(
            f'{rule.standard} {rule.clause}: '
            f'{measured} {rule.get_comparator_display()} {rule.limit_value}'
        ),
    )


def evaluate_all_rules_for_job(job: Job):
    """
    Re-evaluate all rules for a job.
    Called after every measurement save.
    """
    rules = LimitRule.objects.select_related('parameter').all()
    results = []

    for rule in rules:
        result = evaluate_limit_rule(job, rule)

        Result.objects.filter(job=job, rule=rule).delete()
        result.save()

        results.append(result)

    return results


def _compare(value: Decimal, limit: Decimal, comparator: str) -> bool:
    if comparator == Comparator.LE:
        return value <= limit

    if comparator == Comparator.LT:
        return value < limit

    if comparator == Comparator.GE:
        return value >= limit

    if comparator == Comparator.GT:
        return value > limit

    if comparator == Comparator.WITHIN:
        return abs(value) <= limit

    return False


# ─── Controlled measurement saving ───────────────────────────────────────────

@transaction.atomic
def save_measurement(
    actor,
    test,
    parameter,
    value,
    stage=MeasurementStage.BT,
    tap_position=None,
    phase=None,
    source=MeasurementSource.MANUAL,
    raw_text=None,
    confidence=None,
):
    """
    Controlled write path for measurements.

    This enforces:
      - lock protection
      - typed values
      - audit logging
      - automatic re-evaluation of verdicts
    """
    guard_locked_write(test.job)

    if value is None:
        raise ValidationError('Measurement value is required.')

    if phase == '':
        phase = None

    if tap_position == '':
        tap_position = None

    filters = {
        'test': test,
        'parameter': parameter,
        'stage': stage,
        'tap_position': tap_position,
        'phase': phase,
    }

    existing = Measurement.objects.filter(**filters).order_by('-id').first()

    if existing:
        old_value = str(existing.value)

        existing.value = value
        existing.unit = parameter.unit
        existing.source = source
        existing.raw_text = raw_text
        existing.confidence = confidence
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

        measurement = existing

    else:
        measurement = Measurement.objects.create(
            test=test,
            parameter=parameter,
            stage=stage,
            tap_position=tap_position,
            phase=phase,
            value=value,
            unit=parameter.unit,
            raw_text=raw_text,
            source=source,
            confidence=confidence,
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

    # Recompute verdicts after every save
    evaluate_all_rules_for_job(test.job)

    return measurement


# ─── AI Touch #3: BT/AT anomaly detection ────────────────────────────────────

def check_bt_at_anomaly(job: Job, threshold_pct: Decimal = Decimal('10.0')):
    """
    Flags BT/AT drift beyond threshold percentage.
    """
    anomalies = []

    tests = job.tests.all()

    for test in tests:
        bt_parameter_ids = set(
            test.measurements.filter(stage=MeasurementStage.BT)
            .values_list('parameter_id', flat=True)
        )

        for parameter_id in bt_parameter_ids:
            bt_values = test.measurements.filter(
                parameter_id=parameter_id,
                stage=MeasurementStage.BT,
            ).order_by('-id')

            at_values = test.measurements.filter(
                parameter_id=parameter_id,
                stage=MeasurementStage.AT,
            ).order_by('-id')

            if not bt_values.exists() or not at_values.exists():
                continue

            bt = bt_values.first()
            at = at_values.first()

            if bt.value is None or at.value is None:
                continue

            if bt.value == 0:
                continue

            drift_pct = abs((at.value - bt.value) / bt.value) * Decimal('100.0')

            if drift_pct > threshold_pct:
                anomalies.append(
                    {
                        'test': test,
                        'parameter': bt.parameter,
                        'bt_value': bt.value,
                        'at_value': at.value,
                        'drift_pct': drift_pct,
                    }
                )

    return anomalies
