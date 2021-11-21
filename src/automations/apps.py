# coding=utf-8
from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _


class AutomationsConfig(AppConfig):
    name = "automations"
    verbose_name = _("Automations")
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        group_and_permission_settings = (
            hasattr(settings, "ATM_GROUP_MODEL"),
            hasattr(settings, "ATM_USER_WITH_PERMISSIONS_FORM_METHOD"),
            hasattr(settings, "ATM_USER_WITH_PERMISSIONS_MODEL_METHOD"),
        )
        if any(group_and_permission_settings) and not all(
            group_and_permission_settings
        ):
            raise ImproperlyConfigured(
                "Either all or none of the following settings must be present: ATM_GROUP_MODEL, "
                "ATM_USER_WITH_PERMISSIONS_FORM_METHOD, ATM_USER_WITH_PERMISSIONS_MODEL_METHOD"
            )
