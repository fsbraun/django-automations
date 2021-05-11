# coding=utf-8
import datetime
import functools
import json
import sys
import threading
import traceback
from copy import copy

from django.contrib.auth.models import User, Group, Permission
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.db.models.base import ModelBase
from django.db.transaction import atomic
from django.utils.timezone import now

from . import models, settings

"""To allow forward references in Automation object "this" is defined"""


class ThisAttribute:
    """Wrapper for forward-reference to a named attribute"""

    def __init__(self, attr):
        self.attr = attr

    def __repr__(self):
        return f"this.{self.attr}"


class This:
    """Generator for reference to a named attribute"""

    def __getattr__(self, item):
        return ThisAttribute(item)


this = This()
"""Global instance"""

"""
"""


def on_execution_path(m):
    """Decorator to ensure automatic pausing of automations in
    case of WaitUntil, PauseFor and When"""
    @functools.wraps(m)
    def wrapper(self, task, *args, **kwargs):
        try:
            return None if task is None else m(self, task, *args, **kwargs)
        except Exception as err:
            if isinstance(err, ImproperlyConfigured):
                raise err
            if task is not None:
                self.store_result(task, repr(err), dict(error=traceback.format_exc()))
                self.release_lock(task)
                self._automation._db.finished = True
                self._automation._db.save()

            return None
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
        self._conditions = [self.resolve(condition) for condition in self._conditions]

    def get_automation_name(self):
        """returns the name of the Automation instance class the node is bound to"""
        return self._automation.__class__.__name__

    def __getattribute__(self, item):
        value = super().__getattribute__(item)
        if isinstance(value, ThisAttribute) or (isinstance(value, str) and value.startswith('self.')):
            value = self.resolve(value)
            setattr(self, item, value)  # remember
        return value

    def resolve(self, value):
        if isinstance(value, ThisAttribute):  # This object?
            value = getattr(self._automation, value.attr)  # get automation attribute
        elif isinstance(value, str) and value.startswith('self.'):  # String literal instead of this
            value = getattr(self._automation, value[5:])
        return value

    @atomic
    def enter(self, prev_task=None):
        assert prev_task is None or prev_task.finished is not None, "Node entered w/o previous node left"
        db = self._automation._db
        assert isinstance(db, models.AutomationModel)
        task, _ = db.automationtaskmodel_set.get_or_create(
            previous=prev_task,
            status=self._name,
            defaults=dict(
                locked=0,
            ),
        )
        if task.locked > 0:
            return None
        task.locked += 1
        task.save()
        return task

    @atomic
    def release_lock(self, task: models.AutomationTaskModel):
        task.locked -= 1
        task.save()
        return None

    @staticmethod
    def store_result(task: models.AutomationTaskModel, message, result):
        task.message = message[0:settings.MAX_FIELD_LENGTH]
        try:  # Check if result is json serializable
            json.dumps(result)  # Raise error if not json-serializable
            task.result = result  # if it is, store it
        except TypeError:
            task.result = None
        task.save()

    def leave(self, task: models.AutomationTaskModel):
        if task is not None:
            task.finished = now()
            self.release_lock(task)
            if self._next is None:
                next_node = self._automation._iter[self]
            else:
                next_node = self._next
            if next_node is None:
                raise ImproperlyConfigured("No End() node after %s" % self._name)
            return next_node

    @on_execution_path
    def when_handler(self, task):
        for condition in self._conditions:
            if not self.eval(condition, task):
                return self.release_lock(task)
        return task

    @on_execution_path
    def wait_handler(self, task: models.AutomationTaskModel):
        if self._wait is None:
            return task
        earliest_execution = self.eval(self._wait, task)
        if earliest_execution < now():
            return task
        if self._automation._db.paused_until:
            self._automation._db.paused_until = min(self._automation._db.paused_until, earliest_execution)
        else:
            self._automation._db.paused_until = earliest_execution
        self._automation._db.save()
        return self.release_lock(task)

    def execute(self, task: models.AutomationTaskModel):
        return self.when_handler(self.wait_handler(task))

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

    def __repr__(self):
        return f"<{f'{self._name}: ' if self._automation else ''}" \
               f"{self._automation if self._automation else 'unbound'} {self.__class__.__name__} node>"


class End(Node):
    def execute(self, task):
        self._automation._db.finished = True
        self._automation._db.save()
        return task

    def leave(self, task):
        task.finished = now()
        task.locked = 0;
        task.save()


class Repeat(Node):
    def __init__(self, start=None, **kwargs):
        if start is None:
            start = self._automation.start

        super().__init__(**kwargs)
        self._next = start
        self._interval = None
        self._startpoint = None

    @on_execution_path
    def repeat_handler(self, task):
        if self._startpoint is None:
            self._startpoint = now()
        elif now() < self._startpoint:
            return self.release_lock(task)
        db = self._automation._db
        if db.paused_until:
            if now() < db.paused_until:
                return self.release_lock(task)
        else:
            db.paused_until = self._startpoint
        while self._automation._db.paused_until < now():
            db.paused_until += self._interval
        db.save()
        return task

    def execute(self, task: models.AutomationTaskModel):
        task = super().execute(task)
        return self.repeat_handler(task)

    def At(self, hour, minute):
        if self._interval is None:
            raise ImproperlyConfigured(f"Repeat().At: interval statement necessary before")
        if self._interval < datetime.timedelta(days=1):
            raise ImproperlyConfigured(f"Repeat().At: interval >= one day required")
        if self._startpoint is not None:
            raise ImproperlyConfigured(f"Repeat(): Only one .At modifier possible")
        self._startpoint = now()
        self._startpoint.replace(hour=hour, minute=minute)
        return self

    def EveryHour(self, hours=1):
        if self._interval is not None:
            raise ImproperlyConfigured(f"Repeat(): Multiple interval statements")
        self._interval = datetime.timedelta(hours=hours)
        return self

    def EveryNMinutes(self, minutes):
        if self._interval is not None:
            raise ImproperlyConfigured(f"Repeat(): Multiple interval statements")
        self._interval = datetime.timedelta(minutes=minutes)
        return self

    def EveryNDays(self, days):
        if self._interval is not None:
            raise ImproperlyConfigured(f"Repeat(): Multiple interval statements")
        self._interval = datetime.timedelta(days=days)
        return self

    def EveryDay(self):
        return self.EveryNDays(days=1)


class Split(Node):
    """Spawn several tasks which have to be joined by a Join() node"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._splits = []

    def Next(self, node):
        self._splits.append(node)
        return self

    def execute(self, task: models.AutomationTaskModel):
        task = super().execute(task)
        if task:
            assert len(self._splits) > 0, "at least one .Next statement needed for Split()"
            db = self._automation._db
            tasks = list(
                db.automationtaskmodel_set.create(  # Create splits
                    previous=task,
                    status=self.resolve(split)._name,
                    locked=0,
                ) for split in self._splits)
            self.leave(task)
            for task in tasks:
                self._automation.run(task.previous, getattr(self._automation, task.status))  # Run other splits
            return None
        return task


class Join(Node):
    """Collect tasks spawned by Split"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def execute(self, task: models.AutomationTaskModel):
        task = super().execute(task)
        if task:
            split_task = self.get_split(task)
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
                self.leave(task)
                return None
        return task

    def get_split(self, task):
        split_task = task.previous
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

    def method(self, task, *args, **kwargs):
        func = args[0]
        if not callable(func):
            raise ImproperlyConfigured(f"Execute: expected callable, got {func.__class__.__name__}")
        return func(task, *self.args[1:], **self.kwargs)

    @on_execution_path
    def execute_handler(self, task: models.AutomationTaskModel):
        def func(task, *args, **kwargs):
            self._err = None
            try:
                result = self.method(task, *args, **kwargs)
                self.store_result(task, "OK", result)
            except Exception as err:
                if isinstance(err, ImproperlyConfigured):
                    raise err
                self._err = err
                self.store_result(task, repr(err), dict(error=traceback.format_exc()))


        if self.args is not None and len(self.args) > 0:  # Empty arguments: No-op
            args = (self.resolve(value) for value in self.args)
            kwargs = {key: self.resolve(value) for key, value in self.kwargs.items()}
            if kwargs.get("threaded", False):
                assert self._on_error is None, "No .OnError statement on threaded executions"
                threading.Thread(target=func, args=[task] + list(args), kwargs=kwargs).start()
            else:
                func(task, *args, **kwargs)
                if self._err:
                    if self._on_error:
                        self._next = self._on_error
                    else:
                        self.release_lock(task)
                        self._automation._db.finished = True
                        self._automation._db.save()
                        return None
        return task

    def execute(self, task: models.AutomationTaskModel):
        task = super().execute(task)
        return self.execute_handler(task)

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
        self._func = lambda x: None

    def Then(self, *clause_args, **clause_kwargs):
        if self._then is not None:
            raise ImproperlyConfigured(f"Multiple .Then statements")
        self._then = (clause_args, clause_kwargs)
        return self

    def Else(self, *clause_args, **clause_kwargs):
        if self._else is not None:
            raise ImproperlyConfigured(f"Multiple .Else statements")
        self._else = (clause_args, clause_kwargs)
        return self

    @on_execution_path
    def if_handler(self, task: models.AutomationTaskModel):
        if self._then is None:
            raise ImproperlyConfigured(f"Missing .Then statement")
        this_path = self.eval(self._condition, task)
        clause = self._then if this_path else self._else
        if clause is not None:
            opt_args, opt_kwargs = clause
            if len(opt_args) == 1 and len(opt_kwargs) == 0:
                resolved = self.resolve(opt_args[0])
                if isinstance(resolved, Node) and not callable(resolved):
                    self.Next(resolved)
                    return task
            self.args = opt_args
            self.kwargs = opt_kwargs
            return self.execute_handler(task)
        return task

    def execute(self, task: models.AutomationTaskModel):
        # Do not execute super() since If inherits from Execute and there
        # is nothing to execute, call Node.execute instead
        task = Node.execute(self, task)
        return self.if_handler(task)


class Form(Node):
    def __init__(self, form, template_name=None, context=None, **kwargs):
        super().__init__(**kwargs)
        self._form = form
        self._context = context if context is not None else {}
        self._template_name = template_name
        self._user = None
        self._group = None
        self._permissions = []
        self._form_kwargs = {}
        self._run = True

    def execute(self, task: models.AutomationTaskModel):
        task = super().execute(task)

        if task is not None:
            if self._user is None and self._group and not self._permissions:
                raise ImproperlyConfigured("From: at least one .User, .Group, .Permission has to be specified")
            task.interaction_user = self.get_user()
            task.interaction_group = self.get_group()
            if task.data.get(f"_{self._name}_validated", None) is None:
                task.requires_interaction = True
                self.release_lock(task)  # Release lock and stop automation until form is validated
                return None
        return task  # Continue with validated form

    def validate(self, task: models.AutomationTaskModel, request, form):
        task.automation.data[f"_{self._name}_validated"] = request.user.id
        task.automation.save()

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
        self._permissions.append(permission)
        return self

    def get_users_with_permission(self):
        perm = Permission.objects.filter(codename__in=self._permissions)
        filter = Q(groups__permissions__in=perm) | Q(user_permissions__in=perm)
        if self._user is not None:
            filter = filter & Q(**self._user)
        if self._group is not None:
            filter = filter & Q(group_set__contains=self._group)
        users = User.objects.filter(filter).distinct()
        return users


class ModelForm(Form):
    def __init__(self, form, key, template_name=None, **kwargs):
        super().__init__(form, template_name, **kwargs)
        if hasattr(Automation, key):
            raise ImproperlyConfigured(f"Chose different key for ModelForm node: {key} is a property of "
                                       f"flow.Automations")
        self._instance_key = key
        self._form_kwargs = self.get_model_from_kwargs

    def get_model_from_kwargs(self, task):
        model = self._form.Meta.model  # Get model from Form's Meta class
        if self._instance_key in task.data:
            instances = model.objects.filter(id=task.data[self._instance_key])
            return dict(instance=instances[0] if len(instances) == 1 else None)
        else:
            return dict()


class SendMessage(Node):
    def __init__(self, target, message, token=None, allow_multiple_receivers=False, **kwargs):
        self._target = target
        self._message = message
        self._token = token
        self._allow_multiple_receivers = allow_multiple_receivers
        self.kwargs = kwargs
        super().__init__()

    @on_execution_path
    def send_handler(self, task):
        cls = self._target
        if isinstance(cls, str):
            cls = models.get_automation_class(cls)
        if issubclass(cls, Automation):
            results = cls.broadcast_message(self._message, self._token, data=self.kwargs)
        elif isinstance(cls, Automation) or isinstance(cls, int):
            results = [cls.dispatch_message(self._message, self._token, data=self.kwargs)]
        else:
            raise ImproperlyConfigured("")
        self.store_result(task, "OK", dict(results=results))
        return task

    def execute(self, task: models.AutomationTaskModel):
        task = super().execute(task)
        return self.send_handler(task)

#
# Automation class
#
#


def on_signal(signal, start=None, **kwargs):
    """decorator for automations to connect to Django signals"""
    def decorator(cls):
        cls.on(signal, start, **kwargs)
        return cls
    return decorator


class Automation:
    model_class = models.AutomationModel
    unique = False

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
        autorun = kwargs.pop("autorun", True)
        if 'automation' in kwargs:
            self._db = kwargs.pop('automation')
            autorun = False
            assert isinstance(self._db, models.AutomationModel), \
                "automation= parameter needs to be AutomationModel instance"
            assert not kwargs, "Too many arguments for automation %s. " \
                               "If 'automation' is given, no parameters allowed" % self.__clas__.__name__
        elif 'automation_id' in kwargs:  # Attach to automation in DB
            self._create_model_properties(kwargs)
            self._db, _ = self.model_class.objects.get_or_create(
                id=kwargs.pop('automation_id'),
                defaults=dict(
                    automation_class=self.get_automation_class_name(),
                    finished=False,
                    data=kwargs,
                ))
            autorun = False
            assert not kwargs, "Too many arguments for automation %s. " \
                               "If 'automation' is given, no parameters allowed" % self.__clas__.__name__
        elif self.unique is True:  # Create or get singleton in DB
            self._db, created = self.model_class.objects.get_or_create(
                automation_class=self.get_automation_class_name(),
            )
            if created:
                self._db.data = kwargs
                self._db.finished = False
                self._db.save()
            else:
                assert not kwargs, "Too many arguments for automation %s. " \
                                   "If 'automation' is given, no parameters allowed" % self.__clas__.__name__
        elif self.unique:
            assert isinstance(self.unique, (list, tuple)), ".singleton can be bool, list, tuple or None"
            for key in self.unique:
                assert key not in ("automation", "automation_id", "autorun"), \
                    f"'{key}' cannot be parameter to distinguish unique automations. Chose a different name."
                assert key in kwargs, "to ensure unqiue property, " \
                                      "create automation with '%s=...' parameter" % key
            qs = self.model_class.objects.filter(finished=False)
            for instance in qs:
                identical = sum((0 if key not in instance.data or instance.data[key] != kwargs[key] else 1
                                 for key in self.unique))
                if identical == len(self.unique):
                    self._db = instance
                    break
            else:
                self._create_model_properties(kwargs)
                self._db = self.model_class.objects.create(
                    automation_class=self.get_automation_class_name(),
                    finished=False,
                    data=kwargs,
                )
        else:
            self._create_model_properties(kwargs)
            self._db = self.model_class.objects.create(
                automation_class=self.get_automation_class_name(),
                finished=False,
                data=kwargs,
            )
        assert self._db is not None, "Internal error"
        if autorun:
            self.run()

    def _create_model_properties(self, kwargs):
        for name, value in kwargs.items():
            if isinstance(value, ModelBase):
                model_class = value.__class__
                setattr(self, name,  # Replace property by get_model_instance
                        property(lambda slf: slf.get_model_instance(model_class, name), self))
                kwargs[name] = kwargs[name].id

    def get_model_instance(self, model, name):
        if not hasattr(self, '_' + name):
            setattr(self, '_' + name, model.objects.get(id=self._db.data[name]))
        return getattr(self, '_' + name)

    def get_automation_class_name(self):
        return self.__module__ + '.' + self.__class__.__name__

    @property
    def id(self):
        return self._db.id

    @property
    def data(self):
        assert self._db is not None, "Automation not bound to database"
        return self._db.data

    def save(self, *args, **kwargs):
        return self._db.save(*args, **kwargs)

    def nice(self, task=None, next_task=None):
        """Run automation steps in a background thread to, e.g., do not block
        the request response cycle"""
        threading.Thread(target=self.run,
                         kwargs=dict(task=task, next_task=next_task)
                         ).start()

    def run(self, task=None, next_node=None):
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
            task = next_node.enter(task)
            task = next_node.execute(task)
            last, next_node = task, next_node.leave(task)
        return last

    @classmethod
    def get_verbose_name(cls):
        if hasattr(cls, 'Meta'):
            if hasattr(cls.Meta, 'verbose_name'):
                return cls.Meta.verbose_name
        return f"Automation {cls.__name__}"

    @classmethod
    def get_verbose_name_plural(cls):
        if hasattr(cls, 'Meta'):
            if hasattr(cls.Meta, 'verbose_name_plural'):
                return cls.Meta.verbose_name_plural
        return f"Automations {cls.__name__}"

    def finished(self):
        return self._db.finished

    def send_message(self, message, token, data=None):
        """RECEIVES message and dispatches it within the class
        Called send_message so that sending a message to an automation
        is `automation.send_message(...)"""
        if self.__class__.satisfies_data_requirements(message, data):
            method = getattr(self, "receive_"+message)
            return method(token, data)
        return None

    @classmethod
    def satisfies_data_requirements(cls, message, get):
        if hasattr(cls, "receive_" + message):
            method = getattr(cls, "receive_" + message)
            if not hasattr(method, "data_requirements"):
                return True
            accessor = get.GET if hasattr(get, 'GET') else get
            for param, type_class in method.data_requirements.items():
                if param not in accessor:
                    return False
                if not isinstance(accessor[param], type_class):  # Try simple conversion
                    try:
                        type_class(accessor[param])
                    except (ValueError, TypeError):
                        return False
            return True
        return False

    def kill(self):
        """Deletes the automation instance in models.AutomationModel"""
        self._db.delete()
        self._db = None


    @classmethod
    def dispatch_message(cls, automation, message, token, data):
        if cls.satisfies_data_requirements(message, data):
            if isinstance(automation, int):
                automation = cls(automation_id=automation)
            assert isinstance(automation, cls), f"Wrong class to dispatch message: " \
                                                f"{automation.__class__.__name__} found, " \
                                                f"{cls.__name__} expected"
            return automation.send_message(message, token, data)

    @classmethod
    def broadcast_message(cls, message, token, data):
        results = []
        if cls.satisfies_data_requirements(message, data):
            for automation in models.AutomationModel.objects.filter(
                    finished=False,
                    automation_class=cls.__module__+"."+cls.__name__,
            ):
                automation = cls(automation=automation)
                result = automation.send_message(message, token, data)
                results.append(result)
                if isinstance(result, str) and result == "received":
                    break
        return results

    @classmethod
    def create_on_message(cls, message, token, data):
        if cls.satisfies_data_requirements(message, data):
            kwargs = dict()
            accessor = data.GET if hasattr(data, 'GET') else data
            if isinstance(cls.unique, (list, tuple)):
                for param in cls.unique:
                    if param in accessor:
                        kwargs[param] = accessor.get(param)
            instance = cls(autorun=False, **kwargs)
            instance.send_message(message, token, data)
            return instance
        return None

    @classmethod
    def on(cls, signal, start=None, **kwargs):
        def creator(sender, **sargs):
            cls.on_signal(start, sender, **sargs)
        signal.connect(creator, weak=False, **kwargs)

    @classmethod
    def on_signal(cls, start, sender, **kwargs):
        instance = cls()  # Instantiate class
        if hasattr(instance, 'started_by_signal') and callable(instance.started_by_signal):
            instance.started_by_signal(sender, kwargs)  # initialize based on sender data
        instance.run(None, None if start is None else getattr(instance, start))  # run

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
        apps = app.split(".")

        mod = __import__(apps[0])
        for next in apps[1:]:
            mod = getattr(mod, next)

        check_module(mod)
        if hasattr(mod, 'automations'):
            mod = getattr(mod, 'automations')
            check_module(mod)

    return automation_list


def require_data_parameters(**kwargs):
    """decorates Automation class receiver methods to set the data_requirement attribute
    It is checked by cls.satisfies_data_requirements"""
    def decorator(method):
        method.data_requirements = kwargs
        return method
    return decorator
