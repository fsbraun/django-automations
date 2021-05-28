# coding=utf-8
import hashlib
import sys
from logging import getLogger

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils.module_loading import import_string
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django.db import models

from . import settings

# Create your models here.

logger = getLogger(__name__)


def get_automation_class(dotted_name):
    components = dotted_name.rsplit('.',1)
    cls = __import__(components[0], fromlist=[components[-1]])
    cls = getattr(cls, components[-1])
    return cls


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
            default=dict,
    )
    key = models.CharField(
            verbose_name=_("Unique hash"),
            default="",
            max_length=64,
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

    _automation_class = None

    def save(self, *args, **kwargs):
        self.key = self.get_key()
        return super().save(*args, **kwargs)

    def get_automation_class(self):
        if self._automation_class is None:
            self._automation_class = get_automation_class(self.automation_class)
        return self._automation_class

    @property
    def instance(self):
        return self.get_automation_class()(automation=self)

    @classmethod
    def run(cls, timestamp=None):
        if timestamp is None:
            timestamp = now()
        automations = cls.objects.filter(
                finished=False,
        ).filter(Q(paused_until__lte=timestamp) | Q(paused_until=None))

        for automation in automations:
            klass = import_string(automation.automation_class)
            instance = klass(automation_id=automation.id, autorun=False)
            logger.info(f"Running automation {automation.automation_class}")
            try:
                instance.run()
            except Exception as e:          # pragma: no cover
                automation.finished = True
                automation.save()
                logger.error(f'Error: {repr(e)}', exc_info=sys.exc_info())

    def get_key(self):
        return hashlib.sha1(f"{self.automation_class}-{self.id}".encode("utf-8")).hexdigest()

    def __str__(self):
        return f"<AutomationModel for {self.automation_class}>"


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
    requires_interaction = models.BooleanField(
        default=False,
        verbose_name=_("Requires interaction")
    )
    interaction_user = models.ForeignKey(
            'auth.User',
            null=True,
            on_delete=models.PROTECT,
            verbose_name=_("Assigned user"),
    )
    interaction_group = models.ForeignKey(
            'auth.Group',
            null=True,
            on_delete=models.PROTECT,
            verbose_name=_("Assigned group"),
    )
    interaction_permissions = models.JSONField(
        default=list,
        verbose_name=_("Required permissions"),
        help_text=_("List of permissions of the form app_label.codename"),
    )
    created = models.DateTimeField(
            auto_now_add=True,
    )
    finished = models.DateTimeField(
            null=True,
    )
    message = models.CharField(
            max_length=settings.MAX_FIELD_LENGTH,
            verbose_name=_("Message"),
            blank=True,
    )
    result = models.JSONField(
            verbose_name=_("Result"),
            null=True,
            blank=True,
            default=dict,
    )

    @property
    def data(self):
        return self.automation.data

    def hours_since_created(self):
        """returns the number of hours since creation of node, 0 if finished"""
        if self.finished:
            return 0
        return (now()-self.created).total_seconds()/3600

    def get_users_with_permission(self, include_superusers=True,
                                  backend="django.contrib.auth.backends.ModelBackend"):

        users = User.objects.all()
        for permission in self.interaction_permissions:
            users &= User.objects.with_perm(permission, include_superusers=False, backend=backend)
        if self.interaction_user is not None:
            users = users.filter(id=self.interaction_user_id)
        if self.interaction_group is not None:
            users = users.filter(groups=self.interaction_group)
        if include_superusers:
            users |= User.objects.filter(is_superuser=True)
        return users

    def get_node(self):
        instance = self.automation.instance
        return getattr(instance, self.status)

    @classmethod
    def get_open_tasks(cls, user):
        candidates = cls.objects.filter(finished=None)
        return tuple(task for task in candidates
                     if task.requires_interaction and user in task.get_users_with_permission())
