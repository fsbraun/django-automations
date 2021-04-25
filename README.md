# Django-automations

A lightweight framework to collect all processes of your django app in one place.

Use cases:

* Marketing automations, customer journeys
* Simple business processes which require user interactions
* Running regular tasks

## Roadmap

* End of June 2021, core functionality
* August 2021, first release

## Feedback

This project is in a very early stage. All feedback is welcome! Please mail me at fsbraun(at)gmx.de

# Installation

This project will be available on pypi after the first release. In the meantime, please install the master branch from
git using

    pip install https://github.com/fsbraun/django-automations/archive/master.zip

After installation add the `automations` to your installed apps in `settings.py`:

    INSTALLED_APPS = (
        ...,
        'automations',
    )

# Usage

The basic idea is to add an automation layer to Django's model, view, template structure. The automation layer collects
in one place all business processes which in a Django app often are distriuted across models, views and any glue code.

**Automations** consist of **tasks** which are carried out one after another. **Modifiers** affect, e.g. when a task is carried out.

    from automations import flow
    from automations.flow import this

    """this can be used in a class definition as a replacement for "self" """

    class ProcessInput(Automation):
        """The process steps are defiend by sequentially adding the corresponding nodes"""
        start =     flow.Execute(this.get_user_input)
        check =     flow.If(this.does_not_need_approval).Then(this.process)
        approval =      flow.Execute(this.get_approval)
        process =   flow.Execute(this.process_input)
        end =       flow.End()

        critical = 10_000
    
        def get_user_input(task_instance):
            ...

        def does_not_need_approval(task_instance):
            return not (task_instance.data['amount'] > self.critical)

        def get_approval(task_instance):
            ...

        def process_input(task_instance):
            ...

# Documentation

See the [repository's wiki](https://github.com/fsbraun/django-automations/wiki).