"""
OCR assistance service.

This is intentionally human-in-the-loop.

OCR does NOT silently write measurements.

It produces:
    - extracted_text
    - confidence
    - proposal_json

The engineer then confirms each proposed row.
"""

import re
from decimal import Decimal, InvalidOperation

from core.models import Parameter

from .models import OCRQueueItem


# ─── Simple parameter recognition patterns ───────────────────────────────────
#
# These patterns are deliberately simple and transparent.
# They are enough for demo logsheets and can be replaced later with
# a stronger vision model or layout-aware parser.

PARAMETER_PATTERNS = [
    (
        r'no[-\s]?load loss|no load loss|nll',
        'NLL_W',
        'No-load loss',
    ),
    (
        r'no[-\s]?load current|no load current|magnetizing current',
        'I_NL_A',
        'No-load current',
    ),
    (
        r'total loss.*100|total loss at 100|total loss 100',
        'TOTAL_LOSS_100',
        'Total loss at 100%',
    ),
    (
        r'total loss.*50|total loss at 50',
        'TOTAL_LOSS_50',
        'Total loss at 50%',
    ),
    (
        r'load loss.*75|llc.*75|corrected.*75',
        'LLC_W75',
        'Load loss corrected to 75°C',
    ),
    (
        r'hv.*resistance|resistance.*hv',
        'R_HV_OHM',
        'HV winding resistance',
    ),
    (
        r'lv.*resistance|resistance.*lv',
        'R_LV_OHM',
        'LV winding resistance',
    ),
    (
        r'top oil',
        'TOP_OIL_C',
        'Top oil temperature',
    ),
    (
        r'hv.*rise|winding rise.*hv',
        'HV_RISE_C',
        'HV winding temperature rise',
    ),
    (
        r'lv.*rise|winding rise.*lv',
        'LV_RISE_C',
        'LV winding temperature rise',
    ),
    (
        r'ratio error|voltage ratio error',
        'RATIO_ERR_PCT',
        'Voltage ratio error',
    ),
]


# ─── OCR execution ───────────────────────────────────────────────────────────

def run_ocr(item: OCRQueueItem):
    """
    Attempt OCR on the uploaded image.

    If pytesseract/Tesseract is unavailable, fall back to manual-assist mode.
    """
    item.error_log = ''

    try:
        import pytesseract
        from PIL import Image

    except ImportError:
        item.status = OCRQueueItem.Status.EXTRACTED
        item.confidence = None
        item.error_log = (
            'pytesseract/Pillow is not installed. '
            'Paste the text manually and click Re-parse.'
        )
        item.proposal_json = parse_ocr_text(
            item.extracted_text,
            item.confidence,
        )
        item.save()
        return

    try:
        img = Image.open(item.image.path)
        img.load()

        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        text = pytesseract.image_to_string(img)

        # Try to compute average word confidence
        confidence = None

        try:
            data = pytesseract.image_to_data(
                img,
                output_type=pytesseract.Output.DICT,
            )

            confidences = []

            for conf in data.get('conf', []):
                try:
                    value = float(conf)
                    if value > 0:
                        confidences.append(value)
                except (TypeError, ValueError):
                    continue

            if confidences:
                confidence = sum(confidences) / len(confidences) / 100.0

        except Exception:
            confidence = None

        item.extracted_text = text.strip()
        item.confidence = confidence
        item.proposal_json = parse_ocr_text(text, confidence)
        item.status = OCRQueueItem.Status.EXTRACTED

    except Exception as exc:
        item.status = OCRQueueItem.Status.EXTRACTED
        item.error_log = (
            f'OCR failed: {exc}. '
            f'Paste the text manually and click Re-parse.'
        )
        item.proposal_json = parse_ocr_text(
            item.extracted_text,
            item.confidence,
        )

    item.save()


# ─── Text parsing ────────────────────────────────────────────────────────────

def parse_ocr_text(text, confidence=None):
    """
    Very lightweight line-based parser.

    It looks for known parameter phrases and extracts a numeric value
    from the same line.
    """
    proposals = []

    if not text:
        return proposals

    lines = text.splitlines()

    for line in lines:
        line = line.strip()

        if not line:
            continue

        low = line.lower()

        for pattern, parameter_code, label in PARAMETER_PATTERNS:
            if re.search(pattern, low):
                value = extract_number(line, parameter_code)

                if value is None:
                    continue

                parameter = Parameter.objects.filter(
                    code=parameter_code
                ).first()

                proposals.append({
                    'parameter_code': parameter_code,
                    'parameter_id': parameter.pk if parameter else None,
                    'label': label,
                    'value': str(value),
                    'unit': parameter.unit if parameter else '',
                    'stage': guess_stage(line),
                    'tap_position': guess_tap(line),
                    'phase': guess_phase(line),
                    'confidence': confidence,
                    'raw_text': line,
                    'confirmed': False,
                })

                # Only match first parameter pattern per line
                break

    return proposals


def extract_number(line, parameter_code):
    """
    Extract a likely numeric measurement value from a line.

    Rules:
      - ignore percentage values unless the parameter itself is percentage-based
      - return the last remaining candidate number
    """
    normalized = line.replace(',', '')

    matches = re.finditer(
        r'([-+]?\d+(?:\.\d+)?)\s*(%?)',
        normalized,
    )

    candidates = []

    percentage_allowed_parameters = (
        'RATIO_ERR_PCT',
        'I_NL_PCT',
    )

    for match in matches:
        raw_number = match.group(1)
        is_percentage = match.group(2) == '%'

        try:
            value = Decimal(raw_number)
        except InvalidOperation:
            continue

        if is_percentage and parameter_code not in percentage_allowed_parameters:
            continue

        candidates.append(value)

    if not candidates:
        return None

    return candidates[-1]


def guess_stage(line):
    """
    Guess BT/AT stage from text.
    """
    if re.search(r'\bAT\b', line) or 'after' in line.lower():
        return 'AT'

    return 'BT'


def guess_tap(line):
    """
    Guess tap position from text.
    """
    match = re.search(
        r'tap\s*(?:no|number|position)?\s*[:#\-]?\s*(\d+)',
        line.lower(),
    )

    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None

    return None


def guess_phase(line):
    """
    Guess phase R/Y/B from text.
    """
    match = re.search(
        r'phase\s*[:#\-]?\s*([RYB])',
        line.upper(),
    )

    if match:
        return match.group(1)

    return None
