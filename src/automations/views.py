# coding=utf-8

# Create your views here.
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import TemplateView

from . import models


class AutomationMixin:
    _automation_instance = None

    def get_automation_instance(self, task_instance):
        if self._automation_instance is None:
            components = task_instance.automation.automation_class.split('.')
            cls = __import__(components[0])
            for path in components[1:]:
                cls = getattr(cls, path)
            self._automation_instance = cls(automation_id=task_instance.automation.id)
        return self._automation_instance

    def get_node(self, task_instance):
        return getattr(self.get_automation_instance(task_instance), task_instance.status)
#        task_instance = get_object_or_404(models.AutomationTaskModel, id=task_id)


class TaskView(View):
    pass


class TaskListView(LoginRequiredMixin, TemplateView):
    template_name = 'automations/task_list.html'

    def get_context_data(self, **kwargs):
        user = self.request.user
        if not user.is_authenticated:
            return dict(error="not authenticated", message=_("Please login to see your open tasks."))
        if not user.is_active:
            return dict(error="user inactive", message=_("Your account has been deactivated."))
        qs_user = models.AutomationTaskModel.objects.filter(
            interaction_user=user,
            finished=None,
        )
        qs_group = models.AutomationTaskModel.objects.filter(
            interaction_group=user.group,
            finished=None,
        )
        return dict(error="", user_tasks=qs_user, group_tasks=qs_group, count=len(qs_group)+len(qs_user))


class TaskDashboard(View):
    pass
