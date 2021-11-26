Core concepts
#############

Automations are processes
*************************
Automations are nothing but well-defined processes designed to reach a goal. While often it is not technically difficult to implement processes with Django projects, maintenance can become quite complex over time if

* different tasks of the process are hidden at different places in the code base.
* documentation of the automations is not complete or out of sync
* multiple users or user groups are involved in one process and need to share information.

Commonly, business processes are described using events, tasks, and gateways.

Events
======
Events can start an automation or can change its course once it is running. Django automations can be started by Django signals (see `Django documentation <https://docs.djangoproject.com/en/3.1/topics/signals/>`_), programmatically by instantiating an automation, or by sending it a message.

Tasks
=====

Tasks describe work that has to be done, either by the Django application or by an user: Send an email or update a model instance are respective examples.

Tasks are the single units of work that is not or cannot be broken down to a further level. It is referred to as an atomic activity. A task is the lowest level activity illustrated on a process diagram. A set of tasks may represent a high-level procedure. Tasks are are atomic transactions from a Django viewpoint.

Work to be done by a user are represented by Django forms where the user has to fill in the results of her work, e.g., do an approval, fill in billing details etc.



Gateways
========

Gateways change the flow of an automation, e.g., depending on a condition. Django automations offers ``If()``, ``.Then()``, ``.Else()`` constructs. The ``Split()``/``Join()`` gateway allows to parallelize the automation.

Example issue discussion cycle
******************************

Assume you have a Django app that collects issues on a list and each week it creates an
issue list for discussion.

.. image:: https://upload.wikimedia.org/wikipedia/commons/c/c0/BPMN-DiscussionCycle.jpg
    :alt: Business process Issue discussion cycle

Django Automations allows to describe and document the process in one place, a python class (what else?).

This process can be translated into an automation like this

.. code-block:: python

    class IssueDiscussion(flow.Automation):
        issue_list = models.IssueList

        start =         flow.Execute(this.publish_announcement)
        parallel =      flow.Split().Next(this.moderation).Next(this.warning).Next(this.conf_call)

        moderation =    flow.If(this.no_new_mails).Then(this.repeat)
        moderate =      flow.Form(forms.MailModeration).Group(name='Moderators')
        repeat =        (flow.If(this.moderation_deadline_reached)
                            .Then(this.join)
                            .Else(this.moderation)
                        ).AfterWaitingFor(datetime.timedelta(hours=1))

        warning =       (flow.Execute(this.send_deadline_warning)
                            .AfterWaitingFor(datetime.timedelta(days=6))
                            .Next(this.join))

        conf_call =     flow.If(this.conf_call_this_week).Then(this.moderate_call).Else(this.join)
        moderate_call = flow.Execute(this.block_calendar)

        join          = flow.Join()
        evaluate      = flow.Execute(this.evaluate)
        end           = flow.End()


Automation states
*****************

Automations have a state, i.e. they execute at one or more tasks. All execution points share the same attached model instances and (simple) state data. As many instances of an automation may be executed concurrently as necessary each instance has its own state.

Let's say you wanted to automate the signup process for a webinar. Then a single session of a webinar with date and time might be the model instance you wanted to attach to the automation. This means each session of the webinar  would also have an independent automation instance managing the signup process including sending out the webinar link, reminding people when the webinar starts or offering a recording after the webinar. While during the process the session does not change the list of people who have signed up changes but still always refers to the same
webinar session.

Django automations has two optional ways of storing state data. The first one is **binding model instances to an automation instance** allowing for all form of data Django models can handle. Additionally each automation instance has **a json-serializable dictionary attached** called ``data``. Since it is stored in a Django ``JSONField`` it only may contain combination of basic types (like ``int``, ``real``, ``list``, ``dict``, ``None``). This data dictionary is also used to store results of form interactions or for automation methods to keep intermediate states to communicate with each other.

Modifiers
*********

When interacting with humans, an automation will have to wait for input but also give humans time to digest and react. Modifiers control the speed at which an automation is executed: How long to wait before sending a reminder, or how long to give time before escalating the need for important information to the user's superior. The timing of each step is controlled by "modifiers" which, e.g., pause an automation before continuing.

Request-response cycle and scheduling
*************************************

Practically all automations pause or wait for other processes to finish most of the time.

From time to time, the automations have to be checked if they can advance. This is the task of a scheduler outside this package. The scheduler may, e.g., call the class method ``models.AutomationModel.run``. Additionally, Django Automations offers a :ref:`new management command<Management command>` ``python manage.py automation_step`` that can be invoked by an external scheduler.

Also, an automation may advance, e.g., after an processing form has been filled and validated. Then the automation may advance within the request-response cycle of the POST request of the form. To keep the web app responsive, all automation steps need to be fast. Optionally, Django Automations allows to spawn threads for the background processes, or if serious calculations have to be done, outsourced to a worker task.

.. note::

    Django Automations is not a task scheduler for background worker processes. It is a framework that defines what tasks have to be done at what time under what conditions. It works, however, well with background worker processes.

Currently, there is no native integration with, say, Celery. However, this might be an extension which would be welcomed.