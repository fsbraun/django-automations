# coding=utf-8
from django.urls import path

from . import views

urlpatterns = [
    path("<int:task_id>", views.TaskView.as_view(), name="task"),
    path("tasks", views.TaskListView.as_view(), name="task_list"),
    path("dashboard", views.TaskDashboard.as_view(), name="dashboard"),
]
