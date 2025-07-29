from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView

from taskschedule.tasks.forms import (TaskExecuteForm, TaskSubmissionForm,
                                      TaskUpdateForm)
from taskschedule.tasks.models import TaskDefinition, TaskExecution
from taskschedule.tasks.tasks import execute_python_script


def home_view(request):
    """Landing page with task submission form."""
    if request.method == 'POST':
        if not request.user.is_authenticated:
            messages.error(
                request,
                'Please sign in to submit tasks.'
            )
            return redirect('account_login')

        form = TaskSubmissionForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            task = form.save()
            messages.success(
                request,
                f'Task "{task.name}" has been created successfully! '
                f'You can manage it from your dashboard.'
            )
            return redirect('tasks:detail', pk=task.pk)
        else:
            messages.error(
                request,
                'Please correct the errors below and try again.'
            )
    else:
        form = TaskSubmissionForm()

    return render(request, 'pages/home.html', {'form': form})


@login_required
def dashboard_view(request):
    """User dashboard showing all their tasks."""
    tasks = TaskDefinition.objects.filter(user=request.user)

    # Filter by status if requested
    status_filter = request.GET.get('status')
    if status_filter:
        tasks = tasks.filter(status=status_filter)

    # Filter by task type if requested
    type_filter = request.GET.get('type')
    if type_filter:
        tasks = tasks.filter(task_type=type_filter)

    # Pagination
    paginator = Paginator(tasks, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Statistics
    stats = {
        'total_tasks': TaskDefinition.objects.filter(user=request.user).count(),
        'active_tasks': TaskDefinition.objects.filter(
            user=request.user, status='active'
        ).count(),
        'total_executions': TaskExecution.objects.filter(
            task__user=request.user
        ).count(),
        'successful_executions': TaskExecution.objects.filter(
            task__user=request.user, status='success'
        ).count(),
    }

    return render(request, 'tasks/dashboard.html', {
        'page_obj': page_obj,
        'stats': stats,
        'status_filter': status_filter,
        'type_filter': type_filter,
    })


class TaskDetailView(LoginRequiredMixin, DetailView):
    """Detailed view of a specific task."""
    model = TaskDefinition
    template_name = 'tasks/detail.html'
    context_object_name = 'task'

    def get_queryset(self):
        return TaskDefinition.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.get_object()

        # Get recent executions
        recent_executions = task.executions.all()[:10]
        context['recent_executions'] = recent_executions

        # Add execute form
        context['execute_form'] = TaskExecuteForm()

        # Add execution statistics
        context['successful_count'] = task.executions.filter(status='success').count()
        context['failed_count'] = task.executions.filter(status='failed').count()

        return context


@login_required
def task_update_view(request, pk):
    """Update an existing task."""
    task = get_object_or_404(TaskDefinition, pk=pk, user=request.user)

    if request.method == 'POST':
        form = TaskUpdateForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f'Task "{task.name}" has been updated successfully!'
            )
            return redirect('tasks:detail', pk=task.pk)
    else:
        form = TaskUpdateForm(instance=task)

    return render(request, 'tasks/update.html', {
        'form': form,
        'task': task,
    })


@login_required
@require_http_methods(["POST"])
def task_execute_view(request, pk):
    """Manually execute a task."""
    task = get_object_or_404(TaskDefinition, pk=pk, user=request.user)
    form = TaskExecuteForm(request.POST)

    if form.is_valid():
        # Create a new execution record
        execution = TaskExecution.objects.create(task=task)

        # Queue the task for execution
        try:
            result = execute_python_script.delay(execution.id)
            execution.celery_task_id = result.id
            execution.save(update_fields=['celery_task_id'])

            messages.success(
                request,
                f'Task "{task.name}" has been queued for execution!'
            )
        except Exception as e:
            execution.mark_completed('failure', error_output=str(e))
            messages.error(
                request,
                f'Failed to queue task: {str(e)}'
            )
    else:
        messages.error(request, 'Please confirm the execution.')

    return redirect('tasks:detail', pk=task.pk)


@login_required
def task_delete_view(request, pk):
    """Delete a task."""
    task = get_object_or_404(TaskDefinition, pk=pk, user=request.user)

    if request.method == 'POST':
        task_name = task.name
        task.delete()
        messages.success(
            request,
            f'Task "{task_name}" has been deleted successfully!'
        )
        return redirect('tasks:dashboard')

    return render(request, 'tasks/delete.html', {'task': task})


class TaskExecutionDetailView(LoginRequiredMixin, DetailView):
    """Detailed view of a specific task execution."""
    model = TaskExecution
    template_name = 'tasks/execution_detail.html'
    context_object_name = 'execution'

    def get_queryset(self):
        return TaskExecution.objects.filter(task__user=self.request.user)


@login_required
def execution_logs_view(request, pk):
    """View execution logs for a specific task."""
    task = get_object_or_404(TaskDefinition, pk=pk, user=request.user)

    # Get all executions for this task
    executions = task.executions.all().order_by('-created_at')

    # Pagination
    paginator = Paginator(executions, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Statistics
    successful_count = task.executions.filter(status='success').count()
    failed_count = task.executions.filter(status='failed').count()
    running_count = task.executions.filter(status='running').count()

    return render(request, 'tasks/execution_logs.html', {
        'task': task,
        'page_obj': page_obj,
        'successful_count': successful_count,
        'failed_count': failed_count,
        'running_count': running_count,
    })
