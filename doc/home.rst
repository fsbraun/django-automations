Django automations documentation
################################

Business logic
**************

The Django framework rightfully is an extremely popular web development
framework. Django makes it easier to build better Web apps more quickly
and with less code, as they state themselves.

The key elements are **models**, **views** and **templates**. Models represent
the persistent data which is stored in a database backend. Views convert these
data into human readable form: contexts. The context is rendered as html using templates.

This setup leads to business logic being scattered around in a project: Bits
and pieces of the same process appear in different views which in turn access
several models and their logic.

Django-automations aims to add another layer where business logic can be
maintained centrally. Just like models live in ``models.py``, views in ``views.py``
automations are made to live in an app's ``automations.py``.

Automations connect different tasks, may they be automatic or require
user-interaction, to lead to a predefined result. Conditionals allow to
branch according to the specific needs.

The objective is to integrate and automate business processes with less code.
Certain tasks either can be assigned to specific users or user groups or
automatically carried out by your Django app.

Implementation
**************

The implementation is done with a few objectives in mind:

* **Lightweight:** Django-automations builds on proven Django elements: Models to keep the state of the processes and forms to manage user interaction.
* **Python syntax:** Just like models or forms are Python classes, automations are Python classes built in a similar way (from Nodes in stead of ModelFields or FormFields)
* **Easy extensibility:** To keep the core light, it is designed to allow for easy customization in a project.

Benefits
********

* **Transparency:** Business logic in one place
* **Maintainability:** Changes in business logic do not happen in several models or views, just in ``automations.py``.
* **Time savings:** Less code to write
* **Extendability:** Automations can be extended while "running" as long as the names of existing states remain the same.

Enjoy!
******