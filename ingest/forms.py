from django import forms

from core.models import Test, MeasurementStage

from .models import ImportBatch


class ImportStartForm(forms.Form):
    """
    Step 1:
      - select target test
      - upload CSV file
    """

    test = forms.ModelChoiceField(
        queryset=Test.objects.select_related(
            'job',
            'test_type',
        ).order_by('-id'),
        label='Target Job / Test',
    )

    file = forms.FileField(
        label='CSV File',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['test'].widget.attrs.update({
            'class': 'form-select',
        })

        self.fields['file'].widget.attrs.update({
            'class': 'form-control',
        })

    def clean_file(self):
        uploaded = self.cleaned_data.get('file')

        if not uploaded:
            raise forms.ValidationError('Please upload a CSV file.')

        if not uploaded.name.lower().endswith('.csv'):
            raise forms.ValidationError('Only .csv files are supported in this prototype.')

        return uploaded

    def clean(self):
        cleaned_data = super().clean()

        test = cleaned_data.get('test')

        if test and test.job.is_locked:
            raise forms.ValidationError(
                f'Job {test.job.test_series_no} is locked. Import is not allowed.'
            )

        return cleaned_data


class MappingForm(forms.Form):
    """
    Step 2:
      - map CSV columns to ATRG fields
    """

    parameter_code_column = forms.ChoiceField(
        label='Parameter Code Column *',
    )

    value_column = forms.ChoiceField(
        label='Value Column *',
    )

    stage_column = forms.ChoiceField(
        label='Stage Column (BT/AT)',
        required=False,
    )

    tap_column = forms.ChoiceField(
        label='Tap Position Column',
        required=False,
    )

    phase_column = forms.ChoiceField(
        label='Phase Column',
        required=False,
    )

    default_stage = forms.ChoiceField(
        label='Default Stage',
        choices=MeasurementStage.choices,
        initial=MeasurementStage.BT,
    )

    def __init__(self, *args, headers=None, initial_mapping=None, **kwargs):
        super().__init__(*args, **kwargs)

        headers = headers or []
        initial_mapping = initial_mapping or {}

        choices = [('', '— not mapped —')] + [(h, h) for h in headers]

        field_names = [
            'parameter_code_column',
            'value_column',
            'stage_column',
            'tap_column',
            'phase_column',
        ]

        for field_name in field_names:
            self.fields[field_name].choices = choices
            self.fields[field_name].widget.attrs.update({
                'class': 'form-select',
            })

            if field_name in initial_mapping:
                self.fields[field_name].initial = initial_mapping.get(field_name)

        self.fields['default_stage'].widget.attrs.update({
            'class': 'form-select',
        })

        if 'default_stage' in initial_mapping:
            self.fields['default_stage'].initial = initial_mapping.get('default_stage')

    def clean(self):
        cleaned_data = super().clean()

        if not cleaned_data.get('parameter_code_column'):
            self.add_error(
                'parameter_code_column',
                'Please map the parameter code column.',
            )

        if not cleaned_data.get('value_column'):
            self.add_error(
                'value_column',
                'Please map the value column.',
            )

        return cleaned_data


class OCRUploadForm(forms.Form):
    """
    Upload a scanned logsheet image for OCR-assisted review.
    """

    test = forms.ModelChoiceField(
        queryset=Test.objects.select_related(
            'job',
            'test_type',
        ).order_by('-id'),
        label='Target Job / Test',
    )

    image = forms.ImageField(
        label='Scan Image',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['test'].widget.attrs.update({
            'class': 'form-select',
        })

        self.fields['image'].widget.attrs.update({
            'class': 'form-control',
        })

    def clean(self):
        cleaned_data = super().clean()

        test = cleaned_data.get('test')

        if test and test.job.is_locked:
            raise forms.ValidationError(
                f'Job {test.job.test_series_no} is locked. '
                f'OCR-assisted entry is not allowed.'
            )

        return cleaned_data
