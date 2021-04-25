# coding=utf-8

import sys
from logging import getLogger

from django.db.models import Q
from django.utils.module_loading import import_string
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django.db import models

# Create your models here.

logger = getLogger(__name__)


def empty_dict():
    return {}


class AutomationModel(models.Model):
    automation_class = models.CharField(
            max_length=256,
            blank=False,
            verbose_name=_("Process class"),
    )
    finished = models.BooleanField(
            default=False,
            verbose_name=_("Finished"),
    )
    data = models.JSONField(
            verbose_name=_("Data"),
            default = empty_dict,
    )
    paused_until = models.DateTimeField(
            null=True,
            verbose_name=_("Paused until"),
    )
    created = models.DateTimeField(
            auto_now_add=True,
    )
    updated = models.DateTimeField(
            auto_now=True,
    )

    @classmethod
    def run(cls, timestamp=None):
        if timestamp is None:
            timestamp = now()
        automations = cls.objects.filter(
                finished=False,
        ).filter(Q(paused_until__lte=timestamp) | Q(paused_until=None))

        for automation in automations:
            klass = import_string(automation.automation_class)
            instance = klass(automation_id=automation.id)
            logger.info(f"Running automation {automation.automation_class}")
            try:
                instance.run()
            except Exception as e:
                automation.finished = True
                automation.save()
                logger.error(f'Error: {repr(e)}', exc_info=sys.exc_info())


class AutomationTaskModel(models.Model):
    automation = models.ForeignKey(
            AutomationModel,
            on_delete=models.CASCADE,
    )
    previous = models.ForeignKey(
            'automations.AutomationTaskModel',
            on_delete=models.SET_NULL,
            null=True,
            verbose_name=_("Previous task"),
    )
    status = models.CharField(
            max_length=256,
            blank=True,
            verbose_name=_("Status"),
    )
    locked = models.IntegerField(
            default=0,
            verbose_name=_("Locked"),
    )
    interaction_user = models.ForeignKey(
            'auth.User',
            null=True,
            on_delete=models.PROTECT,
    )
    interaction_group = models.ForeignKey(
            'auth.Group',
            null=True,
            on_delete=models.PROTECT,
    )
    created = models.DateTimeField(
            auto_now_add=True,
    )
    finished = models.DateTimeField(
            null=True,
    )
    message = models.CharField(
            max_length=128,
            verbose_name=_("Message"),
            blank=True,
    )
    result = models.JSONField(
            verbose_name=_("Result"),
            null=True,
            blank=True,
            default=empty_dict,
    )

    @property
    def data(self):
        return self.automation.data