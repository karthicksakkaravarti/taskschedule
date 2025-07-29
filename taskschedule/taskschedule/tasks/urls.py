from django.urls import path

from . import views

app_name = 'tasks'

urlpatterns = [
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('<uuid:pk>/', views.TaskDetailView.as_view(), name='detail'),
    path('<uuid:pk>/update/', views.task_update_view, name='update'),
    path('<uuid:pk>/execute/', views.task_execute_view, name='execute'),
    path('<uuid:pk>/delete/', views.task_delete_view, name='delete'),
    path(
        'execution/<uuid:pk>/',
        views.TaskExecutionDetailView.as_view(),
        name='execution_detail'
    ),
    path(
        'execution/<uuid:pk>/logs/',
        views.execution_logs_view,
        name='execution_logs'
    ),
]
