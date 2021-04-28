Reference
#########


flow.Automation
***************



flow.This and flow.this
***********************

Nodes for an automation are specified as class properties. To refer to other notes in the definition of a node Django-automations offers two options:

1. Reference by string literal: ``.Next("next_node")`` will continue the automation with the node named ``next_node``
2. Reference using the global ``This`` object instance ``this``: ``.Next(this.next_node)`` refers to the Automation objects ``next_node`` property. Since the classes' properties are not accessible at definition time the this object buffers the reference. It is resolved when an instance is created and executed.

The ``this`` object serves to avoid unnecessary strings and keep the automation definition less bloated with strings. To use the global ``this`` instance use ``from automations.flow import this``. Alternatively define your own app-specific ``this``:

.. code-block:: python

    from automations import flow

    this = flow.This()  # alternative to from automations.flow import this

    class TestAutomation(flow.Automation):
        singleton = True

        start = flow.Execute(this.worker_job).Next(this.next). # this notation
        next = flow.Execute("worker_job").Next("start")  # notation with string literals

        def worker_job(self, task_instance):
            ...


Base class flow.Node
********************

.. py:class:: flow.Node(*args, **kwargs)

    Base class for all nodes. Modifiers return `self`, i.e., they can be chained as in Javascript. ``SomeNode().AsSoonAs(this.ready).Next(this.end)`` is a valid node with two modifiers. ``*args`` and ``**kwargs`` are ignored. It inherits from ``object``.

    ``flow.Node`` **is never directly used in any automation,** since it is a base class.

Modifiers for all subclasses of flow.Node
=========================================

It defines the following **modifiers**

.. py:method:: .Next(node)

    Sets the node to continue with after finishing this node. If omitted the automation continues with the chronologically next node of the class. ``.Next`` resembles a goto statement. ``.Next`` takes a string or a ``This`` object as a parameter. A string denotes the name of the next node. The this object allows for a different syntax. ``.Next("next_node")`` and ``this.next_node`` are equivalent.

.. py:method:: .AsSoonAs(condition)

    Waits for condition before continuing the automation. If condition is `False` the automation is interrupted and ``condition`` is checked the next time the automation instance is run.

.. py:method:: .AfterWaitingUntil(datetime)

    stops the automation until the specific datetime has passed. Note that depending on how the scheduler runs the automation there might be a significant time slip between ``datetime`` and the real execution time. It is only guaranteed that the node is not executed before. ``datetime`` may be a callable.

.. py:method:: .AfterPausingFor(timedelta)

    stops the automation for a specific amount of time. This is roughly equivalent to ``.AfterWaitingUntil(lambda x: now()+timedelta)``.


Properties
==========

.. py:attribute:: .data

    References a JsonField of the node's automation instance. Each instance of an automation can carry additional data in form of a JsonField. This data is shared by all nodes of the automation. The node's property returns the common JsonField. Any changes in the field need to be saved using `.data.save()` or they might be lost.

    Attached model objects will be referenced by their id in the `.data` property. Beyond this the automation may use the data field to safe its   state in any way it prefers **as long as the dict is json serializable**. This excludes ``datetime`` objects or ``timedelta`` objects.

Additional methods
==================

Additonal methods differ from modifiers since they do **not** return ``self``.

.. py:method:: .ready(self, automation_instance)

    Is called by the newly initialized Automation instance to bind the nodes to the instance. Typically, there is no need to call it from other apps.

.. py:method:: get_automation_name(self)

    Returns the (dotted) name of the Automation instance class the node is bound to. Automations are identified by this name.

.. py:method:: resolve(self, value)

    Resolves the value to the node's automation property if ``value`` is either a ``This`` object or a string with the name of a node's automation property.



Subclasses of form.Node
***********************


flow.End
========

.. py:class:: flow.End()

    ends an automation. All finite automations need an ``.End()`` node. An automation instance that has ended cannot be executed. If you call its ``run`` method it will throw an error. As long as the automation is not a singleton you can of course at any time instantiate a new instance of the same automation which will run from the start.



flow.Repeat
===========

.. py:class:: flow.Repeat(start=None)

    allows for repetitive automations (which do not need an ``flow.End()`` node. The automation will resume at node given by the ``start`` argument, or - if ommitted - from the first node.

The repetition patter is described by **modifiers**:

.. py:method:: .EveryDayAt(hour, minute)

    for daily automations which need to run at a certain hour and minute.

.. py:method:: .EveryHour(no_of_hours=1)

    for hourly automations or automations that need to run every ``no_of_hours`` hour.

.. py:method:: .EveryNMinutes(minutes)

    for regular automations that need to run every ``minutes`` minutes.




flow.Execute
============

.. py:class:: flow.Execute(func, *args, **kwargs)

    runs a callable, typically a method of the automation. The method gets passed a parameter, called ``task_instance`` which is an instance of the ``AutomationTaskModel``. It gives the method access to the processes json dataspace.

    The ``*args`` and ``**kwargs`` are passed to ``func``.

    Subclass ``flow.Execute`` to create your own executable nodes, e.g. ``class SendEMail(flow.Execute)``. Implement a method named ``method``. It gets passed a ``task_instance`` and all parameters of the node.

``flow.Execute`` has one specific modifier.

.. py:method:: .OnError(next_node)

    defines a node to continue with in case the ``Execute`` node fails with an exception.

flow.If
=======

.. py:class:: flow.If(condition)

    is a conditional node which needs at least the ``.Then()`` modifier and optionally can contain an ``.Else()`` modifier.

.. py:method:: .Then(parameter)

    contains either a callable that is Executed (see ``flow.Execute``) or a reference to another node where the automation is continued, if the condition is ``True``.

.. py:method: .Else(parameter)

    specifies what is to be done in case the condition is ``False``. If it is omitted the automation continues with the next node.


flow.Split
==========

.. py:class:: flow.Split()

    spawns two or more paths which are to be executed independently. These nodes are given by one or more ``.Next()`` modifiers. (Example ``flow.Split().Next(this.path1).Next(this.path2).Next(this.path3)``). These paths all need to end in the same ``flow.Join()`` node.




flow.Join
=========

.. py:class:: flow.Join()

    stops the automation until all paths spawned by the same ``flow.Split()`` have arrived at this node.


flow.Form
=========

.. py:class:: flow.Form(form, template_name=None, description="")

    Represents a user interaction with a Django Form. The form's class is passed as ``form``. It will be rendered using the optional ``template_name``. If ``template_name`` is not provided, Django automations looks for the ``default_template_name`` property of the automation class. Use the ``default_template_name`` property if all forms of an automation share the same template.

    Also optional is ``description``, a text that explains what the user is expected to do with the form, e.g., validate its entries.

The ``flow.Form`` has two extra modifiers to assign the task to a user or a group of users:

.. py:method:: .User(**kwargs)

    assigns the form to a single user who will have to process it. For the time being the user needs to be unique.

.. py:method:: .Group(**kwargs)

    assigns the form to all members of a user group. Selectors typically are only ``id=1`` or ``name="admins"``.

If both are given both the user and any user of the group can process the form. At least one of the two modifiers is required. The ``**kwargs`` are used to identify the user/group by passing them to the ``User`` model. Examples might be ``.User(id=1)``, ``.User(username='admin')`` or ``.Group(name='Management')``.

The automation will continue as soon as the form is submitted and validated, i.e. in the request response cycle. If you need to execute an action after this step consider using a threaded ``Execute()`` not to keep the user waiting for too long.


flow.ModelForm
==============

.. py:class:: flow.ModelForm(form, key, template_name=None, description="")

    Represents a user interaction with a model. ``form`` needs to be a subclass of Django's ``models.ModelForm``. The model is fixed in the form's ``Meta`` class (see `Django's ModelForm documentation <https://docs.djangoproject.com/en/dev/topics/forms/modelforms/>`_)


flow.get_automations
********************

.. py:function:: flow.get_automations(app=None)

    returns either all automations in the current project (including those in dependencies if they are loaded). All modules or submodules named ``automations.py`` are searched. If the ``app`` parameter is given only ``app.automations`` is searched. Other submodules of ``app`` are ignored.

The result is a list of tuples, the first one being the automations dotted path, the second one its human readably name. It differs only from the path if ``verbose_name`` is set in the automations ``Meta`` subclass.

Django-CMS integration
**********************

Teh Django-CMS dependency is weak, i.e. if the Django-CMS package is not installed, Django Automations will not force an installation. Instead all functionality in this section will just not be available.

Alternatively pure Django users can use :ref:`template tags<Template tags>` instead.

views
*****

Template tags
*************