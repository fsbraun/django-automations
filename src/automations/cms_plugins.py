# coding=utf-8

"""Soft dependecy on django-cms: Define plugins for open tasks"""
import logging

from django import forms

from . import models, flow


try:
    from cms.plugin_base import CMSPluginBase
    from cms.utils import get_current_site
    from cms.plugin_pool import plugin_pool
    from django.utils.translation import gettext_lazy as _

    logger = logging.getLogger(__name__)

    class AutomationTaksList(CMSPluginBase):
        name = _("Task list")
        module = _("Automations")
        model = models.AutomationTasksPlugin
        allow_children = False
        require_parent = False

        def render(self, context, instance, placeholder):
            self.render_template = instance.template
            qs = models.AutomationTaskModel.get_open_tasks(context['request'].user)
            context.update(dict(tasks=qs, count=len(qs)))
            return context

    plugin_pool.register_plugin(AutomationTaksList)


    class EditAutomationHook(forms.ModelForm):
        class Meta:
            model = models.AutomationHookPlugin
            widgets = {
                'automation':   forms.Select(choices=flow.get_automations()),
            }
            fields = "__all__"


    class AutomationHook(CMSPluginBase):
        name = _("Callback hook")
        module = _("Automations")
        model = models.AutomationHookPlugin
        allow_children = False
        require_parent = False
        render_template = "automations/empty_template.html"
        form = EditAutomationHook

        def render(self, context, instance, placeholder):
            request = context['request']
            cls = models.get_automation_class(instance.automation)
            if instance.operation == 0:  # Start process
                atm = cls(**instance.kwargs)
                atm.start_from_request(request)
            elif instance.operation == 1:  # Callback message
                automation_id = request.GET.get("atm_id", None)
                if isinstance(automation_id, str) and automation_id.isnumeric():
                    atm = cls(automation_id=int(automation_id))
                    atm.receive_message(instance.message, request)
            else:
                logger.error("Invalid AutomationHook configuration: %s" % instance)
            return context

    plugin_pool.register_plugin(AutomationHook)

except ImportError:
    pass