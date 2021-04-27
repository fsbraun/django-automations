# coding=utf-8

# Create your views here.
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, FormView
from django.forms import BaseForm

from . import models, flow


class AutomationMixin:
    _automation_instance = None  # Buffer class for specific task_instance
    _task_instance_id = None

    def get_automation_instance(self, task_instance):
        if self._automation_instance is None or self._task_instance_id != task_instance.id:
            cls = task_instance.automation.get_automation_class()
            self._automation_instance = cls(automation=task_instance.automation)
            self._task_instance_id = task_instance.id
        return self._automation_instance


    @staticmethod
    def user_in_group(user, group):
        if group is None:
            return False
        return user.groups.filter(id=group.id).exists()


class TaskView(LoginRequiredMixin, AutomationMixin, FormView):
    def bind_to_node(self):
        self.task_instance = get_object_or_404(models.AutomationTaskModel, id=self.kwargs["task_id"])
        self.node = self.task_instance.get_node()

    def get_form_kwargs(self):
        if not hasattr(self, "node"):
            self.bind_to_node()
        kwargs = self.node._form_kwargs
        return kwargs(self.task_instance) if callable(kwargs) else kwargs

    def get_form_class(self):
        if not hasattr(self, "node"):
            self.bind_to_node()
        form = self.node._form
        return form if issubclass(form, BaseForm) else form(self.task_instance)

    def get_context_data(self, **kwargs):
        if not hasattr(self, "node"):
            self.bind_to_node()
        if not isinstance(self.node, flow.Form):
            raise Http404
        if (self.request.user != self.task_instance.interaction_user and
                not self.user_in_group(self.request.user, self.task_instance.interaction_group)):
            raise PermissionDenied
        if self.task_instance.finished:
            raise Http404  # Need to display a message: s.o. else has completed form
        self.template_name = (self.node._template_name or
                              self.get_automation_instance(self.task_instance).default_template_name)
        return super().get_context_data(**kwargs)

    def form_valid(self, form):
        self.node.validate(self.task_instance, self.request)
        if self.node._run:
            self.node._automation.run(self.task_instance.previous, self.node)
        if hasattr(self.node, "_success_url"):
            return redirect(self.node._success_url)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("task_list")


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
            interaction_group__in=user.groups.all(),
            finished=None,
        )
        return dict(error="", user_tasks=qs_user, group_tasks=qs_group, count=len(qs_group)+len(qs_user))


class TaskDashboard(TemplateView):
    template_name = 'automations/dashboard.html'

    def get_context_data(self, **kwargs):
        return dict(automations=models.AutomationModel.objects.all(),
                    tasks=models.AutomationTaskModel.objects.all())
