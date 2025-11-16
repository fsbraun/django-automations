# coding=utf-8

from django.apps import apps as django_apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

MAX_FIELD_LENGTH = 128

FORM_VIEW_CONTEXT = getattr(
    settings,
    "ATM_FORM_VIEW_CONTEXT",
    dict(
        submit_classes="btn btn-primary float-right float-end",
        back_classes="btn btn-outline-primary",
    ),
)

TASK_LIST_TEMPLATES = getattr(
    settings,
    "ATM_TASK_LIST_TEMPLATES",
    (("automations/includes/task_list.html", _("Default template")),),
)

AUTH_USER_MODEL = getattr(settings, "AUTH_USER_MODEL", "auth.User")


def get_group_model(settings=settings):
    """
    Return the Group or alternate grouping model that is active in this project.
    """
    GROUP_MODEL = getattr(settings, "ATM_GROUP_MODEL", "auth.Group")

    try:
        return django_apps.get_model(GROUP_MODEL, require_ready=False)
    except ValueError:
        raise ImproperlyConfigured(
            "ATM_GROUP_MODEL must be of the form 'app_label.model_name'"
        )
    except LookupError:
        raise ImproperlyConfigured(
            f"ATM_GROUP_MODEL refers to model '{GROUP_MODEL}' that has not been installed"
        )


def get_users_with_permission_form_method(settings=settings):
    return getattr(
        settings,
        "ATM_USER_WITH_PERMISSIONS_FORM_METHOD",
        None,
    )


def get_users_with_permission_model_method(settings=settings):
    return getattr(
        settings,
        "ATM_USER_WITH_PERMISSIONS_MODEL_METHOD",
        None,
    )
