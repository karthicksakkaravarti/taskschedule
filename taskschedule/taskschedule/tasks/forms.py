import re

from django import forms
from django.core.exceptions import ValidationError

from .models import TaskDefinition


class TaskSubmissionForm(forms.ModelForm):
    """Form for submitting new tasks from the landing page."""

    class Meta:
        model = TaskDefinition
        fields = [
            'name', 'task_type', 'script_file', 'script_content',
            'schedule_type', 'schedule_value', 'environment_variables'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'My Data Processing Task'
            }),
            'task_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'script_file': forms.FileInput(attrs={
                'class': 'sr-only',
                'accept': '.py'
            }),
            'script_content': forms.Textarea(attrs={
                'class': 'form-control font-mono text-sm',
                'rows': 8,
                'placeholder': '''# Paste your Python code here
import pandas as pd
import requests

def main():
    # Your code here
    print('Hello, TaskSchedule!')

if __name__ == '__main__':
    main()'''
            }),
            'schedule_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'schedule_value': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '0 9 * * 1-5 (weekdays at 9 AM)'
            }),
            'environment_variables': forms.Textarea(attrs={
                'class': 'form-control font-mono text-sm',
                'rows': 3,
                'placeholder': '''API_KEY=your_api_key_here
DATABASE_URL=postgresql://user:pass@host:port/db
DEBUG=True'''
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Make fields required as needed
        self.fields['name'].required = True
        self.fields['task_type'].required = True

    def clean(self):
        cleaned_data = super().clean()
        script_file = cleaned_data.get('script_file')
        script_content = cleaned_data.get('script_content')

        # Ensure either script_file or script_content is provided
        if not script_file and not script_content:
            raise ValidationError(
                "Please provide either a Python script file or paste your code."
            )

        # Validate schedule_value based on schedule_type
        schedule_type = cleaned_data.get('schedule_type')
        schedule_value = cleaned_data.get('schedule_value')

        if schedule_type and schedule_value:
            if schedule_type == 'cron':
                if not self._validate_cron_expression(schedule_value):
                    raise ValidationError({
                        'schedule_value': 'Invalid cron expression format.'
                    })
            elif schedule_type == 'interval':
                try:
                    interval = int(schedule_value)
                    if interval <= 0:
                        raise ValueError()
                except ValueError:
                    raise ValidationError({
                        'schedule_value': 'Interval must be a positive integer (seconds).'
                    })

        return cleaned_data

    def _validate_cron_expression(self, cron_expr):
        """Basic validation for cron expressions."""
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return False

        # Basic regex patterns for each cron field
        patterns = [
            r'^(\*|[0-5]?\d)$',  # minute (0-59)
            r'^(\*|[01]?\d|2[0-3])$',  # hour (0-23)
            r'^(\*|[12]?\d|3[01])$',  # day of month (1-31)
            r'^(\*|[01]?\d)$',  # month (1-12)
            r'^(\*|[0-6])$',  # day of week (0-6)
        ]

        for i, part in enumerate(parts):
            # Allow ranges, lists, and step values
            if ',' in part or '-' in part or '/' in part:
                continue
            if not re.match(patterns[i], part):
                return False

        return True

    def save(self, commit=True):
        task = super().save(commit=False)
        if self.user:
            task.user = self.user

        # Set default status
        task.status = 'draft'

        if commit:
            task.save()
        return task


class TaskUpdateForm(forms.ModelForm):
    """Form for updating existing tasks."""

    class Meta:
        model = TaskDefinition
        fields = [
            'name', 'description', 'status', 'script_content',
            'schedule_type', 'schedule_value', 'environment_variables',
            'timeout_seconds', 'max_retries'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'script_content': forms.Textarea(attrs={
                'class': 'form-control font-mono text-sm',
                'rows': 15
            }),
            'schedule_type': forms.Select(attrs={'class': 'form-control'}),
            'schedule_value': forms.TextInput(attrs={'class': 'form-control'}),
            'environment_variables': forms.Textarea(attrs={
                'class': 'form-control font-mono text-sm',
                'rows': 5
            }),
            'timeout_seconds': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_retries': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class TaskExecuteForm(forms.Form):
    """Simple form for manually executing a task."""

    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="I confirm that I want to execute this task now"
    )
