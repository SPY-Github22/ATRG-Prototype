from django import forms

from core.models import (
    Parameter,
    MeasurementStage,
    Phase,
    RequestType,
    EquipmentType,
)


# ─────────────────────────────────────────────────────────────────────────────
# Engineer measurement entry forms
# ─────────────────────────────────────────────────────────────────────────────

class MeasurementForm(forms.Form):
    """
    Generic measurement entry form.
    """

    parameter = forms.ModelChoiceField(
        queryset=Parameter.objects.none(),
        empty_label='Select parameter',
    )

    stage = forms.ChoiceField(
        choices=MeasurementStage.choices,
        initial=MeasurementStage.BT,
    )

    tap_position = forms.IntegerField(
        required=False,
        min_value=1,
        label='Tap Position',
    )

    phase = forms.ChoiceField(
        choices=[('', '—')] + list(Phase.choices),
        required=False,
    )

    value = forms.DecimalField(
        max_digits=12,
        decimal_places=4,
        label='Measured Value',
    )

    def __init__(self, *args, test_type=None, **kwargs):
        super().__init__(*args, **kwargs)

        if test_type:
            self.fields['parameter'].queryset = Parameter.objects.filter(
                test_type=test_type
            ).order_by('code')

        self.fields['parameter'].widget.attrs.update({'class': 'form-select'})
        self.fields['stage'].widget.attrs.update({'class': 'form-select'})
        self.fields['tap_position'].widget.attrs.update({'class': 'form-control'})
        self.fields['phase'].widget.attrs.update({'class': 'form-select'})
        self.fields['value'].widget.attrs.update({
            'class': 'form-control',
            'step': '0.0001',
        })


class RatioGridForm(forms.Form):
    """
    Routine test ratio-error grid:
      taps x phases
    """

    stage = forms.ChoiceField(
        choices=MeasurementStage.choices,
        initial=MeasurementStage.BT,
        label='BT/AT',
    )

    def __init__(self, *args, taps=7, **kwargs):
        super().__init__(*args, **kwargs)

        self.taps = taps
        self.phases = [code for code, _ in Phase.choices]

        self.fields['stage'].widget.attrs.update({'class': 'form-select'})

        for tap in range(1, taps + 1):
            for phase in self.phases:
                field_name = f'ratio_{tap}_{phase}'

                self.fields[field_name] = forms.DecimalField(
                    max_digits=12,
                    decimal_places=4,
                    required=False,
                    label=f'Tap {tap} {phase}',
                    widget=forms.NumberInput(attrs={
                        'class': 'form-control form-control-sm',
                        'step': '0.0001',
                    }),
                )


# ─────────────────────────────────────────────────────────────────────────────
# Customer request form
# ─────────────────────────────────────────────────────────────────────────────

class CustomerRequestForm(forms.Form):
    """
    Customer self-entry request form.

    Creates:
      - Job in REQUESTED state
      - provisional sample record
    """

    request_type = forms.ChoiceField(
        choices=RequestType.choices,
        initial=RequestType.TYPE,
        label='Request Type',
    )

    equipment_type = forms.ChoiceField(
        choices=EquipmentType.choices,
        initial=EquipmentType.TRANSFORMER,
        label='Equipment Type',
    )

    standard = forms.CharField(
        max_length=100,
        initial='IS 1180',
        label='Standard',
    )

    eel_level = forms.CharField(
        max_length=20,
        required=False,
        initial='EEL-1',
        label='Energy Efficiency Level',
    )

    rating_kva = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        label='Rating (kVA)',
    )

    hv_v = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        label='HV Voltage (V)',
    )

    lv_v = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        label='LV Voltage (V)',
    )

    frequency_hz = forms.DecimalField(
        max_digits=6,
        decimal_places=1,
        initial=50.0,
        label='Frequency (Hz)',
    )

    vector_group = forms.CharField(
        max_length=20,
        required=False,
        initial='Dyn11',
        label='Vector Group',
    )

    serial_no = forms.CharField(
        max_length=100,
        required=False,
        label='Serial Number',
    )

    description = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        label='Additional Details',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name in self.fields:
            field = self.fields[field_name]

            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({'class': 'form-select'})
            else:
                field.widget.attrs.update({'class': 'form-control'})

class SCShotForm(forms.Form):
    """
    Quick entry for short-circuit test shots.

    Shot number is stored using Measurement.tap_position.
    """

    shot_no = forms.IntegerField(
        min_value=1,
        initial=1,
        label='Shot No',
    )

    phase = forms.ChoiceField(
        choices=[('', '—')] + list(Phase.choices),
        required=False,
        label='Phase',
    )

    stage = forms.ChoiceField(
        choices=MeasurementStage.choices,
        initial=MeasurementStage.AT,
        label='Stage',
    )

    applied_kv = forms.DecimalField(
        max_digits=12,
        decimal_places=4,
        required=False,
        label='Applied Voltage (kV)',
    )

    peak_current_ka = forms.DecimalField(
        max_digits=12,
        decimal_places=4,
        required=False,
        label='Peak Current (kA)',
    )

    rms_current_ka = forms.DecimalField(
        max_digits=12,
        decimal_places=4,
        required=False,
        label='RMS Current (kA)',
    )

    duration_s = forms.DecimalField(
        max_digits=12,
        decimal_places=4,
        required=False,
        label='Duration (s)',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['shot_no'].widget.attrs.update({'class': 'form-control'})
        self.fields['phase'].widget.attrs.update({'class': 'form-select'})
        self.fields['stage'].widget.attrs.update({'class': 'form-select'})
        self.fields['applied_kv'].widget.attrs.update({
            'class': 'form-control',
            'step': '0.0001',
        })
        self.fields['peak_current_ka'].widget.attrs.update({
            'class': 'form-control',
            'step': '0.0001',
        })
        self.fields['rms_current_ka'].widget.attrs.update({
            'class': 'form-control',
            'step': '0.0001',
        })
        self.fields['duration_s'].widget.attrs.update({
            'class': 'form-control',
            'step': '0.0001',
        })

    def clean(self):
        cleaned_data = super().clean()

        value_fields = [
            'applied_kv',
            'peak_current_ka',
            'rms_current_ka',
            'duration_s',
        ]

        has_value = any(
            cleaned_data.get(field) is not None
            for field in value_fields
        )

        if not has_value:
            raise forms.ValidationError(
                'Enter at least one short-circuit measurement value.'
            )

        return cleaned_data


class TempRiseQuickForm(forms.Form):
    """
    Quick entry for temperature-rise readings.

    Hour / reading number is stored using Measurement.tap_position.
    """

    hour = forms.IntegerField(
        required=False,
        min_value=1,
        label='Hour / Reading No',
    )

    stage = forms.ChoiceField(
        choices=MeasurementStage.choices,
        initial=MeasurementStage.AT,
        label='Stage',
    )

    top_oil_c = forms.DecimalField(
        max_digits=12,
        decimal_places=4,
        required=False,
        label='Top Oil Temperature (°C)',
    )

    ambient_c = forms.DecimalField(
        max_digits=12,
        decimal_places=4,
        required=False,
        label='Ambient Temperature (°C)',
    )

    hv_rise_c = forms.DecimalField(
        max_digits=12,
        decimal_places=4,
        required=False,
        label='HV Winding Rise (°C)',
    )

    lv_rise_c = forms.DecimalField(
        max_digits=12,
        decimal_places=4,
        required=False,
        label='LV Winding Rise (°C)',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['hour'].widget.attrs.update({'class': 'form-control'})
        self.fields['stage'].widget.attrs.update({'class': 'form-select'})
        self.fields['top_oil_c'].widget.attrs.update({
            'class': 'form-control',
            'step': '0.0001',
        })
        self.fields['ambient_c'].widget.attrs.update({
            'class': 'form-control',
            'step': '0.0001',
        })
        self.fields['hv_rise_c'].widget.attrs.update({
            'class': 'form-control',
            'step': '0.0001',
        })
        self.fields['lv_rise_c'].widget.attrs.update({
            'class': 'form-control',
            'step': '0.0001',
        })

    def clean(self):
        cleaned_data = super().clean()

        value_fields = [
            'top_oil_c',
            'ambient_c',
            'hv_rise_c',
            'lv_rise_c',
        ]

        has_value = any(
            cleaned_data.get(field) is not None
            for field in value_fields
        )

        if not has_value:
            raise forms.ValidationError(
                'Enter at least one temperature-rise value.'
            )

        return cleaned_data


class OilPressureQuickForm(forms.Form):
    """
    Quick entry for oil/pressure test.
    """

    stage = forms.ChoiceField(
        choices=MeasurementStage.choices,
        initial=MeasurementStage.AT,
        label='Stage',
    )

    pressure_kpa = forms.DecimalField(
        max_digits=12,
        decimal_places=4,
        required=False,
        label='Test Pressure (kPa)',
    )

    leakage = forms.ChoiceField(
        choices=[
            ('', '—'),
            ('0', 'No leakage'),
            ('1', 'Leakage observed'),
        ],
        required=False,
        label='Leakage Result',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['stage'].widget.attrs.update({'class': 'form-select'})
        self.fields['pressure_kpa'].widget.attrs.update({
            'class': 'form-control',
            'step': '0.0001',
        })
        self.fields['leakage'].widget.attrs.update({'class': 'form-select'})

    def clean(self):
        cleaned_data = super().clean()

        has_pressure = cleaned_data.get('pressure_kpa') is not None
        has_leakage = cleaned_data.get('leakage') not in (None, '')

        if not has_pressure and not has_leakage:
            raise forms.ValidationError(
                'Enter pressure or leakage result.'
            )

        return cleaned_data
