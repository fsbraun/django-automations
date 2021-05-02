from cms.models import CMSPlugin
from django.utils.translation import gettext as _

from .. import settings
from django.db import models


class AutomationTasksPlugin(CMSPlugin):
    template = models.CharField(
        max_length=settings.MAX_FIELD_LENGTH,
        choices=settings.TASK_LIST_TEMPLATES,
        default=settings.TASK_LIST_TEMPLATES[0][0],
        blank=False,
        verbose_name=_("Template"),
    )
    always_inform=models.BooleanField(
        default=True,
        verbose_name=_("Always inform"),
        help_text=_("If deactivated plugin will out output anything if no task is available.")
    )


class AutomationHookPlugin(CMSPlugin):          # pragma: no cover
    class OperationChoices(models.IntegerChoices):
        start = 0, _("Start automaton")
        callback = 1, _("Automation callback")

    automation = models.CharField(
        blank=False,
        max_length=settings.MAX_FIELD_LENGTH,
        verbose_name=_("Automation"),
    )

    token = models.CharField(
        max_length=settings.MAX_FIELD_LENGTH,
        blank=True,
        verbose_name=_("Optional token"),
    )

    def __str__(self):
        return self.automation.split('.')[-1]

class AutomationStatusPlugin(CMSPlugin):            # pragma: no cover
    template = models.CharField(
        blank=False,
        max_length=settings.MAX_FIELD_LENGTH,
        verbose_name=_("Task data"),
    )
    name = models.CharField(
        blank=True,
        max_length=settings.MAX_FIELD_LENGTH,
    )

    def __str__(self):
        return self.name if self.name else super().__str__()
