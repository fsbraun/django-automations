# coding=utf-8
from io import StringIO
from unittest.mock import patch

from django import forms
from django.contrib.auth.models import User
from django.core.management import execute_from_command_line
from django.test import TestCase
import datetime

from django.utils.timezone import now
from django.utils.translation import gettext as _

from . import flow, models, views
from .flow import this

import django.dispatch
from django.test import RequestFactory


# Create your tests here.

test_signal = django.dispatch.Signal()


class Print(flow.Execute):
    @staticmethod
    def method(task_instance, *args):
        print(task_instance.status, *args)


class TestAutomation(flow.Automation):
    start =             flow.Execute(this.init, threaded=True).AsSoonAs(lambda x:True).AsSoonAs(this.cont)
    intermediate =      flow.Execute("self.init2")
    func_if =           flow.If(lambda x: x.data['more_participants'] == "test").Then().Else(this.print)
    if_clause =         flow.If(lambda x: x.data['more_participants'] == "test").Then("self.conditional")
    if2 =               flow.If(lambda x: x.data['more_participants'] == "test"
                                ).Then(this.if_clause
                                ).Else(this.end)
    end =               flow.End()

    conditional =       flow.Execute(this.init2).Next("self.if2")

    def init(self, task_instance, *args, **kwargs):
        if 'participants' not in self.data:
            self.data['participants'] = []
            self.save()

    def init2(self, task):
        self.data['more_participants'] = "test" + self.data.get("more_participants", "")
        self.save()
        return task  # Illegal since not json serializable

    def cont(self, task):
        return bool(self) and (task)  # True

    def print(self, task):
        print("Hello", task.data)



class TestForm(forms.Form):
    success_url = "https://www.google.de/"
    first_name = forms.CharField(
            label=_('First name'),
            max_length=80,
    )
    email = forms.EmailField(
        label=_('Your e-mail address'),
        max_length=100,
    )
    session = forms.IntegerField(
            label=_('Chose session'),
    )


class TestSplitJoin(flow.Automation):
    class Meta:
        verbose_name = "Allow to split and join"
        verbose_name_plural = "Allow splitS and joinS"

    start = Print("Hello, this is the single thread").AfterPausingFor(datetime.timedelta(days=-1))
    l10 = Print("Line 10").AfterWaitingUntil(now()-datetime.timedelta(minutes=1))
    split = flow.Split().Next("self.t10").Next("self.t20").Next("self.t30")
    join = flow.Join()
    l20 = Print("All joined now")
    l30 = flow.End()

    t10 = Print("Thread 10").Next(this.join)
    t20 = Print("Thread 20").Next(this.join)
    t30 = Print("Thread 30").Next(this.join)


@flow.on_signal(test_signal)
class SignalAutomation(flow.Automation):
    def started_by_signal(self, *args, **kwargs):
        self.data['started'] = 'yeah!'
        self.save()
    start = flow.End()


class AtmTaskForm(forms.ModelForm):
    class Meta:
        model = models.AutomationTaskModel
        exclude = []


class FormTest(flow.Automation):
    class Meta:
        verbose_name = "Edit task #8"
        verbose_name_plural = "Edit tasks"

    start = flow.Execute(this.init_with_item)
    form = (flow.Form(TestForm, context=dict(claim="Save"))
            .User(id=0))
    form2 = (flow.Form(TestForm, context=dict(claim="Save")).User(id=0)
            .Permission("automations.create_automationmodel"))
    end = flow.End()

    def init_with_item(self, task_instance):
        task_instance.data['task_id'] = 8
        self.save()


class Looping(flow.Automation):
    start = flow.Split().Next("self.loop1").Next("self.loop2").Next("self.loop3")

    loop1 = flow.ModelForm(AtmTaskForm, "key_id")
    loop1_1 = flow.Repeat("self.loop1").EveryDay().At(21,00)
    loop2 = flow.Repeat("self.loop2").EveryNMinutes(30)
    loop3 = flow.Repeat("self.loop3").EveryHour()


class BoundToFail(flow.Automation):
    start = Print("Will divide by zero.")
    div = flow.Execute(lambda x: 5/0).OnError(this.error_node)
    never = Print("This should NOT be printed")
    not_caught = flow.Execute(lambda x: 5/0)
    never_reached = Print("Will not reach this")
    end = flow.End()

    error_node = Print("Oh dear").Next(this.not_caught)


class ModelTestCase(TestCase):

    def test_modelsetup(self):
        x = TestAutomation()
        qs = models.AutomationModel.objects.all()
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].automation_class, 'automations.tests.TestAutomation')

        self.assertEqual(models.get_automation_class(x._db.automation_class), TestAutomation)

        x.run()
        self.assertIn("more_participants", x.data)
        self.assertEqual(x.data["more_participants"], "testtest")
        self.assertIn("participants", x.data)

        self.assertEqual(x.get_verbose_name(), "Automation TestAutomation")
        self.assertEqual(x.get_verbose_name_plural(), "Automations TestAutomation")



class AutomationTestCase(TestCase):

    def test_split_join(self):
        with patch('sys.stdout', new=StringIO()) as fake_out:
            atm = TestSplitJoin()
            atm.run()
        output = fake_out.getvalue().splitlines()
        self.assertEqual(output[0], "start Hello, this is the single thread")
        self.assertEqual(output[1], "l10 Line 10")
        self.assertEqual(output[-1], "l20 All joined now")
        self.assertIn("t10 Thread 10", output)
        self.assertIn("t20 Thread 20", output)
        self.assertIn("t30 Thread 30", output)

        self.assertEqual(atm.get_verbose_name(), "Allow to split and join")
        self.assertEqual(atm.get_verbose_name_plural(), "Allow splitS and joinS")


class FormTestCase(TestCase):
    def setUp(self):
        # Every test needs access to the request factory.
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='jacob', email='jacob@…', password='top_secret')

    def test_form(self):
        atm = FormTest()
        atm.form._user=dict(id=self.user.id)  # Fake User
        atm.form2._user=dict(id=self.user.id)  # Fake User
        atm.run()

        users = atm.form.get_users_with_permission()
        self.assertEqual(len(users), 0)

        tasks = atm._db.automationtaskmodel_set.filter(finished=None)
        self.assertEqual(len(tasks), 1)

        # Create an instance of a GET request.
        request = self.factory.get(f"/{tasks[0].id}")

        # Recall that middleware are not supported. You can simulate a
        # logged-in user by setting request.user manually.
        request.user = self.user
        response = views.TaskView.as_view()(request, task_id=tasks[0].id)
        self.assertEqual(response.status_code, 200)

        form_data = dict(session=8, email="none@nowhere.com", first_name="Fred")
        request = self.factory.post(f"/{tasks[0].id}", data=form_data)
        request.user = self.user
        response = views.TaskView.as_view()(request, task_id=tasks[0].id)
        self.assertEqual(response.status_code, 302)  # Success leads to redirect

        request = self.factory.get(f"/tasks")
        request.user = self.user
        response = views.TaskListView.as_view()(request)
        self.assertEqual(response.status_code, 200)


        request = self.factory.get(f"/tasks")
        request.user = self.user
        response = views.TaskListView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        atm.run()
        self.assertEqual(len(atm.form2.get_users_with_permission()), 0)


class SignalTestCase(TestCase):
    def test_signal(self):
        self.assertEqual(0, len(models.AutomationModel.objects.filter(
            automation_class='automations.tests.SignalAutomation',
        )))

        test_signal.send(self.__class__)

        inst = models.AutomationModel.objects.filter(
            automation_class='automations.tests.SignalAutomation',
        )
        self.assertEqual(1, len(inst))
        self.assertEqual(inst[0].data.get("started", ""), "yeah!")

        self.assertGreater(len(inst[0].automationtaskmodel_set.all()), 0)


class RepeatTest(TestCase):
    def test_repeat(self):
        atm = Looping()
        atm.run()
        tasks = atm._db.automationtaskmodel_set.filter(finished=None)
        self.assertEqual(len(tasks), 3)
        atm.run()
        tasks = atm._db.automationtaskmodel_set.filter(finished=None)
        self.assertEqual(len(tasks), 3)



    def test_get_automations(self):
        self.assertEqual(len(flow.get_automations()), 0)
        self.assertEqual(len(flow.get_automations("automations.flow")), 1)
        tpl = flow.get_automations("automations.tests")
        self.assertIn('Allow to split and join', (name for _, name in tpl))


class ManagementCommandTest(TestCase):
    def test_managment_command(self):
        with patch('sys.stdout', new=StringIO()) as fake_out:
            atm = TestSplitJoin()
            execute_from_command_line(["manage.py", "automation_step"])
        output = fake_out.getvalue().splitlines()
        self.assertEqual(output[0], "start Hello, this is the single thread")
        self.assertEqual(output[1], "l10 Line 10")
        self.assertEqual(output[-1], "l20 All joined now")
        self.assertIn("t10 Thread 10", output)
        self.assertIn("t20 Thread 20", output)
        self.assertIn("t30 Thread 30", output)

        db_id = atm._db.id
        self.assertGreater(len(models.AutomationTaskModel.objects.filter(
            automation_id=db_id
        )), 0)
        atm.kill_automation()
        self.assertEqual(len(models.AutomationTaskModel.objects.filter(
            automation_id=db_id
        )), 0)


class ExecutionErrorTest(TestCase):
    def test_managment_command(self):
        with patch('sys.stdout', new=StringIO()) as fake_out:
            atm = BoundToFail()
            atm.run()
        output = fake_out.getvalue().splitlines()
        self.assertEqual(output[0], "start Will divide by zero.")
        self.assertEqual(output[-1], "error_node Oh dear")
        self.assertNotIn("never This should NOT be printed", output)
        self.assertNotIn("never_reached Will not reach this", output)
