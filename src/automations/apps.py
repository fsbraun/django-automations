# coding=utf-8
from django.apps import AppConfig
from django.conf import settings
from django.core.checks import Error
from django.core.checks import Tags as DjangoTags
from django.core.checks import register
from django.utils.translation import gettext_lazy as _


class Tags(DjangoTags):
    automations_settings_tag = "automations_settings"


def checks_atm_settings(app_configs, **kwargs):
    """Checks that either all or none of the group/permissions settings are set"""
    errors = []
    group_and_permission_settings = (
        hasattr(settings, "ATM_GROUP_MODEL"),
        hasattr(settings, "ATM_USER_WITH_PERMISSIONS_FORM_METHOD"),
        hasattr(settings, "ATM_USER_WITH_PERMISSIONS_MODEL_METHOD"),
    )

    if any(group_and_permission_settings) and not all(group_and_permission_settings):
        errors = [
            (
                Error(
                    "Django Automations settings incorrectly configured",
                    hint=_(
                        "Either all or none of the following settings must be present: ATM_GROUP_MODEL, "
                        "ATM_USER_WITH_PERMISSIONS_FORM_METHOD, ATM_USER_WITH_PERMISSIONS_MODEL_METHOD"
                    ),
                    id="automations.E001",
                )
            )
        ]
    return errors


class AutomationsConfig(AppConfig):
    name = "automations"
    verbose_name = _("Automations")
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        super().ready()
        register(Tags.automations_settings_tag)(checks_atm_settings)
