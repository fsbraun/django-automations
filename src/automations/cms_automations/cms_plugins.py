# coding=utf-8

"""Soft dependecy on django-automations_cms: Define plugins for open tasks"""
import logging

from django import forms

from .. import models
from . import models as cms_models
from .. import flow


try:
    from cms.plugin_base import CMSPluginBase
    from cms.utils import get_current_site
    from cms.plugin_pool import plugin_pool
    from django.utils.translation import gettext_lazy as _

    logger = logging.getLogger(__name__)

    class AutomationTaskList(CMSPluginBase):
        name = _("Task list")
        module = _("Automations")
        model = cms_models.AutomationTasksPlugin
        allow_children = False
        require_parent = False
        render_template = None

        def render(self, context, instance, placeholder):
            self.render_template = instance.template
            qs = models.AutomationTaskModel.get_open_tasks(context['request'].user)
            context.update(dict(tasks=qs, count=len(qs), always_inform=instance.always_inform))
            return context

    plugin_pool.register_plugin(AutomationTaskList)


    def get_task_choices(pattern, convert, subcls=None):
        status_choices = []
        for cls_name, verbose_name in flow.get_automations():
            cls = models.get_automation_class(cls_name)
            choices = []
            if subcls is not None and hasattr(cls, subcls):
                cls = getattr(cls, subcls)
            for item in dir(cls):
                if pattern(item):
                    attr = getattr(cls, item)
                    tpl = convert(attr, item, cls_name)
                    if isinstance(tpl, (tuple, list)):
                        choices.append(tuple(tpl))
            if choices:
                status_choices.append((verbose_name, tuple(choices)))
        return tuple(status_choices)   # make immutable

    def get_task_status_choices():
        def convert(attr, item, cls_name):
            if isinstance(attr, str):
                attr = attr, item.replace('_', ' ').capitalize()
            return attr
        return get_task_choices(lambda x: x.endswith("_template"), convert=convert, subcls="Meta")

    def get_task_receiver_choices():
        def convert(attr, item, cls_name):
            if callable(attr) and len(item) > 8:
                return cls_name+'.'+item[8:], item[8:].replace('_', ' ').capitalize()
            return None
        return get_task_choices(lambda x: x.startswith("receive_"), convert=convert)

    def get_int(get_data, data):
        if data in get_data and isinstance(get_data[data], str) and get_data[data].isnumeric():
            return int(get_data[data])
        return None

    def get_automation_instance(get_params):
        task_id, atm_id = get_int(get_params, "task_id"), get_int(get_params, "atm_id")
        if atm_id is not None:
            try:
                automation_instance = models.AutomationModel.objects.get(id=atm_id)
            except models.AutomationModel.DoesNotExist:
                return None
        elif task_id is not None:
            try:
                automation_instance = models.AutomationTaskModel.objects.get(id=atm_id).automation
            except models.AutomationTaskModel.DoesNotExist:
                return None
        else:
            return None

    def get_automation_data(context, template):
        automation_instance = get_automation_instance(context.get("request", dict()).GET)
        if automation_instance:
            cls = models.get_automation_class(automation_instance.automation_class)
            if hasattr(cls, "Meta"):
                for item in dir(cls.Meta):
                    if item.endswith('_template'):
                        attr = getattr(cls.Meta, item)
                        if (isinstance(attr, str) and attr == template or
                                isinstance(attr, (tuple, list)) and attr[0] == template):
                            return automation_instance
        return None


    class EditTaskData(forms.ModelForm):
        class Meta:
            model = cms_models.AutomationStatusPlugin
            widgets = {
                'template': forms.Select(choices=get_task_status_choices()),
                'name': forms.HiddenInput(),
            }
            fields = "__all__"

        def clean_name(self):
            choices = {}
            for _, chapter in get_task_status_choices():
                choices.update({key: value for key, value in chapter})
            return choices.get(self.data['template'], "")


    class AutomationStatus(CMSPluginBase):
        name = _("Status")
        module = _("Automations")
        model = cms_models.AutomationStatusPlugin
        allow_children = False
        require_parent = False
        text_enabled = True
        form = EditTaskData
        render_template = None

        def render(self, context, instance, placeholder):
            self.render_template = instance.template

            automation_instance = get_automation_data(context, self.render_template)
            if automation_instance is not None:
                automation = automation_instance.get_automation_class()(automation_id=automation_instance.id)
            else:
                automation = None
            context.update(dict(automation=automation,
                                automation_instance=automation_instance,
                                instance=instance))
            return context

    plugin_pool.register_plugin(AutomationStatus)


    class EditAutomationHook(forms.ModelForm):
        class Meta:
            model = cms_models.AutomationHookPlugin
            widgets = {
                'automation':   forms.Select(choices=get_task_receiver_choices()),
            }
            fields = "__all__"


    class AutomationHook(CMSPluginBase):
        name = _("Send message")
        module = _("Automations")
        model = cms_models.AutomationHookPlugin
        allow_children = False
        require_parent = False
        render_template = "automations/cms/empty_template.html"
        form = EditAutomationHook

        def render(self, context, instance, placeholder):
            request = context['request']
            automation, message = instance.automation.rsplit('.', 1)
            cls = models.get_automation_class(automation)
            if instance.operation == cms_models.AutomationHookPlugin.OperationChoices.message:
                automation_id = request.GET.get("atm_id", None)
                if isinstance(automation_id, str) and automation_id.isnumeric():
                    cls.dispatch_message(int(automation_id), message, instance.token, request)
                else:
                    logger.error("Invalid automation instance: %s" % instance)
            elif instance.operation == cms_models.AutomationHookPlugin.OperationChoices.start:
                cls.create_on_message(message, instance.token, request)
            elif instance.operation == cms_models.AutomationHookPlugin.OperationChoices.broadcast:
                cls.broadcast_message(message, instance.token, request)
            return context


    plugin_pool.register_plugin(AutomationHook)


except ImportError:
    pass
