Reference
#########


Automation class
****************

Automations are subclasses of the ``flow.Automation`` class.

flow.Automation
===============

flow.This and flow.this
***********************

Nodes for an automation are specified as class attributes. To refer to other notes in the definition of a node Django-automations offers two options:

1. Reference by string literal: ``.Next("next_node")`` will continue the automation with the node named ``next_node``
2. Reference using the global ``This`` object instance ``this``: ``.Next(this.next_node)`` refers to the Automation objects ``next_node`` attribute. Since the classes' attributes are not accessible at definition time the this object buffers the reference. It is resolved when an instance is created and executed.

The ``this`` object serves to avoid unnecessary strings and keep the automation definition less bloated with strings. To use the global ``this`` instance use ``from automations.flow import this``. Alternatively define your own app-specific ``this``:

.. code-block:: python

    from automations import flow

    this = flow.This()  # alternative to from automations.flow import this

    class TestAutomation(flow.Automation):
        singleton = True

        start = flow.Execute(this.worker_job).Next(this.next). # this notation
        next = flow.Execute("worker_job").Next("self.start")  # alternative notation with string literals

        def worker_job(self, task_instance):
            ...


Alternatively, forward references can be denoted by a string starting with ``"self."``. Both forms are equivalent and may be used interchangeably.


Node class
**********

flow.Node
=========

.. py:class:: flow.Node(*args, **kwargs)

    Base class for all nodes. Nodes are only functional if bound to ``flow.Automation`` subclass as attributes.  ``*args`` and ``**kwargs`` are ignored. It inherits from ``object``.

Nodes use the concept of modifiers to come to a somewhat human readable syntax. Modifiers are methods that return ``self``, the node's instance. This implies that modifier be chained just as in Javascript. ``SomeNode().AsSoonAs(this.ready).Next(this.end)`` is a valid node with two modifiers.

``flow.Node`` **is never directly used in any automation,** since it is a base class.

Modifiers for all subclasses of flow.Node
-----------------------------------------

The ``flow.Node`` class defines the following **modifiers** common to all subclasses. Some subclasses, however, add specific modifiers for their use.

.. py:method:: .Next(node)

    Sets the node to continue with after finishing this node. If omitted the automation continues with the chronologically next node of the class. ``.Next`` resembles a goto statement. ``.Next`` takes a string or a ``This`` object as a parameter. A string denotes the name of the next node. The this object allows for a different syntax. ``.Next("next_node")`` and ``this.next_node`` are equivalent.

.. py:method:: .AsSoonAs(condition)

    Waits for condition before continuing the automation. If condition is ``False`` the automation is interrupted and ``condition`` is checked the next time the automation instance is run.

    If ``condition`` is callable it will be called every time the condition needs to be evaluated.

.. py:method:: .AfterWaitingUntil(datetime)

    stops the automation until the specific datetime has passed. Note that depending on how the scheduler runs the automation there might be a significant time slip between ``datetime`` and the real execution time. It is only guaranteed that the node is not executed before. ``datetime`` may be a callable.

.. py:method:: .AfterPausingFor(timedelta)

    stops the automation for a specific amount of time. This is roughly equivalent to ``.AfterWaitingUntil(lambda x: now()+timedelta)``. ``timedelta`` may be a callable.


Attributes
----------

.. py:attribute:: .data

    References a JsonField of the node's automation instance. Each instance of an automation can carry additional data in form of a JsonField. This data is shared by all nodes of the automation instance. The node's attribute returns the common JsonField. Any changes in the field need to be saved using ``.data.save()`` or they might be lost.

    Attached model objects will be referenced by their id in the ``.data`` attribute. Beyond this the automation may use the data field to safe its   state in any way it prefers **as long as the dict is json serializable**. This excludes ``datetime`` objects or ``timedelta`` objects.

Additional methods
------------------

Additional methods differ from modifiers since they do **not** return ``self``.

.. py:method:: .ready(self, automation_instance)

    Is called by the newly initialized Automation instance to bind the nodes to the instance. Typically, there is no need to call it from other apps.

.. py:method:: .get_automation_name(self)

    Returns the (dotted) name of the Automation instance class the node is bound to. Automations are identified by this name.

.. py:method:: .resolve(self, value)

    Resolves the value to the node's automation attribute if ``value`` is either a ``This`` object or a string with the name of a node's automation attribute.




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

.. py:class:: flow.Execute(func, threaded=False, *args, **kwargs)

    runs a callable, typically a method of the automation. The method gets passed a parameter, called ``task_instance`` which is an instance of the ``AutomationTaskModel``. It gives the method access to the processes json database.

    The ``*args`` and ``**kwargs`` are passed to ``func``. If the function returns a json-serializable result it will be stored in the task instance in the database.

    Subclass ``flow.Execute`` to create your own executable nodes, e.g. ``class SendEMail(flow.Execute)``. Implement a method named ``method``. It gets passed a ``task_instance`` and all parameters of the node.

``flow.Execute`` has one specific modifier.

.. py:method:: .OnError(next_node)

    defines a node to continue with in case the ``Execute`` node fails with an exception. If no ``.OnError`` modifier is given the automation will stop if an error occurs. The error information is kept in the task instance in the database.

flow.If
=======

.. py:class:: flow.If(condition)

    is a conditional node which needs at least the ``.Then()`` modifier and optionally can contain an ``.Else()`` modifier.

.. py:method:: .Then(parameter)

    contains either a callable that is Executed (see ``flow.Execute``) or a reference to another node where the automation is continued, if the condition is ``True``.

.. py:method:: .Else(parameter)

    specifies what is to be done in case the condition is ``False``. If it is omitted the automation continues with the next node.


flow.Split
==========

.. py:class:: flow.Split()

    spawns two or more paths which are to be executed independently. These nodes are given by one or more ``.Next()`` modifiers. (Example ``flow.Split().Next(this.path1).Next(this.path2).Next(this.path3)``). These paths all need to end in the same ``flow.Join()`` node.




flow.Join
=========

.. py:class:: flow.Join()

    stops the automation until all paths spawned by the same ``flow.Split()`` have arrived at this node.


flow.SendMessage
================

.. py:class:: flow.SendMessage(target, message, token=None, data=None)

    Sends a message to other (unfinished) automation instances. ``target`` can either be an ``int`` giving the automation id of the automation instance the message is sent to. It can be an Automation instance that receives the message, or it can be an Automation calls. Then the message is sent to all running instances of that class. The class can be replaced by a string with the dotted path to the class definition.

   A message is nothing but a method of the receiving class called ``receive_<<message>>``. This method will be called for the target instance giving the optional parameters ``token`` and ``data``. Token typically is a string to define more specifically what the message is supposed to mean. ``data`` can be any pyhton object.

.. note::

    The message is the same mechanism used by the template tags or CMS plugins to send a message when a specific page is rendered. If the message comes from the template tag or plugin ``date`` is the request object.


flow.Form
=========

.. py:class:: flow.Form(form, template_name=None, description="", context={})

    Represents a user interaction with a Django Form. The form's class is passed as ``form``. It will be rendered using the optional ``template_name``. If ``template_name`` is not provided, Django automations looks for the ``default_template_name`` attribute of the automation class. Use the ``default_template_name`` attribute if all forms of an automation share the same template. If neither is given Django Automations will fall back to ``"automations/form_view.html"``.

    Also optional is ``description``, a text that explains what the user is expected to do with the form, e.g., validate its entries. The description can, e.g., be shown to a user when editing the form, or in her task list.

    The form is redered by a Django ``FormView``. Additional context for the template is provided by the ``FormView``

        * project-wide using ``settings.ATM_FORM_VIEW_CONTEXT`` in the :ref:`project's settings file<ATM_FORM_VIEW_CONTEXT>`,
        * defining the ``context`` attribute for the whole Automation class, and
        * specifying the ``context`` parameter in an individual ``flow.Form``.

The ``flow.Form`` has two extra modifiers to assign the task to a user or a group of users:

.. py:method:: .User(**kwargs)

    assigns the form to a single user who will have to process it. For the time being the user needs to be unique.

.. py:method:: .Group(**kwargs)

    assigns the form to all members of a user group. Selectors typically are only ``id=1`` or ``name="admins"``.

.. py:method:: .Permission(str)

    assigns the form to all users who have the permission given by a string dot-formatted: ``app_name.codename``. ``app_name`` ist the name of the Django app which provides the permission and ``codename`` is the permission's name. An example could be ``my_app.add_mymodel``. This permission allows an user to add an instance of My_App's ``MyModel`` model. For details on permissions see `Django's Permission documentation <https://docs.djangoproject.com/en/dev/topics/auth/default/#permissions-and-authorization>`_. Multiple ``.Permission(str)`` modifiers can be added implying the a user woulde require **all** permissions requested.

If more than one modifier is given, ``.User``, ``.Group``, and ``.Permission`` have all to be satisfied. If a user loses a required group membership he cannot process the form any more. The same is true for permissions. Superusers  can always process the form.

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

The `Django-CMS <https://www.django-cms.org/>`_ dependency is weak. Installing Django Automations will not require or trigger the installation of Django-CMS.

.. note::
    If you want to use Django Automations's CMS plugins, be sure to include ``automations.cms_automations`` in your ``INSTALLED_APPS`` settings.

Alternatively pure Django users can use :ref:`template tags<Template tags>` instead.

CMS Plugins
===========



Task List Plugin
----------------

.. py:class:: AutomationTaskList


This plugin shows all interactions required for automations to continue their work from the current user. It will never show tasks for the anonymous user (nobody logged in).

With this plugin the task list can be part of any CMS page. It is helpful if the user's tasks are to be shown as a part of a page, say, a dashboard.

In the project settings a choice of template can be defined. CMS page authors can chose the appropriate template do adjust the plugin's look and feel.

Status Plugin
-------------

.. py:class:: AutomationStatus

This plugin allows a user to see the status of the automation. The automation instance is defined by get parameters, either ``atm_id`` giving the automation model instance id or ``task_id`` giving the id of an automation's task.

Additionally a parameter ``KEY`` is specified which is unique for an automation and is used to prevent unauthorized access.

Automations may chose to offer status templates. They have to be declared in the Automations Meta class:

.. code-block:: python

    class MyAutomation(flow.Automation):
        class Meta:
            status_template = "my_automation/status.html", _("Current status")
            issue_template = "my_automation/issues.html", _("Problem sheet")

Any property with a name that ends on ``_template`` in the automation's Meta class is considered to be a template path for some sort of status view. For user friedlyness a verbose name can be added. Once declared the plugin will offer all status templates.

The templates receive the automation class and automation instance in the context with the keys ``automation`` and ``automation_instance``, respectively.


.. _automation_hook:

Send Message Plugin
-------------------

.. py:class:: AutomationHook


The automation hook does not display or render anything. Its purpose is to send a message to the automation, if a page is viewd. If on this page this plugin should be included. It offers all receiving automations and its receiver ports.

An automation declares an receiving slot by defining a method with a name starting with ``receive_``, e.g., ``receive_add_prarticipant_to_webinar``. All such slots are open for the Send Message Plugin and the example will appear as "Add participant to webinar" (capitalized, and underscores replaced by spaces).

The receiver will be passed an optional token and a data object which in this case is the request object.

Views
*****

TaskView
========

TaskListView
============

Templates
*********

Django Automation comes with simplistic templates. They are largely thought to be a reference for implementing your project-specific set of templates which probably include some more markup to adapt to your project's look and feel.

All template can be replaced simply by offering alternatives in your project's template folder. This is the structure:

::

    └── automations
        ├── base.html
        ├── cms
        │   └── empty_template.html
        ├── form_view.html
        ├── includes
        │   ├── form_view.html
        │   ├── task_item.html
        │   └── task_list.html
        └── task_list.html



The templates can be replaced individually. It is not necessary (though certainly possible) to replicate the whole tree.

The templates in the ``includes`` subdirectory are also used by the :ref:`Django-CMS plugins<CMS Plugins>`.


``base.html``
=============

All other templates extend automation's base template. Modify this template to bind into your project's template hierarchy.

``cms/empty_template.html``
===========================

Literally an empty file. Only necessary for the :ref:`Django-CMS plugin AutomationHook<automation_hook>`. The automation hook does not render anything by using this template.

``form_view.html``
==================

This is a simple fall-back template if no templates are given in a ``Form()`` node. Ideally, you specify the correct template by note or process. See :ref:`flow.Form<flow.Form>`.


``task_list.html``
==================

This is the template used by the ``TaskListView``.


Template tags
*************

Management command
*******************


.. code-block:: bash

    python manage.py automation_step

This wrapper calls the class method ``models.AutomationModel.run()`` which in turn lets all automations run which are not waiting for a response (filled form, other condition) or a certain point in time.


Settings in ``settings.py``
***************************

.. _ATM_FORM_VIEW_CONTEXT:

.. py:attribute:: settings.ATM_FORM_VIEW_CONTEXT

    The ``Form()`` nodes and its subclasses present the forms to the user using a Django ``FormView``. It is an dictionary which will be added to the template's context when rendering. The dictionary items may be overwritten by an automation classes ``context`` attribute or by a node's ``context`` parameter.
