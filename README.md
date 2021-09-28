![PyPI - Python Version](https://img.shields.io/pypi/pyversions/django-automations)
![PyPI - Django Version](https://img.shields.io/pypi/djversions/django-automations)
![GitHub](https://img.shields.io/github/license/fsbraun/django-automations)

[![PyPI](https://img.shields.io/pypi/v/django-automations)](https://pypi.org/project/django-automations/)
[![Read the Docs](https://img.shields.io/readthedocs/django-automations)](https://django-automations.readthedocs.io/en/latest/)
[![codecov](https://codecov.io/gh/fsbraun/django-automations/branch/master/graph/badge.svg?token=DSA28NEFL9)](https://codecov.io/gh/fsbraun/django-automations)

# Django-automations

A lightweight framework to collect all processes of your django app in one place.

Use cases:

* Marketing automations, customer journeys
* Simple business processes which require user interactions
* Running regular tasks

Django-automations works with plain Django but also integrates with Django-CMS.

## Key features

* Describe automations as python classes

* Bind automations to models from other Django apps
  
* Use Django forms for user interaction

* Create transparency through extendable dashboard

* Declare automations as unique or unique for a certain data set
  
* Start automations on signals or when, e.g., user visits a page

* Send messages between automations

## Requirements

* **Python**: 3.7, 3.8, 3.9
* **Django**: 3.0, 3.1, 3.2

## Feedback

This project is in a early stage. All feedback is welcome! Please mail me at fsbraun(at)gmx.de

# Installation

This project will be available on pypi after the first release. In the meantime, please install the master branch from
git using

    pip install https://github.com/fsbraun/django-automations/archive/master.zip

After installation add the `automations` to your installed apps in `settings.py`:

    INSTALLED_APPS = (
        ...,
        'automations',
        'automations.cms_automations',   # ONLY IF YOU USE DJANGO-CMS!
    )

Only include the "sub app" `automations.cms_automations` if you are using Django CMS. 

The last step is to create and run the necessary migrations using the `manage.py` command:

    pathon manage.py makemigrations automations
    python manage.py migrate automations


# Usage

The basic idea is to add an automation layer to Django's model, view, template structure. The automation layer collects
in one place all business processes which in a Django app often are distributed across models, views and any glue code.

**Automations** consist of **tasks** which are carried out one after another. **Modifiers** affect, e.g. when a task is
carried out.

    from automations import flow
    from automations.flow import this  
    # "this" can be used in a class definition as a replacement for "self"

    from . import forms

    class ProcessInput(Automation):
        """The process steps are defiend by sequentially adding the corresponding nodes"""
        start =     flow.Execute(this.get_user_input)                  # Collect input a user has supplied
        check =     flow.If(
                        this.does_not_need_approval                    # Need approval?
                    ).Then(this.process)                               # No? Continue later
        approval =      flow.Form(forms.ApprovalForm).Group(name="admins")  # Let admins approve
        process =   flow.Execute(this.process_input)                   # Generate output
        end =       flow.End()

        critical = 10_000
    
        def get_user_input(task_instance):
            ...

        def does_not_need_approval(task_instance):
            return not (task_instance.data['amount'] > self.critical)

        def process_input(task_instance):
            ...

# Documentation

See the [documentation on readthedocs.io](https://django-automations.readthedocs.io/).