import os
import subprocess
import sys
import tempfile

from celery import shared_task
from django.utils import timezone

from .models import TaskExecution


@shared_task(bind=True)
def execute_python_script(self, execution_id):
    """
    Execute a Python script for a given TaskExecution.

    Args:
        execution_id: UUID of the TaskExecution instance

    Returns:
        dict: Execution results with status, output, error_output, etc.
    """
    try:
        execution = TaskExecution.objects.get(id=execution_id)
        task = execution.task

        # Mark execution as started
        execution.mark_started()

        # Get script content
        script_content = task.get_script_content()
        if not script_content:
            raise ValueError("No script content found")

        # Get environment variables
        env_vars = task.get_environment_dict()

        # Create a temporary file for the script
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False
        ) as script_file:
            script_file.write(script_content)
            script_path = script_file.name

        try:
            # Prepare environment
            exec_env = os.environ.copy()
            exec_env.update(env_vars)

            # Execute the script
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=task.timeout_seconds,
                env=exec_env,
                cwd=tempfile.gettempdir()
            )

            # Determine status based on exit code
            if result.returncode == 0:
                status = 'success'
            else:
                status = 'failure'

            # Mark execution as completed
            execution.mark_completed(
                status=status,
                output=result.stdout,
                error_output=result.stderr,
                exit_code=result.returncode
            )

            return {
                'status': status,
                'output': result.stdout,
                'error_output': result.stderr,
                'exit_code': result.returncode,
                'execution_time_seconds': execution.execution_time_seconds
            }

        except subprocess.TimeoutExpired:
            execution.mark_completed(
                status='timeout',
                error_output=f'Script execution timed out after {task.timeout_seconds} seconds'
            )
            return {
                'status': 'timeout',
                'error_output': f'Script execution timed out after {task.timeout_seconds} seconds'
            }

        except Exception as e:
            execution.mark_completed(
                status='failure',
                error_output=f'Execution error: {str(e)}'
            )
            return {
                'status': 'failure',
                'error_output': f'Execution error: {str(e)}'
            }

        finally:
            # Clean up temporary script file
            try:
                os.unlink(script_path)
            except OSError:
                pass

    except TaskExecution.DoesNotExist:
        return {
            'status': 'failure',
            'error_output': f'TaskExecution with id {execution_id} not found'
        }
    except Exception as e:
        return {
            'status': 'failure',
            'error_output': f'Unexpected error: {str(e)}'
        }


@shared_task
def schedule_periodic_tasks():
    """
    Celery beat task to schedule periodic tasks based on their schedule configuration.
    This should be called regularly (e.g., every minute) by Celery Beat.
    """
    from .models import TaskDefinition

    now = timezone.now()

    # Find tasks that are due for execution
    due_tasks = TaskDefinition.objects.filter(
        status='active',
        next_run_at__lte=now
    )

    for task in due_tasks:
        # Create a new execution
        execution = TaskExecution.objects.create(task=task)

        # Queue for execution
        result = execute_python_script.delay(execution.id)
        execution.celery_task_id = result.id
        execution.save(update_fields=['celery_task_id'])

        # Update next run time based on schedule
        task.next_run_at = calculate_next_run_time(task)
        task.save(update_fields=['next_run_at'])


def calculate_next_run_time(task):
    """
    Calculate the next run time for a task based on its schedule configuration.

    Args:
        task: TaskDefinition instance

    Returns:
        datetime: Next scheduled run time, or None if task shouldn't repeat
    """
    import re
    from datetime import timedelta

    now = timezone.now()

    if task.schedule_type == 'once':
        return None  # One-time tasks don't repeat

    elif task.schedule_type == 'interval':
        try:
            interval_seconds = int(task.schedule_value)
            return now + timedelta(seconds=interval_seconds)
        except (ValueError, TypeError):
            return None

    elif task.schedule_type == 'cron':
        # For cron expressions, we'd need a more sophisticated library
        # like croniter. For now, return a default interval
        # TODO: Implement proper cron parsing
        return now + timedelta(hours=1)

    return None


@shared_task
def cleanup_old_executions():
    """
    Clean up old task execution records to prevent database bloat.
    Keep executions from the last 30 days by default.
    """
    from datetime import timedelta

    cutoff_date = timezone.now() - timedelta(days=30)

    # Delete old execution records
    deleted_count = TaskExecution.objects.filter(
        created_at__lt=cutoff_date
    ).delete()[0]

    return f"Cleaned up {deleted_count} old execution records"
