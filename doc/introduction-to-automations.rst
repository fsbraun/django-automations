Getting started
###############

Automations
***********


In Django, a model is the single, definitive source of information about
your data. View encapsulate the logic responsible for processing a user’s
request and for returning the response. Templates are used to create HTML
from views. Forms define how model instances can be edited and created.

Automations describe (business) processes that define what model
manipulations or form interactions have to be executed to reach a
specific goal in your applications. Automations glue together different
parts of your Django project while keeping all required code in one place.
Just like models live in ``models.py``, views in ``views.py``, forms in
``forms.py`` automations live in an apps's ``automations.py``.

The basics:

#. Automations are Python subclasses of ``flow.Automation``
#. Each`attribute represents a task node, quite similar to Django models
#. All instances of automations are executed. Their states are kept in two models used by all Automations, quite in contrast to Django models where there is a one-to-one correspondence between model and table.

Preparing your Django project
*****************************

Before using the Django automations app, you need to install the package
using pip. Then `automations has to be added to your project's
``INSTALLED_APPS`` in ``settings.py``:

.. code-block:: python

    INSTALLED_APPS = (
        ...,
        'automations',
        'automations.cms_automations',   # ONLY IF YOU USE DJANGO-CMS!
   )


.. note::
    Only include the "sub app" ``automations.cms_automations`` if you are using Django CMS. This sub-application will add additional plugins for Django CMS that integrate nicely with Django Automations.



Finally, run

.. code-block:: bash

    python manage.py makemigrations automations
    python manage.py makemigrations cms_automations
    python manage.py migrate automations
    python manage.py migrate cms_automations

to create Django Automations' database tables.

Simple example: WebinarWorkflow
*******************************

This automation executes four consecutive tasks before terminating. These tasks have a timely pattern: The reminder is only sent shortly before the webinar begins. The replay offer is sent after the webinar, 2.5 hours after the reminder.

.. code-block:: python

    import datetime

    from automations import flow
    from automations.flow import this

    from . import webinar

    class WebinarWorkflow(flow.Automation):
        start =             flow.Execute(this.init)
        send_welcome_mail = flow.Execute(webinar.send_welcome_mail)
        send_reminder =     (flow.Execute(webinar.send_reminder_mail)
                                .AfterWaitingUntil(webinar.reminder_time))
        send_replay_offer = (flow.Execute(webinar.send_replay_mail)
                                .AfterPausingFor(datetime.timedelta(minutes=150)))
        end =               flow.End()

        def init(self, task):
            ...

This defines the WebinarWorkflow. Only once a class object is created, the
``WebinarWorkflow`` automation will be executed. Programmatically, you can
create an object by saying ``webinar_workflow = WebinarWorkflow()``.

Nodes
*****

Each task of an automation is expressed by a ``flow.Node``. In the example above
two node classes are used: ``flow.Execute`` and ``flow.End()``. By making a node
an attribute of an ``Automation`` class it gets bound to it. Some nodes
take parameters, like ``flow.Execute``, some do not, like ``flow.End()``.

.. note::
    * Nodes are processed in their order of declaration in the automation class (unless specified differently, see below).
    * Each node has a name (``start``, ``send_welcome_mail``, ...). Each running instance of the automation has a state (or program counter) which corresponds to the name of the node which is to be executed next.
    * Since at the declaration of the ``Automation`` attributes no object has been created there is no ``self`` reference. The ``this`` object replaces ``self`` during the declaration of the automation class. (``this`` objects are replaced by ``self``-references at the time of execution of the automation.)
    * To allow for timed execution, some sort of scheduler is needed in the project.

Node types
==========

Django Automation has some built-in node types (see [reference](reference)).

* ``flow.Execute()`` executes a Python callable, typically a method of the automation class to perform the task.
* ``flow.End()`` terminates the execution of the current automation object.

More nodes are:

* ``flow.Repeat()`` declares an infinite loop to define regular worker processes.
* ``flow.If`` allows conditional branching within the automation.
* ``flow.Split()`` allows to split the execution of the automation in 2 or more concurring paths.
* ``flow.Join()`` waits until all paths that have started at the same previous ``Split()`` have converged again. (All splitted paths must be join before ending an automation!)
* ``flow.Form()`` requires a specific user or a user of a group of users to fill in a form before the automation continues.
* ``flow.ModelForm()`` is a simplified front end of ``flow.Form()`` to create or edit model instances.
* ``flow.SendMessage()`` allows to communicate with other automations.


Modifier
========

Each node can be modified using modifiers. Modifiers are methods of the ``Node``
class which return ``self`` and therefore can be chained together. This well-known
pattern from JavaScript allows a node to be modified multiple times.

Modifiers can add conditions which have to be fulfilled before the execution of
the task begins. Typical conditions include passing of a certain amount of time
or reaching a certain date and time. Other uses include defining the next node
that is to be executed (a little bit like goto).

Modifiers for all nodes (with the exception for ``flow.Form`` and
``flow.ModelForm``) are

* ``.Next(node)`` sets the node to continue with after finishing this node. If omitted the automation continues with the chronologically next node of the class. ``.Next`` resembles a goto statement. ``.Next`` takes a string or a ``This`` object as a parameter. A string denotes the name of the next node. The this object allows for a different syntax. ``.Next("next_node")`` and ``.Next(this.next_node)`` are equivalent.
* ``.AsSoonAs(condition)`` waits for condition before continuing the automation. If condition is ``False`` the automation is interrupted and ``condition`` is checked the next time the automation instance is run.
* ``.AfterWaitingUntil(datetime)`` stops the automation until the specific datetime has passed. Note that depending on how the scheduler runs the automation there might be a significant time slip between ``datetime`` and the real execution time. It is only guaranteed that the node is not executed before. ``datetime`` may be a callable.
* ``.AfterPausingFor(timedelta)`` stops the automation for a specific amount of time. This is equivalent to ``.AfterWaitingUntil(lambda x: now()+timedelta)``.
* ``.SkipIf`` leaves a node unprocessed if a condition is fulfilled.

Other nodes implement additional modifiers, e.g., ``.Then()`` and
``.Else()`` in the ``If()`` node. A different example is
``.OnError(next_node)`` in the ``flow.Execute()`` node which defines where to jump should the execution of the specified method raise an exception.

Node inheritance
================

Especially the ``flow.Execute`` node can be easily subclassed to create specific
and speaking nodes. E.g., in the above example it might be useful to create a
node ``SendMail``:

.. code-block:: python

    class SendMail(flow.Execute):
        def method(self, task, mail_id):
            """here goes the code to be executed"""


Meta options
============

Similar to Django's meta options, Django Automations allows to define verbose names for each automation.


.. code-block:: python

    class WebinarWorkflow(flow.Automation):
        class Meta:
            verbose_name = _("Webinar preparation")

        start =             flow.Execute(this.init)
        ...

Verbose names can appear in Django Automations' views. If no verbose name
is given the standard name "Automation " plus the class name is used. In
this example it is ``Automation WebinarWorkflow``.

