# coding=utf-8

# Create your views here.
import datetime

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.timezone import now
from django.views.generic import TemplateView, FormView
from django.forms import BaseForm

from . import models, flow, settings


class AutomationMixin:
    _automation_instance = None  # Buffer class for specific task_instance
    _task_id = None

    def get_automation_instance(self, task):
        if self._automation_instance is None or self._task_id != task.id:
            cls = task.automation.get_automation_class()
            self._automation_instance = cls(automation=task.automation)
            self._task_id = task.id
        return self._automation_instance


class TaskView(LoginRequiredMixin, AutomationMixin, FormView):
    def bind_to_node(self):
        self.task = get_object_or_404(models.AutomationTaskModel, id=self.kwargs["task_id"])
        self.node = self.task.get_node()

    def get_form_kwargs(self):
        if not hasattr(self, "node"):
            self.bind_to_node()
        kwargs = super().get_form_kwargs()
        task_kwargs = self.node._form_kwargs
        kwargs.update(task_kwargs(self.task) if callable(task_kwargs) else task_kwargs)
        return kwargs

    def get_form_class(self):
        if not hasattr(self, "node"):
            self.bind_to_node()
        form = self.node._form
        return form if issubclass(form, BaseForm) else form(self.task)

    def get_context_data(self, **kwargs):
        if not hasattr(self, "node"):
            self.bind_to_node()
        if not isinstance(self.node, flow.Form):
            raise Http404
        if self.request.user not in self.task.get_users_with_permission():
            raise PermissionDenied
        if self.task.finished:
            raise Http404  # Need to display a message: s.o. else has completed form
        self.template_name = (
                self.node._template_name or
                getattr(self.get_automation_instance(self.task), 'default_template_name',
                        'automations/form_view.html'))
        context = super().get_context_data(**kwargs)
        context.update(settings.FORM_VIEW_CONTEXT)
        context.update(getattr(self.node._automation, 'context', dict()))
        context.update(self.node._context)
        return context

    def form_valid(self, form):
        self.node.validate(self.task, self.request, form)
        if self.node._run:
            self.node._automation.run(self.task.previous, self.node)
        if hasattr(self.node, "_success_url"):
            return redirect(self.node._success_url)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("task_list")


class TaskListView(LoginRequiredMixin, TemplateView):
    template_name = 'automations/task_list.html'

    def get_context_data(self, **kwargs):
        qs = models.AutomationTaskModel.get_open_tasks(self.request.user)
        return dict(error="", tasks=qs, count=len(qs))


class UserIsStaff(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class TaskDashboardView(UserIsStaff, TemplateView):
    template_name = 'automations/dashboard.html'

    def get_context_data(self, **kwargs):
        qs = models.AutomationModel.objects.filter(created__gt=now()-datetime.timedelta(days=30))
        automations = []
        for item in qs.order_by("automation_class").values("automation_class").distinct():
            automation = models.get_automation_class(item['automation_class'])
            qs_filtered = qs.filter(**item)
            dashboard = (automation.get_dashboard_context(qs_filtered)
                         if hasattr(automation, "get_dashboard_context") else dict())
            automations.append(dict(cls=item['automation_class'],
                                    verbose_name=automation.get_verbose_name(),
                                    verbose_name_plural=automation.get_verbose_name_plural(),
                                    running=qs_filtered.filter(finished=False),
                                    finished=qs_filtered.filter(finished=True),
                                    dashboard_template= getattr(automations, "dashboard_template", ""),
                                    dashboard=dashboard))
        return dict(automations=automations)
