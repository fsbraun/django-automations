from django.apps import AppConfig
from django.utils.translation import gettext as _


class CmsAutomationsConfig(AppConfig):
    name = 'cms_automations'
    default_auto_field = 'django.db.models.AutoField'
    verbose_name = _('CMS Automations')
