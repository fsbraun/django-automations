# coding=utf-8
import datetime
import json
import sys
import threading
import traceback
from copy import copy

from django.contrib.auth.models import User, Group
from django.core.exceptions import ImproperlyConfigured
from django.db.models.base import ModelBase
from django.db.transaction import atomic
from django.utils.timezone import now

from . import models, settings

"""To allow forward references in Automation object "this" is defined"""


class ThisObject:
    """Wrapper for forward-reference to a named attribute"""

    def __init__(self, attr):
        super().__init__()
        self.attr = attr


class This:
    """Generator for reference to a named attribute"""

    def __getattr__(self, item):
        return ThisObject(item)


this = This()

"""
"""


def on_execution_path(m):
    """Wrapper to ensure automatic pausing of automations in
    case of WaitUntil, PauseFor and When"""

    def wrapper(self, task_instance, *args, **kwargs):
        return None if task_instance is None else m(self, task_instance, *args, **kwargs)

    return wrapper


class Node:
    """Parent class for all nodes"""

    def __init__(self, *args, **kwargs):
        self._conditions = []
        self._next = None
        self._wait = None
        self.description = kwargs.pop('description', '')

    @staticmethod
    def eval(sth, task):
        return sth(task) if callable(sth) else sth

    def ready(self, automation_instance, name):
        """is called by the newly initialized Automation instance to bind the nodes to the instance."""
        self._automation = automation_instance
        self._name = name
        self._conditions = [automation_instance.get_node(condition) for condition in self._conditions]

    def get_automation_name(self):
        """returns the name of the Automation instance class the node is bound to"""
        return self._automation.__class__.__name__

    def __getattribute__(self, item):
        value = super().__getattribute__(item)
        if isinstance(value, ThisObject) or (isinstance(value, str) and hasattr(self._automation, value)
                                             and item != '_name' and item != '_automation'):
            value = self.resolve(value)
            setattr(self, item, value)  # remember
        return value

    def resolve(self, value):
        if isinstance(value, ThisObject):  # This object?
            value = getattr(self._automation, value.attr)  # get automation attribute
        elif isinstance(value, str) and hasattr(self._automation, value):  # String literal instead of this
            value = getattr(self._automation, value)
        return value

    @atomic
    def enter(self, prev_task=None):
        assert prev_task is None or prev_task.finished is not None, "Node entered w/o previous node left"
        db = self._automation._db
        assert isinstance(db, models.AutomationModel)
        task_instance, _ = db.automationtaskmodel_set.get_or_create(
            previous=prev_task,
            status=self._name,
            defaults=dict(
                locked=0,
            ),
        )
        if task_instance.locked > 0:
            return None
        task_instance.locked += 1
        task_instance.save()
        return task_instance

    @atomic
    def release_lock(self, task_instance: models.AutomationTaskModel):
        task_instance.locked -= 1
        task_instance.save()
        return None

    def leave(self, task_instance: models.AutomationTaskModel):
        if task_instance is not None:
            task_instance.finished = now()
            self.release_lock(task_instance)
            if self._next is None:
                next_node = self._automation._iter[self]
            else:
                next_node = self._next
            if next_node is None:
                raise ImproperlyConfigured("No End statement")
            return next_node

    @on_execution_path
    def when_handler(self, task_instance):
        for condition in self._conditions:
            if not self.eval(condition, task_instance):
                return self.release_lock(task_instance)
        return task_instance

    @on_execution_path
    def wait_handler(self, task_instance: models.AutomationTaskModel):
        if self._wait is None:
            return task_instance
        earliest_execution = self.eval(self._wait, task_instance)
        if earliest_execution < now():
            return task_instance
        if self._automation._db.paused_until:
            self._automation._db.paused_until = min(self._automation._db.paused_until, earliest_execution)
        else:
            self._automation._db.paused_until = earliest_execution
        self._automation._db.save()
        return self.release_lock(task_instance)

    def execute(self, task_instance: models.AutomationTaskModel):
        return self.when_handler(self.wait_handler(task_instance))

    def Next(self, next_node):
        if self._next is not None:
            raise ImproperlyConfigured(f"Multiple .Next statements")
        self._next = next_node
        return self

    def AsSoonAs(self, condition):
        self._conditions.append(condition)
        return self

    def AfterWaitingUntil(self, time):
        if self._wait is not None:
            raise ImproperlyConfigured(f"Multiple .WaitUntil or .PauseFor statements")
        self._wait = time
        return self

    def AfterPausingFor(self, timedelta):
        if self._wait is not None:
            raise ImproperlyConfigured(f"Multiple .WaitUntil or .PauseFor statements")
        self._wait = lambda x: x.created + self.eval(timedelta, x)
        return self

    @property
    def data(self):
        assert self._automation is not None, "Node not bound to Automation"
        return self._automation.data

    def save(self):
        assert self._automation is not None, "Node not bound to Automation"
        return self._automation.save()

    def __repr__(self):
        return f"<{self._automation if self._automation else 'unbound'}: {self.__class__.__name__} node>"


class End(Node):
    def execute(self, task):
        self._automation._db.finished = True
        self._automation._db.save()
        return task

    def leave(self, task_instance):
        task_instance.finished = now()
        task_instance.save()


class Repeat(Node):
    def __init__(self, start=None, **kwargs):
        if start is None:
            start = self._automation.start

        super().__init__(**kwargs)
        self._next = start
        self._interval = None
        self._startpoint = None

    @on_execution_path
    def repeat_handler(self, task_instance):
        if self._startpoint is None:
            self._startpoint = now()
        elif now() < self._startpoint:
            return self.release_lock(task_instance)
        db = self._automation._db
        if db.paused_until:
            if now() < db.paused_until:
                return self.release_lock(task_instance)
        else:
            db.paused_until = self._startpoint
        while self._automation._db.paused_until < now():
            db.paused_until += self._interval
        db.save()
        return task_instance

    def execute(self, task_instance: models.AutomationTaskModel):
        task_instance = super().execute(task_instance)
        return self.repeat_handler(task_instance)

    def EveryDayAt(self, hour, minute):
        if self._interval is not None:
            raise ImproperlyConfigured(f"Multiple interval statements")
        self._interval = datetime.timedelta(days=1)
        self._startpoint = now()
        self._startpoint.replace(hour=hour, minute=minute)
        return self

    def EveryHour(self, hours=1):
        if self._interval is not None:
            raise ImproperlyConfigured(f"Multiple interval statements")
        self._interval = datetime.timedelta(hours=hours)
        return self

    def EveryNMinutes(self, minutes):
        if self._interval is not None:
            raise ImproperlyConfigured(f"Multiple interval statements")
        self._interval = datetime.timedelta(minutes=minutes)
        return self

    def EveryNDays(self, days):
        if self._interval is not None:
            raise ImproperlyConfigured(f"Multiple interval statements")
        self._interval = datetime.timedelta(days=days)
        return self


class Split(Node):
    """Spawn several tasks which have to be joined by a Join() node"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._splits = []

    def Next(self, node):
        self._splits.append(node)
        return self

    def execute(self, task_instance: models.AutomationTaskModel):
        task_instance = super().execute(task_instance)
        if task_instance:
            assert len(self._splits) > 0, "at least on .Next statement needed for Split()"
            db = self._automation._db
            tasks = list(
                db.automationtaskmodel_set.create(  # Create splits
                    previous=task_instance,
                    status=self.resolve(split)._name,
                    locked=0,
                ) for split in self._splits)
            self.leave(task_instance)
            for task in tasks:
                self._automation.run(task.previous, getattr(self._automation, task.status))  # Run other splits
            return None
        return task_instance


class Join(Node):
    """Collect tasks spawned by Split"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def execute(self, task_instance: models.AutomationTaskModel):
        task_instance = super().execute(task_instance)
        if task_instance:
            split_task = self.get_split(task_instance)
            if split_task is None:
                raise ImproperlyConfigured("Join() without Split()")
            all_splits = []
            for open_task in self._automation._db.automationtaskmodel_set.filter(
                    finished=None,
            ):
                split = self.get_split(open_task)
                if split and split.id == split_task.id:
                    all_splits.append(open_task)
            assert len(all_splits) > 0, "Internal error: at least one split expected"
            if len(all_splits) > 1:  # more than one split at the moment: close this split
                self.leave(task_instance)
                return None
        return task_instance

    def get_split(self, task_instance):
        split_task = task_instance.previous
        while split_task is not None:
            node = getattr(self._automation, split_task.status)
            if isinstance(node, Split):
                return split_task
            split_task = split_task.previous  # Go back the history
        return None


class Execute(Node):
    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        self._on_error = None
        self.args = args
        self.kwargs = kwargs
        self._err = None

    def method(self, task_instance, *args, **kwargs):
        func = args[0]
        return func(task_instance, *self.args[1:], **self.kwargs)

    @on_execution_path
    def execute_handler(self, task_instance: models.AutomationTaskModel):
        def func(task_instance, *args, **kwargs):
            try:
                result = self.method(task_instance, *args, **kwargs)
                task_instance.message = "OK"
                try:  # Check if result is json serializable
                    json.dumps(result)
                except ValueError:
                    task_instance.result = None
                else:
                    task_instance.result = result  # if yes, store it
            except Exception as err:
                self._err = err
                try:
                    task_instance.message = repr(err)[:settings.MAX_FIELD_LENGTH]
                    task_instance.result = dict(erro=traceback.format_exc())
                except TypeError:
                    pass

        if self.args is not None:
            args = (self.resolve(value) for value in self.args)
            kwargs = {key: self.resolve(value) for key, value in self.kwargs.items()}

            if kwargs.get("threaded", False):
                assert self._on_error is None, "No .OnError statement on threaded executions"
                threading.Thread(target=func, args=[task_instance] + args, kwargs=kwargs).start()
            else:
                func(task_instance, *args, **kwargs)
                if self._err and self._on_error:
                    self._next = self._on_error
        return task_instance

    def execute(self, task_instance: models.AutomationTaskModel):
        task_instance = super().execute(task_instance)
        return self.execute_handler(task_instance)

    def OnError(self, next_node):
        if self._on_error is not None:
            raise ImproperlyConfigured(f"Multiple .OnError statements")
        self._on_error = next_node
        return self


class If(Execute):
    def __init__(self, condition, **kwargs):
        super().__init__(None, **kwargs)
        self._condition = condition
        self._then = None
        self._else = None

    def Then(self, func):
        if self._then is not None:
            raise ImproperlyConfigured(f"Multiple .Then statements")
        self._then = func
        return self

    def Else(self, func):
        if self._else is not None:
            raise ImproperlyConfigured(f"Multiple .Else statements")
        self._else = func
        return self

    @on_execution_path
    def if_handler(self, task_instance: models.AutomationTaskModel):
        if self._then is None:
            raise ImproperlyConfigured(f"Missing .Then statement")
        opt = self._then if self.eval(self._condition, task_instance) \
            else self._else
        if isinstance(opt, Node):
            self._next = opt
        elif opt is not None:
            self._func = opt
            return self.execute_handler(task_instance)
        return task_instance

    def execute(self, task_instance: models.AutomationTaskModel):
        task_instance = super().execute(task_instance)
        return self.if_handler(task_instance)


class Form(Node):
    def __init__(self, form, template_name=None, **kwargs):
        super().__init__(**kwargs)
        self._form = form
        self._template_name = template_name
        self._user = None
        self._group = None
        self._permission = None
        self._run = True

    def execute(self, task_instance: models.AutomationTaskModel):
        if self._conditions:
            raise ImproperlyConfigured("UserForm() does not allow .AsSoonAs() decorator")
        if self._wait:
            raise ImproperlyConfigured("UserForm() does not allow .AfterWaitingUntil() or .AfterPausingFor() decorator")
        task_instance = super().execute(task_instance)

        if task_instance is not None:
            if self._user is None and self._group is None:
                raise ImproperlyConfigured("From: at least .User or .Group has to be specified")
            task_instance.interaction_user = self.get_user()
            task_instance.interaction_group = self.get_group()
            if task_instance.data.get(f"_{self._name}_validated", None) is None:
                self.release_lock(task_instance)  # Release lock and stop automation until form is validated
                return None
        return task_instance  # Continue with validated form

    def validate(self, task_instance: models.AutomationTaskModel, request):
        task_instance.automation.data[f"_{self._name}_validated"] = request.user.id
        task_instance.automation.save()

    def User(self, **kwargs):
        if self._user is not None:
            raise ImproperlyConfigured("Only one .User modifier for Form")
        self._user = kwargs
        return self

    def Group(self, **kwargs):
        if self._group is not None:
            raise ImproperlyConfigured("Only one .Group modifier for Form")
        self._group = kwargs
        return self

    def get_user(self):
        return User.objects.get(**self._user) if self._user is not None else None

    def get_group(self):
        return Group.objects.get(**self._group) if self._group is not None else None

    def Permission(self, permission):
        raise NotImplementedError(".Permission() not implemented")
        # self._permission = permission
        # return self


def OnSignal(signal, start=None, **kwargs):
    """decorator for automations to connect to Django signals"""
    def decorator(cls):
        def creator(sender, **sargs):
            automation=cls()
            if hasattr(automation, 'started_by_signal'):
                automation.started_by_signal(sender, **sargs)
            automation.run(None, None if start is None else getattr(automation, start))
        signal.connect(creator, weak=False, **kwargs)
        return cls
    return decorator


class Automation:
    model_class = models.AutomationModel
    singleton = False

    end = End()  # Endpoint of automation

    def __init__(self, **kwargs):
        super().__init__()
        prev = None
        self._iter = {}
        self._start = {}
        for name, attr in self.__class__.__dict__.items():
            if isinstance(attr, Node):  # Init nodes
                self._iter[prev] = attr
                attr.ready(self, name)
                prev = attr
            if isinstance(attr, ModelBase):  # Attach to Model instance
                at_c = copy(attr)  # Create copies of name and Model (attr)
                nm_c = copy(name)
                setattr(self.__class__, name,  # Replace property by get_model_instance
                        property(lambda slf: slf.get_model_instance(at_c, nm_c), self))
                if name not in kwargs:
                    kwargs[name] = None
                elif not isinstance(kwargs[name], int):  # Convert instance to id
                    kwargs[name] = kwargs[name].id
        self._iter[prev] = None  # Last item

        if 'automation' in kwargs:
            self._db = kwargs.pop('automation')
            assert isinstance(self._db, models.AutomationModel), \
                "automation= parameter needs to be AutomationModel instance"
        elif 'automation_id' in kwargs:  # Attach to automation in DB
            self._db, _ = self.model_class.objects.get_or_create(
                id=kwargs.pop('automation_id'),
                defaults=dict(
                    automation_class=self.get_automation_class_name(),
                    finished=False,
                    data=kwargs,
                ))
        elif self.singleton:  # Create or get singleton in DB
            self._db, _ = self.model_class.objects.create_or_get(
                automation_class=self.get_automation_class_name(),
            )
            self._db.data = kwargs
            self._db.finished = False
            self._db.save()
        else:  # Create new automation in DB
            self._db = self.model_class.objects.create(
                automation_class=self.get_automation_class_name(),
                finished=False,
                data=kwargs,
            )

    def get_model_instance(self, model, name):
        if not hasattr(self, '_' + name):
            setattr(self, '_' + name, model.objects.get(id=self._db.data[name]))
        return getattr(self, '_' + name)

    def get_automation_class_name(self):
        return self.__module__ + '.' + self.__class__.__name__

    def get_node(self, node):
        """Resolve ThisObject references"""
        if isinstance(node, ThisObject):
            return getattr(self, node.attr)
        elif isinstance(node, str) and hasattr(self, node):
            return getattr(self, node)
        return node

    def get_task(self):
        if self._db.finished:
            raise ValueError("Trying to run an already finished automation")

        last_tasks = self._db.automationtaskmodel_set.filter(finished=None)
        if len(last_tasks) == 0:  # Start
            return None, self.start
        elif len(last_tasks) == 1:  # Last task
            task = getattr(self, last_tasks[0].status)
            return task, self.get_node(task._next)

    @property
    def id(self):
        return self._db.id

    @property
    def data(self):
        assert self._db is not None, "Automation not bound to database"
        return self._db.data

    def save(self, *args, **kwargs):
        return self._db.save(*args, **kwargs)

    def nice(self, task_instance=None, next_task=None):
        """Run automation steps in a background thread to, e.g., do not block
        the request response cycle"""
        threading.Thread(target=self.run,
                         kwargs=dict(task_instance=task_instance, next_task=next_task)
                         ).start()

    def run(self, task_instance=None, next_node=None):
        """Execute automation until external responses are necessary"""
        assert not self.finished(), ValueError("Trying to run an already finished automation")

        if next_node is None:
            last_tasks = self._db.automationtaskmodel_set.filter(finished=None)
            if len(last_tasks) == 0:  # Start
                last, next_node = None, self._iter[None]  # First
            else:
                for last_task in last_tasks:
                    node = getattr(self, last_task.status)
                    self.run(last_task.previous, node)
                return

        while next_node is not None:
            task_instance = next_node.enter(task_instance)
            task_instance = next_node.execute(task_instance)
            last, next_node = task_instance, next_node.leave(task_instance)

    @classmethod
    def get_verbose_name(cls):
        if hasattr(cls, 'Meta'):
            if hasattr(cls.Meta, 'verbose_name'):
                return cls.Meta.verbose_name
        return f"automation {cls.__name__}"

    @classmethod
    def get_verbose_name_plural(cls):
        if hasattr(cls, 'Meta'):
            if hasattr(cls.Meta, 'verbose_name_plural'):
                return cls.Meta.verbose_name
        return f"automations {cls.__name__}"

    def finished(self):
        return self._db.finished

    @classmethod
    def on(cls, signal, **kwargs):
        signal.connect(cls.on_signal, **kwargs)

    @classmethod
    def on_signal(cls, sender, **kwargs):
        instance = cls()  # Instantiate class
        if hasattr(instance, 'started_by_signal') and callable(instance.started_by_signal):
            instance.started_by_signal(sender, kwargs)  # initialize based on sender data
        instance.run()  # run

    def __str__(self):
        return self.__class__.__name__


def get_automations(app=None):
    def check_module(mod):
        for item in dir(mod):
            attr = getattr(mod, item)
            if isinstance(attr, type) and issubclass(attr, Automation):
                automation_list.append((attr.__module__+'.'+ attr.__name__, attr.get_verbose_name()))

    automation_list = []
    if app is None:
        for name, mod in sys.modules.items():
            if name.rsplit(".")[-1] == "automations":
                check_module(mod)
    else:
        mod = __import__(app)
        if hasattr(mod, 'automations'):
            mod = getattr(mod, 'automations')
            check_module(mod)

    return automation_list
