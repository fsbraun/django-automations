Reference
#########


Automation class
****************

``flow.Automation`` is a class that provides the core functionality of Django Automations. To create an automation ``flow.Automation`` is subclassed with a list of properties of type ``flow.Note`` which are to executed one after the other.


flow.Automation
===============

Creating a subclass of ``flow.Automation`` is simple and similar to creating forms or models in Django.
The order of the properties defines the order of execution. All nodes can be adapted using modifiers.

Example:

.. code-block:: python

    from automations import flow

    this = flow.This()

    class IssueDiscussion(flow.Automation):
        issue_list = models.IssueList

        start =         flow.Execute(this.publish_announcement)
        parallel =      flow.Split().Next(this.moderation).Next(this.warning).Next(this.conf_call)

        moderation =    flow.If(this.no_new_mails).Then(this.repeat)
        moderate =      flow.Form(forms.MailModeration).Group(name='Moderators')
        repeat =        (flow.If(this.moderation_deadline_reached)
                            .Then(this.join)
                            .Else(this.moderation)
                        ).AfterPausingFor(datetime.timedelta(hours=1))

        warning =       (flow.Execute(this.send_deadline_warning)
                            .AfterPausingFor(datetime.timedelta(days=6))
                            .Next(this.join))

        conf_call =     flow.If(this.conf_call_this_week).Then(this.moderate_call).Else(this.join)
        moderate_call = flow.Execute(this.block_calendar)

        join          = flow.Join()
        evaluate      = flow.Execute(this.evaluate)
        end           = flow.End()

        def publish_anncouncement(self, task):
            ...

        def no_new_mails(self, task):
            # Do something to check mails
            return not new_mail_found

        ...


Note that each node has a name (start, parallel, ...). Execution of the automation starts at the first node and continues node by node as long as no branches are set (``.Next()``, ``.Then()``, or ``.Else()`` modifiers). Nodes need to have a name even if they are not the target of a branch.

It is customary to bracket nodes that continue over line breaks.

The ``.End()`` node deontes the end of the automation. Once it is reached the automation's instances' finished flag is set.

Short programs to execute are realized as methods which take one argument besides ``self``: ``task`` is an instance of ``models.AutomationTaskModel`` and has access to the automations json data field through ``task.data``. This is a convenience solution since it allows lambda expressions, e.g., as parameters for the ``If()`` node:

.. code-block:: python

    branch = (If(lambda x: x.data.get('has_signed_contract', False))
              .Then(this.process_contract)
              .Else(this.send_reminder))



Self-referencing can be achieved using the ``this`` instance of the ``This()`` object or by denoting the reference as string:  ``"self.last_node"`` is equivalent to ``this.last_node``.

.. warning::

    The property names might shadow attributes or methods of the ``flow.Automations`` class. Avoid using existing names like ``id``, ``data``, ``save``, etc. See the list below. Shadowing might lead to unexpected side-effects. Names beginning with underscore ``_`` are reserved and not to used for nodes.

    Here is a list of names to avoid:

    * ``broadcast_message``

    * ``create_on_message``

    * ``data``

    * ``dispatch_message``

    * ``finished``

    * ``get_automation_class_name``

    * ``get_key``

    * ``get_model_instance``

    * ``get_verbose_name``

    * ``get_verbose_name_plural``

    * ``id``

    * ``kill``

    * ``model_class``

    * ``nice``

    * ``on``

    * ``on_signal``

    * ``run``

    * ``satisfies_data_requirements``

    * ``save``

    * ``send_message``

    * ``unique``


Automations are started when instantiated, e.g., by ``instance = IssueDiscussion(issue_list=this_weeks_list)``.

.. note::

    Parameters to the ``__init__`` method are stored in the instance's data json field. The values need to be json-serializable. the only exception are Django model instances. If a model instance is passed the id will be stored in the data field. Also, a property will be created where the respective instance of the model is available.

There are three special parameters when creating an instance:

* ``automation`` denotes the ``models.AutomationModel`` instance to bind this automation to. Hence, not a new automation will be created but an exisiting automation instance will be created from the database data.

* ``automation_id`` is an integer, denoting the id of an ``models.AutomationModel`` instance. The effect is the same as binding directly to the automation.

* ``autorun`` is a boolean value indicating whether the execution shall start immediately when creating the instance. Its default is ``True``. Set it ``False`` if you need to do additional initialization work.

.. py:attribute:: Automation.unique

    The unique attribute is declared when subclassing ``flow.Automation``. It takes either a boolean value or is a list or tuple of strings.

    If ``True`` it makes the automation a singleton, i.e. only one instance can run at a time. If a singleton is instantiated and already an instance is running it will return this running instance.

    If ``.unique`` is a list of strings it declares a set of parameters for the automation which are unique for any instance of it. Parameters of an automation instance are stored in its ``.data`` json field. For example, if you want to avoid sending the same e-mails to an email address multiple times, you can use ``unique = ('email', )`` to only alow one instance of the automation per email.

    ``.unique`` defaults to ``False``.



.. py:attribute:: Automation.id

    Gives the id of the automation instance. It can be used, e.g., to send messages to this instance. Since it is an integer, it can easily serialized and, e.g., passed as a GET parameter.

.. py:attribute:: Automation.data

    Gives the automation instance's ``data`` json field. It is a dictionary of json-serializable data: an instance of Django's ``JSONField``.

.. py:method:: Automation.save()

    Saves the data field back to the database. This method needs to be called after modifying the ``.data`` attribute.

.. py:method:: Automation.run()

    Starts the execution loop of the automation and runs until the automation

    1. Finishes

    2. Reaches a node which requires user interaction (subclass of ``flow.Flow()``)

    3. Reaches a node which requires waiting for a condition or a certain amount of time

    Automations should only contain nodes that do not need more than a few milliseconds to reach one of these conditions. Complex algorithms are supposed to be coded in Python directly. If an automation needs to do complex calculations these calculations should use the ``threaded=True`` option fo the ``Execute()`` node.

    ``run()`` returns the node at which one of the three conditions was reached.

.. py:method:: Automation.nice()

    Starts the execution loop in a new thread using Python's ``threading`` library and returns immediately.

.. py:method:: Automation.is_finished()

    Returns ``True`` if the automation has finished, ``False`` if it is still running. Finished automations remain in the database for analytics.

.. py:method:: Automation.kill()

    Deletes the instance entry in ``models.AutomationModel``.

    This implies that the execution of the automation is stopped and its history and status are removed from the database. Use this method only if an instance has been created in error, e.g., if you detect invalid arguments after creation. Killing an instance is also removing it from all analytics.

.. note::

    To prematurely stop the execution of an automation consider using ``If()`` nodes to branch to an ``End()`` node. This makes the stopping condition explicit in the declaration of an automation.

.. py:method:: Automation.get_key()

    Retrieves a unique key (hash) to be used to identify an automation instance. This has can be used as a ``key`` parameter to send messages if, e.g., a page is viewed. Just add ``?key={{ atm.get_key }}`` to the page's url.


flow.Automation.Meta
====================

Meta data on automations can be stored in a nested ``Meta`` class.

.. code-block:: python

    class MyAutomation(flow.Automation):
        class Meta:
            ...


Currently the following attributes are used.

.. py:attribute:: Automation.Meta.verbose_name
.. py:attribute:: Automation.Meta.verbose_name_plural

    This is a human-readable verbose name of the automation which can be used, e.g., in templates to refer the user to which automation she is for example filling a form.

    If unset it will be ``Automation <<class__name>>``.


.. py:method:: Automation.get_verbose_name()
.. py:method:: Automation.get_verbose_name_plural()

    Returns the verbose name set in the automation's meta class, or, if unset, the standard verbose name ``"Automation <<class_name>>"`` and ``"Automations <<class_name>>"``, respectively.


Messages
========

Automations can receive messages. Messages are used to update an automation instance once it has started, e.g., when a user visits a certain page fo your Django project.

Also, messages can be used create an instance of an automation and start it.


Declaring receivers
-------------------

To receive messages automations have to declare receivers. Receivers are spacial methods of an automation class. Messages are always received by instances (and not the class itself).

Receivers have names that begin with ``receive_`` followed by the message name. They take three parameters: ``self``, ``token``, and ``data``.

They have access to the automation's ``data`` property using ``self.data``. After updating ``self.data`` receivers need to call ``self.save()`` to avoid changes to be lost.

``token`` specifies either an expected action or specifics about the sender of the message. It is either None or of type ``str``.

``data`` is either a dictionary of additional information or - if called by a template tag or a CMS plugin - a request object. Receivers are not to change the dictionary and only to keep copies and not references to avoid side effects.

Example:

.. code-block:: python

    def receive_update_subscriber(self, token, data):
        if token == "subscribe":
            self.data['subscriber_list'].append(data['details'])
            self.save()
        elif token == "unsubscribe":
            ...


This receiver can be sent the message ``"update_subscriber"`` and will require a token to specify the exected action.


Sending messages
----------------

.. py:method:: instance.send_message(message, token, data)

    ``automation.send_message()`` sends the message ``message`` to the automation instance ``autoamtion``. Its class needs to have declared a receiver by providing a method named ``receive_<<message>>`` where ``<<message>>`` is to be replaced by the string ``message``.

    ``token`` is a string parameter which may be used to give the receiver additional information on, e.g., the sender or the specific content of the message. Sender and receiver are free to agree on its meaning. ``data`` typically is a dict of additional data passed to the receiver. The receiving part is supposed not to alter it and to make a copy of it if it is to be stored.

    If the message is sent from a template tag or CMS plugin ``data`` is the request object.


.. py:classmethod:: Automation.dispatch_message(automation, message, token, data)

    If the first parameter ``automation`` is an instance of an automation this is equivalent to ``automation.send_message(..)``. If ``automation`` is of type ``int`` it is interpreted as the id of the automation and the instance is created before it is sent the message. Hence this class method can be used as a shortcut if only an automation's id is known.


.. py:classmethod:: Automation.create_on_message(message, token, data)

    The class method creates an instance of the automation and immediately sends the message. If the automation is a singleton with respect to certain properties these property values must be given in the ``data`` dict or request object.

    The message is sent ``before`` the automation's ``run`` method is called the first time. This means the first Node will not have been executed yet.


.. py:classmethod:: Automation.broadcast_message(message, token, data)

    The class method sends the message to all running instances of the automation. The order is undefined.

    An instance can "catch" a message by returning the string ``"received"``. This will stop the broadcast and not all instances might get the message. All other return values do not influence the broadcast.

    The class method returns a list of all return values. If the broadcast was caught then the last element in this list will be the string ``"received"``.


flow.require_data_parameters
----------------------------

.. py:function:: @flow.require_data_parameters(**kwargs)

    This decorator for receivers (i.e., methods the name of which starts with ``receive_``) declares that the receiver needs certain parameters of certain type, e.g. ``email=str`` denotes that it requires an parameter named ``email`` which has the type ``str`` (string). The parameters must be present in the ``data`` dict or - if ``data`` is the request object - in the requests GET parameters.

    If a sender does not provide the listed parameters the message will not be sent to the receiver in the first place. Using this decorator avoids that a message is sent if, e.g., the required GET parameters are not present.

.. py:classmethod:: Automation.satisfies_data_requirements(message, data)

    This class method checks if ``data`` satisfies the declaration of ``require_data_parameters`` of the message receiver. If the receiver does not have required data parameters defined, it will return ``True``.

Singletons
==========

models.AutomationModel
======================

All automation instances share a Django model class called ``models.AutomationModel``. To distinguish different automations each instance has a field ``automation_class`` which contains the dotted path to the declaration of the automation class.

All interactions with automations go through their classes and instances. With a few exceptions

.. py:classmethod:: models.AutomationModel.run()

    This class method is to be called by the scheduler (e.g., through the management command ``./manage.py automation_step``) regularly. It will check any unfinished automation instances and process them as appropriate.


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
        next = flow.Execute("self.worker_job").Next("self.start")  # alternative notation with string literals

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

.. py:method:: Node.Next(node)

    Sets the node to continue with after finishing this node. If omitted the automation continues with the chronologically next node of the class. ``.Next`` resembles a goto statement. ``.Next`` takes a string or a ``This`` object as a parameter. A string denotes the name of the next node. The this object allows for a different syntax. ``.Next("next_node")`` and ``this.next_node`` are equivalent.

.. py:method:: Node.AsSoonAs(condition)

    Waits for condition before continuing the automation. If condition is ``False`` the automation is interrupted and ``condition`` is checked the next time the automation instance is run.

    If ``condition`` is callable it will be called every time the condition needs to be evaluated.

.. py:method:: Node.AfterWaitingUntil(datetime)

    stops the automation until the specific datetime has passed. Note that depending on how the scheduler runs the automation there might be a significant time slip between ``datetime`` and the real execution time. It is only guaranteed that the node is not executed before. ``datetime`` may be a callable.

.. py:method:: Node.AfterPausingFor(timedelta)

    stops the automation for a specific amount of time. This is roughly equivalent to ``.AfterWaitingUntil(lambda x: now()+timedelta)``. ``timedelta`` may be a callable.

.. py:method:: Node.SkipIf(condition)

    Skips the current node if ``condition`` is truthy (i.e., ``bool(condition)`` evaluates to ``True``) or evaluates to a truthy value. The node is left with ``"skipped"`` in the message field of the ``AutomationTaskModel``.

    The ``SkipIf()`` modifier is useful to skip, e.g., user interactions or sending emails under a certain condition.

.. note::

    ``.SkipIf()`` has precedence over waiting/pausing modifiers. If a node is skipped, e.g., it is not guaranteed that the ``contiditon`` of ``.AsSoonAs()`` is fulfilled. If the condition has to be fulfilled separate the modifiers and add them to different nodes.



Attributes
----------

.. py:attribute:: Node.data

    References a JsonField of the node's automation instance. Each instance of an automation can carry additional data in form of a JsonField. This data is shared by all nodes of the automation instance. The node's attribute returns the common JsonField. Any changes in the field need to be saved using ``.data.save()`` or they might be lost.

    Attached model objects will be referenced by their id in the ``.data`` attribute. Beyond this the automation may use the data field to safe its   state in any way it prefers **as long as the dict is json serializable**. This excludes ``datetime`` objects or ``timedelta`` objects.

Additional methods
------------------

Additional methods differ from modifiers since they do **not** return ``self``.

.. py:method:: Node.ready(automation_instance)

    Is called by the newly initialized Automation instance to bind the nodes to the instance. Typically, there is no need to call it from other apps.

.. py:method:: Node.get_automation_name()

    Returns the (dotted) name of the Automation instance class the node is bound to. Automations are identified by this name.

.. py:method:: Node.resolve(value)

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

.. py:method:: Repeat.EveryDayAt(hour, minute)

    for daily automations which need to run at a certain hour and minute.

.. py:method:: Repeat.EveryHour(no_of_hours=1)

    for hourly automations or automations that need to run every ``no_of_hours`` hour.

.. py:method:: Repeat.EveryNMinutes(minutes)

    for regular automations that need to run every ``minutes`` minutes.




flow.Execute
============

.. py:class:: flow.Execute(func, threaded=False, *args, **kwargs)

    runs a callable, typically a method of the automation. The method gets passed a parameter, called ``task_instance`` which is an instance of the ``AutomationTaskModel``. It gives the method access to the processes json database.

    The ``*args`` and ``**kwargs`` are passed to ``func``. If the function returns a json-serializable result it will be stored in the task instance in the database.

    Subclass ``flow.Execute`` to create your own executable nodes, e.g. ``class SendEMail(flow.Execute)``. Implement a method named ``method``. It gets passed a ``task_instance`` and all parameters of the node.

``flow.Execute`` has one specific modifier.

.. py:method:: Execute.OnError(next_node)

    defines a node to continue with in case the ``Execute`` node fails with an exception. If no ``.OnError`` modifier is given the automation will stop if an error occurs. The error information is kept in the task instance in the database.

flow.If
=======

.. py:class:: flow.If(condition)

    is a conditional node which needs at least the ``.Then()`` modifier and optionally can contain an ``.Else()`` modifier.

.. py:method:: If.Then(parameter)

    contains either a callable that is Executed (see ``flow.Execute``) or a reference to another node where the automation is continued, if the condition is ``True``.

.. py:method:: If.Else(parameter)

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

.. py:method:: Form.User(**kwargs)

    assigns the form to a single user who will have to process it. For the time being the user needs to be unique.

.. py:method:: Form.Group(**kwargs)

    assigns the form to all members of a user group. Selectors typically are only ``id=1`` or ``name="admins"``.

.. py:method:: From.Permission(str)

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

This plugin allows a user to see a detailed status of an automation instance. The automation instance is defined by a get parameter: ``key`` is an unique identifier for an automation instance.

Automations may chose to offer status templates. They have to be declared in the Automations Meta class:

.. code-block:: python

    class MyAutomation(flow.Automation):
        class Meta:
            status_template = "my_automation/status.html", _("Current status")
            issue_template = "my_automation/issues.html", _("Problem sheet")

Any property with a name that ends on ``_template`` in the automation's Meta class is considered to be a template path for some sort of status view. For user friendliness a verbose name can be added. Once declared the plugin will offer all status templates.

The templates receive the  automation instance in the context with the key ``automation`` and the corresponding automation model instance with the key ``automation_model``.


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
        ├── dashboard.html
        ├── form_view.html
        ├── includes
        │   ├── dashboard.html
        │   ├── dashboard_item.html
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

    The ``Form()`` nodes and its subclasses present the forms to the user using a Django ``FormView``. This attribute is an dictionary which will be added to the template's context when rendering. The dictionary items may be overwritten by an automation classes' ``context`` attribute or by a node's ``context`` parameter. Hence, this setting in practice is used to set default context elements.
