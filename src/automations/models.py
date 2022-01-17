# coding=utf-8
import datetime
import hashlib
import sys
from logging import getLogger
from types import MethodType

from django.conf import settings as project_settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.utils.module_loading import import_string
from django.utils.timezone import now
from django.utils.translation import gettext as _

from . import settings

# Create your models here.

logger = getLogger(__name__)

User = get_user_model()
Group = settings.get_group_model()


def get_automation_class(dotted_name):
    components = dotted_name.rsplit(".", 1)
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
            except Exception as e:  # pragma: no cover
                automation.finished = True
                automation.save()
                logger.error(f"Error: {repr(e)}", exc_info=sys.exc_info())

    def get_key(self):
        return hashlib.sha1(
            f"{self.automation_class}-{self.id}".encode("utf-8")
        ).hexdigest()

    @classmethod
    def delete_history(cls, days=30):
        automations = cls.objects.filter(
            finished=True, updated__lt=now() - datetime.timedelta(days=days)
        )
        return automations.delete()

    def __str__(self):
        return f"<AutomationModel for {self.automation_class}>"


class AutomationTaskModel(models.Model):
    automation = models.ForeignKey(
        AutomationModel,
        on_delete=models.CASCADE,
    )
    previous = models.ForeignKey(
        "automations.AutomationTaskModel",
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
        default=False, verbose_name=_("Requires interaction")
    )
    interaction_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.PROTECT,
        verbose_name=_("Assigned user"),
    )
    interaction_group = models.ForeignKey(
        Group,
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
        return (now() - self.created).total_seconds() / 3600

    def get_node(self):
        instance = self.automation.instance
        return getattr(instance, self.status)

    def get_previous_tasks(self):
        if self.message == "Joined" and self.result:
            return self.__class__.objects.filter(id__in=self.result)
        return [self.previous] if self.previous else []

    def get_next_tasks(self):
        return self.automationtaskmodel_set.all()

    @classmethod
    def get_open_tasks(cls, user):
        candidates = cls.objects.filter(finished=None, requires_interaction=True)
        return tuple(
            task for task in candidates if user in task.get_users_with_permission()
        )

    def get_users_with_permission(
        self,
        include_superusers=True,
        backend="django.contrib.auth.backends.ModelBackend",
    ):
        """
        Given an AutomationTaskModel instance, which has access to a list of permission
        codenames (self.interaction_permissions), the assigned user (self.interaction_user),
        and assigned group (self.interaction_group), returns a QuerySet of users with
        applicable permissions that meet the requirements for access.
        """
        users = User.objects.all()
        for permission in self.interaction_permissions:
            users &= User.objects.with_perm(
                permission, include_superusers=False, backend=backend
            )
        if self.interaction_user is not None:
            users = users.filter(id=self.interaction_user_id)
        if self.interaction_group is not None:
            users = users.filter(groups=self.interaction_group)
        if include_superusers:
            users |= User.objects.filter(is_superuser=True)
        return users

    def __str__(self):
        return f"<ATM {self.status} {self.message} ({self.id})>"

    def __repr__(self):
        return self.__str__()


def swap_users_with_permission_model_method(model, settings_conf):
    """
    Function to swap `get_users_with_permission` method within model if needed.
    """
    from django.utils.module_loading import import_string

    users_with_permission_method = settings.get_users_with_permission_model_method(
        settings=settings_conf
    )

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


# Swap AutomationTaskModel.get_users_with_permission method if needed
swap_users_with_permission_model_method(
    AutomationTaskModel, settings_conf=project_settings
)
