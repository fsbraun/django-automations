# coding=utf-8
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AutomationsConfig(AppConfig):
    name = 'automations'
    verbose_name = _('Automations')
    default_auto_field = 'django.db.models.AutoField'