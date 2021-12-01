# coding=utf-8
from django.urls import path

from . import views

urlpatterns = [
    path("", views.TaskListView.as_view(), name="task_list"),
    path("<int:task_id>", views.TaskView.as_view(), name="task"),
    path("dashboard", views.TaskDashboardView.as_view(), name="dashboard"),
    path("dashboard/<int:automation_id>", views.AutomationHistoryView.as_view(), name="history"),
    path("dashboard/<int:automation_id>/traceback/<int:task_id>", views.AutomationTracebackView.as_view(), name="traceback"),
]
