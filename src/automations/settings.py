# coding=utf-8

from django.conf import settings
from django.utils.translation import gettext_lazy as _

MAX_FIELD_LENGTH = 128

FORM_VIEW_CONTEXT = getattr(settings, 'ATM_FORM_VIEW_CONTEXT',
                            dict(
                                submit_classes="btn btn-primary float-right",
                                back_classes="btn btn-outline-primary",
                            ))

TASK_LIST_TEMPLATES = getattr(settings, 'ATM_TASK_LIST_TEMPLATES',
                              (
                                  ('automations/includes/task_list.html', _("Default template")),
                              ))
