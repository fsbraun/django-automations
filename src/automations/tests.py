# coding=utf-8
from io import StringIO
from unittest.mock import patch

from django import forms
from django.test import TestCase
import datetime

from django.utils.timezone import now
from django.utils.translation import gettext as _

from . import flow, models, views
from .flow import this

import django.dispatch

# Create your tests here.

test_signal = django.dispatch.Signal()


class TestAutomation(flow.Automation):
    start =             flow.Execute(this.init).AsSoonAs(lambda x:True).AsSoonAs(this.cont)
    intermediate =      flow.Execute("init2")
    if_clause =         flow.If(lambda x:x.data['more_participants'] == "test").Then("conditional")
    if2 =               flow.If(lambda x:x.data['more_participants'] == "test").Then(this.if_clause).Else(this.end)
    end =               flow.End()

    conditional =       flow.Execute(this.init2).Next("if2")

    def init(self, task_instance):
        if 'participants' not in self.data:
            self.data['participants'] = []
            self.save()
        return task_instance

    def init2(self, task_instance):
        self.data['more_participants'] = "test" + self.data.get("more_participants", "")
        self.save()
        return task_instance

    def cont(self, task):
        return bool(self) and (task)  # True


class Print(flow.Execute):
    @staticmethod
    def method(task_instance, *args):
        print(task_instance.status, *args)


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
    split = flow.Split().Next("t10").Next("t20").Next("t30")
    join = flow.Join()
    l20 = Print("All joined now")
    l30 = flow.End()

    t10 = Print("Thread 10").Next("join")
    t20 = Print("Thread 20").Next("join")
    t30 = Print("Thread 30").Next("join")


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
    form = (flow.ModelForm(AtmTaskForm, key='task_id', context=dict(claim="Save"))
            .Permission("automations.create_automationmodel"))
    end = flow.End()

    def init_with_item(self, task_instance):
        task_instance.data['task_id'] = 8
        self.save()

class Looping(flow.Automation):
    start = flow.Split().Next("loop1").Next("loop2").Next("loop3")

    loop1 = flow.Repeat("loop1").EveryDay().At(21,00)
    loop2 = flow.Repeat("loop2").EveryNMinutes(30)
    loop3 = flow.Repeat("loop3").EveryHour()


class ModelTestCase(TestCase):

    def test_modelsetup(self):
        x = TestAutomation()
        qs = models.AutomationModel.objects.all()
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].automation_class, 'automations.tests.TestAutomation')

        self.assertEqual(models.get_automation_class(x._db.automation_class), TestAutomation)

        x.run()
        self.assertIn("participants", x.data)
        self.assertIn("more_participants", x.data)
        self.assertEqual(x.data["more_participants"], "testtest")

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

    def test_form(self):
        atm = FormTest()
        atm.run()
        users = atm.form.get_users_with_permission()
        self.assertEqual(len(users), 0)


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
        self.assertEqual(0, len(models.AutomationModel.objects.filter(
            automation_class='automations.tests.SignalAutomation',
        )))

        test_signal.send(self.__class__)

        self.assertEqual(1, len(models.AutomationModel.objects.filter(
            automation_class='automations.tests.SignalAutomation',
        )))

    def test_get_automations(self):
        self.assertEqual(len(flow.get_automations()), 0)
        self.assertEqual(len(flow.get_automations("automations.flow")), 1)
        tpl = flow.get_automations("automations.tests")
        self.assertIn('Allow to split and join', (name for _, name in tpl))