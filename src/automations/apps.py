# coding=utf-8
from types import MethodType

from django.apps import AppConfig
from django.apps import apps as django_apps
from django.conf import settings
from django.core.checks import Error
from django.core.checks import Tags as DjangoTags
from django.core.checks import register
from django.utils.translation import gettext_lazy as _

from .settings import USERS_WITH_PERMISSIONS_MODEL_METHOD


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


def get_users_with_permission_model_method(model):
    """
    Function to swap `get_users_with_permission` method within model if needed.
    """
    from django.utils.module_loading import import_string

    users_with_permission_method = USERS_WITH_PERMISSIONS_MODEL_METHOD

    if users_with_permission_method is not None:
        if callable(users_with_permission_method):
            model.get_users_with_permission = MethodType(
                users_with_permission_method,
                model,
            )
        else:
            model.get_users_with_permission = MethodType(
                import_string(users_with_permission_method),
                model,
            )


class AutomationsConfig(AppConfig):
    name = "automations"
    verbose_name = _("Automations")
    default_auto_field = "django.db.models.AutoField"

    def ready(self):

        # Swap AutomationTaskModel.get_users_with_permission method if needed
        AutomationTaskModel = django_apps.get_model(
            "automations.AutomationTaskModel", require_ready=False
        )
        get_users_with_permission_model_method(AutomationTaskModel)

        super().ready()
        register(Tags.automations_settings_tag)(checks_atm_settings)
