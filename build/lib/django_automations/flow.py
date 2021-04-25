# coding=utf-8
import threading
import traceback
from copy import copy

from django.core.exceptions import ImproperlyConfigured
from django.db.models.base import ModelBase
from django.db.transaction import atomic
from django.utils.timezone import now

import datetime

from . import models


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
    def __init__(self):
        self._conditions = []
        self._next = None
        self._wait = None

    @staticmethod
    def eval(sth, task):
        return sth(task) if callable(sth) else sth

    def ready(self, automation_instance, name):
        self._automation = automation_instance
        self._name = name
        self._conditions = [automation_instance.get_node(condition) for condition in self._conditions]

    def get_automation_name(self):
        return self._automation.__class__.__name__

    def get_node(self, node):
        value = getattr(self, node)
        if isinstance(value, ThisObject):  # This object?
            value = getattr(self._automation, value.attr)   # get automation attribute
            setattr(self, node, value)  # Remember
        return value

    @atomic
    def enter(self, prev_task=None):
        db = self._automation._db
        assert db.finished is not None, "Node entered w/o previous node left"
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
                next_node = self.get_node('_next')
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
        earliest_execution = self.eval(self.get_node('_wait'), task_instance)
        if earliest_execution < now():
            return task_instance
        if self._automation._db.paused_until:
            self._automation._db.paused_until = min(self._automation._db.paused_until, earliest_execution)
        else:
            self._automation._db.paused_until = earliest_execution
        self._automation._db.save()
        return self.release_lock(task_instance)

    def execute(self, task_instance):
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

    def leave(self, task_instance: models.AutomationTaskModel):
        task_instance.finished = now()
        task_instance.save()


class Repeat(Node):
    def __init__(self, start=None):
        if start is None:
            start = self._automation.start

        super().__init__()
        self._next = start
        self._interval = None
        self._startpoint = None

    @on_execution_path
    def repeat_handler(self, task_instance: models.AutomationTaskModel):
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
            raise ImproperlyConfigured(f"Multiple inverval statements")
        self._interval = datetime.timedelta(days=1)
        self._startpoint = now()
        self._startpoint.replace(hour=hour, minute=minute)
        return self

    def EveryHour(self, hours=1):
        if self._interval is not None:
            raise ImproperlyConfigured(f"Multiple inverval statements")
        self._interval = datetime.timedelta(hours=hours)
        return self

    def EveryNMinutes(self, minutes):
        if self._interval is not None:
            raise ImproperlyConfigured(f"Multiple inverval statements")
        self._interval = datetime.timedelta(minutes=minutes)
        return self

    def EveryNDays(self, days):
        if self._interval is not None:
            raise ImproperlyConfigured(f"Multiple inverval statements")
        self._interval = datetime.timedelta(days=days)
        return self


class Execute(Node):
    def __init__(self, *args, **kwargs):
        super().__init__()
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
                try:
                    task_instance.message = "OK"
                    task_instance.result = result
                except TypeError:
                    pass
            except Exception as err:
                self._err = err
                try:
                    task_instance.message = repr(err)[:settings.MAX_FIELD_LENGTH]
                    task_instance.result = dict(erro=traceback.format_exc())
                except TypeError:
                    pass

        if self.args is not None:
            args = (getattr(self._automation, value.attr) if isinstance(value, ThisObject)
                    else value for value in self.args)
            kwargs = {key: getattr(self._automation, value.attr) if isinstance(value, ThisObject)
                      else value for key, value in self.kwargs.items()}

            if kwargs.get("threaded", False):
                assert self._on_error is None, "No .OnError statement on threaded executions"
                threading.Thread(target=func, args=[task_instance] + args, kwargs = kwargs).start()
            else:
                func(task_instance, *args, **kwargs)
                if self._err and self._on_error:
                    self._next = self._on_error
        return task_instance

    def execute(self, task_instance):
        task_instance = super().execute(task_instance)
        return self.execute_handler(task_instance)

    def OnError(self, next_node):
        if self._on_error is not None:
            raise ImproperlyConfigured(f"Multiple .OnError statements")
        self._on_error = next_node
        return self


class If(Execute):
    def __init__(self, condition):
        super().__init__(None)
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
    def if_handler(self, task_instance):
        if self._then is None:
            raise ImproperlyConfigured(f"Missing .Then statement")
        opt = self.get_node('_then') if self.eval(self.get_node('_condition'), task_instance) \
            else self.get_node('_else')
        if isinstance(opt, Node):
            self._next = opt
        elif opt is not None:
            self._func = opt
            return self.execute_handler(task_instance)
        return task_instance

    def execute(self, task_instance):
        task_instance = super().execute(task_instance)
        return self.if_handler(task_instance)


class Automation:
    model_class = models.AutomationModel
    singleton = False

    start = End()
    end = End()  # Endpoint of automation

    def __init__(self, **kwargs):
        super().__init__()
        prev = None
        self._iter = {}
        for name, attr in self.__class__.__dict__.items():
            if isinstance(attr, Node):
                self._iter[prev] = attr
                attr.ready(self, name)
                prev = attr
            if isinstance(attr, ModelBase):  # Attach to Model instance
                at_c = copy(attr)  # Create copies of name and Model (attr)
                nm_c = copy(name)
                setattr(self.__class__, name,
                        property(lambda self: self.get_model_instance(at_c, nm_c), self))
                if name not in kwargs:
                    kwargs[name] = None
                elif not isinstance(kwargs[name], int):  # Convert instance to id
                    kwargs[name] = kwargs[name].id
        self._iter[prev] = None  # Last item

        if 'automation_id' in kwargs:  # Attach to automation in DB
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
        if not hasattr(self, '_'+name):
            setattr(self, '_'+name, model.objects.get(id=self._db.data[name]))
        return getattr(self, '_'+name)

    def get_automation_class_name(self):
        return self.__module__ + '.' + self.__class__.__name__

    def get_node(self, node):
        """Resolve ThisObject references"""
        if isinstance(node, ThisObject):
            return getattr(self, node.attr)
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


    def run(self, task_instance=None, next_task=None):
        """Execute automation until external responses are necessary"""
        assert not self.finished(), ValueError("Trying to run an already finished automation")

        if next_task is None:
            last_tasks = self._db.automationtaskmodel_set.filter(finished=None)
            if len(last_tasks) == 0:  # Start
                last, next_task = None, self._iter[None]  # First
            else:
                for last_task in last_tasks:
                    task = getattr(self, last_task.status)
                    self.run(last_task.previous, task)
                return

        while next_task is not None:
            task_instance = next_task.enter(task_instance)
            task_instance = next_task.execute(task_instance)
            last, next_task = task_instance, next_task.leave(task_instance)

    def finished(self):
        return self._db.finished

    def __str__(self):
        return self.__class__.__name__
