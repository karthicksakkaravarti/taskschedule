import os
import uuid

from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

User = get_user_model()


def upload_script_to(instance, filename):
    """Generate upload path for script files."""
    return f'scripts/{instance.user.id}/{instance.id}/{filename}'


class TaskDefinition(models.Model):
    """Model to store task definitions and configurations."""

    TASK_TYPES = [
        ('background', 'Background Job'),
        ('scheduled', 'Scheduled Task'),
        ('workflow', 'Automation Workflow'),
    ]

    SCHEDULE_TYPES = [
        ('once', 'Run Once'),
        ('interval', 'Recurring Interval'),
        ('cron', 'Cron Expression'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('inactive', 'Inactive'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')

    # Basic task information
    name = models.CharField(max_length=200, help_text="Descriptive name for the task")
    description = models.TextField(blank=True, help_text="Optional description of what this task does")
    task_type = models.CharField(max_length=20, choices=TASK_TYPES, default='background')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Script information
    script_file = models.FileField(
        upload_to=upload_script_to,
        validators=[FileExtensionValidator(['py'])],
        blank=True,
        null=True,
        help_text="Upload a Python script file"
    )
    script_content = models.TextField(
        blank=True,
        help_text="Python code to execute (alternative to file upload)"
    )

    # Schedule configuration
    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_TYPES, default='once')
    schedule_value = models.CharField(
        max_length=100,
        blank=True,
        help_text="Cron expression, interval in seconds, or datetime for one-time execution"
    )

    # Environment and configuration
    environment_variables = models.TextField(
        blank=True,
        help_text="Environment variables in KEY=value format, one per line"
    )
    timeout_seconds = models.PositiveIntegerField(
        default=3600,
        help_text="Maximum execution time in seconds (default: 1 hour)"
    )
    max_retries = models.PositiveIntegerField(
        default=3,
        help_text="Maximum number of retry attempts on failure"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)

    # Statistics
    total_runs = models.PositiveIntegerField(default=0)
    successful_runs = models.PositiveIntegerField(default=0)
    failed_runs = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status', 'next_run_at']),
            models.Index(fields=['task_type']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_task_type_display()})"

    @property
    def success_rate(self):
        """Calculate the success rate percentage."""
        if self.total_runs == 0:
            return 0
        return round((self.successful_runs / self.total_runs) * 100, 1)

    def get_script_content(self):
        """Get the script content from either file or text field."""
        if self.script_file:
            try:
                with open(self.script_file.path, 'r') as f:
                    return f.read()
            except (FileNotFoundError, IOError):
                pass
        return self.script_content or ""

    def get_environment_dict(self):
        """Parse environment variables into a dictionary."""
        env_dict = {}
        if self.environment_variables:
            for line in self.environment_variables.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    env_dict[key.strip()] = value.strip()
        return env_dict


class TaskExecution(models.Model):
    """Model to store individual task execution records."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failure', 'Failure'),
        ('timeout', 'Timeout'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(TaskDefinition, on_delete=models.CASCADE, related_name='executions')

    # Execution details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    celery_task_id = models.CharField(max_length=200, blank=True, help_text="Celery task ID for tracking")

    # Timing information
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Execution results
    output = models.TextField(blank=True, help_text="Standard output from script execution")
    error_output = models.TextField(blank=True, help_text="Error output from script execution")
    exit_code = models.IntegerField(null=True, blank=True)

    # Metadata
    worker_node = models.CharField(max_length=100, blank=True, help_text="Worker node that executed the task")
    execution_time_seconds = models.FloatField(null=True, blank=True)
    memory_usage_mb = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['task', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['celery_task_id']),
        ]

    def __str__(self):
        return f"{self.task.name} - {self.created_at.strftime('%Y-%m-%d %H:%M:%S')} ({self.status})"

    @property
    def duration(self):
        """Calculate execution duration if both start and end times are available."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None

    def mark_started(self):
        """Mark the execution as started."""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at'])

    def mark_completed(self, status, output='', error_output='', exit_code=None):
        """Mark the execution as completed with results."""
        self.status = status
        self.completed_at = timezone.now()
        self.output = output
        self.error_output = error_output
        self.exit_code = exit_code

        if self.started_at:
            self.execution_time_seconds = (self.completed_at - self.started_at).total_seconds()

        self.save(update_fields=[
            'status', 'completed_at', 'output', 'error_output',
            'exit_code', 'execution_time_seconds'
        ])

        # Update task statistics
        self.task.total_runs += 1
        self.task.last_run_at = self.completed_at

        if status == 'success':
            self.task.successful_runs += 1
        else:
            self.task.failed_runs += 1

        self.task.save(update_fields=[
            'total_runs', 'successful_runs', 'failed_runs', 'last_run_at'
        ])
