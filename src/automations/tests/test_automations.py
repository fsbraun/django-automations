# coding=utf-8
import datetime
import inspect
from io import StringIO
from unittest.mock import patch

import django.dispatch
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import execute_from_command_line
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils.timezone import now
from django.utils.translation import gettext as _

from .. import flow, models, views
from ..flow import this
from ..models import AutomationModel, AutomationTaskModel, get_automation_class

# Create your tests here.

User = get_user_model()


class Print(flow.Execute):
    @staticmethod
    def method(task_instance, *args):
        print(task_instance.status, *args)


class TestAutomation(flow.Automation):
    start = flow.Execute(this.init).AsSoonAs(lambda x: True).AsSoonAs(this.cont)
    intermediate = flow.Execute("self.init2")
    func_if = (
        flow.If(lambda x: x.data["more_participants"] == "test").Then().Else(this.print)
    )
    if_clause = flow.If(lambda x: x.data["more_participants"] == "test").Then(
        "self.conditional"
    )
    if2 = (
        flow.If(lambda x: x.data["more_participants"] == "test")
        .Then(this.if_clause)
        .Else(this.end)
    )
    end = flow.End()

    conditional = flow.Execute(this.init2).Next("self.if2")

    def init(self, task, *args, **kwargs):
        if "participants" not in self.data:
            self.data["participants"] = []
            self.save()

    def init2(self, task):
        self.data["more_participants"] = "test" + self.data.get("more_participants", "")
        self.save()
        return task  # Illegal since not json serializable

    def cont(self, task):
        return bool(self) and bool(task)  # True

    def print(self, task):
        print("Hello", task.data)


class TestForm(forms.Form):
    success_url = "https://www.google.de/"
    first_name = forms.CharField(
        label=_("First name"),
        max_length=80,
    )
    email = forms.EmailField(
        label=_("Your e-mail address"),
        max_length=100,
    )
    session = forms.IntegerField(
        label=_("Chose session"),
    )


class TestSplitJoin(flow.Automation):
    class Meta:
        verbose_name = "Allow to split and join"
        verbose_name_plural = "Allow splitS and joinS"

    start = Print("Hello, this is the single thread").AfterWaitingFor(
        datetime.timedelta(days=-1)
    )
    l10 = Print("Line 10").AfterWaitingUntil(now() - datetime.timedelta(minutes=1))
    split = flow.Split().Next("self.t10").Next("self.t20").Next("self.t30")

    join = flow.Join()
    l20 = Print("All joined now")
    l30 = flow.End()

    t10 = Print("Thread 10").Next(this.split_again)
    t20 = Print("Thread 20").Next(this.join)
    t30 = Print("Thread 30").Next(this.join)

    split_again = flow.Split().Next(this.t40).Next(this.t50)
    t40 = Print("Thread 40").Next(this.join_again)
    t50 = Print("Thread 50").Next(this.join_again)
    join_again = flow.Join()
    going_back = Print("Sub split joined").Next(this.join)


class AtmTaskForm(forms.ModelForm):
    class Meta:
        model = AutomationTaskModel
        exclude = []


class FormTest(flow.Automation):
    class Meta:
        verbose_name = "Edit task #8"
        verbose_name_plural = "Edit tasks"

    start = flow.Execute(this.init_with_item)
    form = flow.Form(TestForm, context=dict(claim="Save")).User(id=0)
    form2 = (
        flow.Form(TestForm, context=dict(claim="Save"))
        .User(id=0)
        .Permission("automations.create_automationmodel")
    )
    end = flow.End()

    def init_with_item(self, task_instance):
        task_instance.data["task_id"] = 8
        self.save()


class Looping(flow.Automation):
    start = flow.Split().Next("self.loop1").Next("self.loop2").Next("self.loop3")

    loop1 = flow.ModelForm(AtmTaskForm, "key_id")
    loop1_1 = flow.Repeat("self.loop1").EveryDay().At(21, 00)
    loop2 = flow.Repeat("self.loop2").EveryNMinutes(30)
    loop3 = flow.Repeat("self.loop3").EveryHour()


class BoundToFail(flow.Automation):
    start = Print("Will divide by zero.").SkipAfter(datetime.timedelta(days=1))
    div = flow.Execute(lambda x: 5 / 0).OnError(this.error_node)
    never = Print("This should NOT be printed")
    not_caught = flow.Execute(lambda x: 5 / 0)
    never_reached = Print("Will not reach this")
    end = flow.End()

    error_node = Print("Oh dear").Next(this.not_caught)


class SingletonAutomation(flow.Automation):
    unique = True

    end = flow.End()


class ByEmailSingletonAutomation(flow.Automation):
    unique = ("email",)

    end = flow.End()

    @flow.require_data_parameters(email=str, mails=int)
    def receive_test(self, token, data):
        pass


class ModelTestCase(TestCase):
    def test_modelsetup(self):
        x = TestAutomation(autorun=False)
        qs = AutomationModel.objects.all()
        self.assertEqual(len(qs), 1)
        self.assertEqual(
            qs[0].automation_class, "automations.tests.test_automations.TestAutomation"
        )

        self.assertEqual(get_automation_class(x._db.automation_class), TestAutomation)

        x.run()
        self.assertIn("more_participants", x.data)
        self.assertEqual(x.data["more_participants"], "testtest")
        self.assertIn("participants", x.data)

        self.assertEqual(x.get_verbose_name(), "Automation TestAutomation")
        self.assertEqual(x.get_verbose_name_plural(), "Automations TestAutomation")

    def test_get_group_model(self):
        """With no settings overridden, the default group model "auth.Group" can be retrieved"""
        from ..settings import get_group_model

        self.assertEqual(get_group_model(), Group)


class AutomationTestCase(TestCase):
    def test_split_join(self):
        with patch("sys.stdout", new=StringIO()) as fake_out:
            atm = TestSplitJoin()
        output = fake_out.getvalue().splitlines()
        self.assertEqual(output[0], "start Hello, this is the single thread")
        self.assertEqual(output[1], "l10 Line 10")
        self.assertEqual(output[-1], "l20 All joined now")
        self.assertIn("t10 Thread 10", output)
        self.assertIn("t20 Thread 20", output)
        self.assertIn("t30 Thread 30", output)
        self.assertIn("t40 Thread 40", output)
        self.assertIn("t50 Thread 50", output)
        self.assertIn("going_back Sub split joined", output)

        self.assertEqual(atm.get_verbose_name(), "Allow to split and join")
        self.assertEqual(atm.get_verbose_name_plural(), "Allow splitS and joinS")


class FormTestCase(TestCase):
    def setUp(self):
        # Every test needs access to the request factory.
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="jacob", email="jacob@…", password="top_secret"
        )
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@...",
            password="Even More Secr3t",
            is_superuser=True,
        )

    def test_form(self):
        atm = FormTest(autorun=False)
        tasks = atm._db.automationtaskmodel_set.filter(finished=None)
        self.assertEqual(len(tasks), 0)
        atm.form._user = dict(id=self.user.id)  # Fake User
        atm.form2._user = dict(id=self.user.id)  # Fake User
        atm.run()
        users = atm.form.get_users_with_permission()
        self.assertEqual(len(users), 0)

        tasks = atm._db.automationtaskmodel_set.filter(finished=None)
        self.assertEqual(len(tasks), 1)  # Form not validated

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

        request = self.factory.get("/tasks")
        request.user = self.user
        response = views.TaskListView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        request = self.factory.get("/tasks")
        request.user = self.user
        response = views.TaskListView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        request = self.factory.get("/dashboard")
        request.user = self.admin
        response = views.TaskDashboardView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        atm.run()
        self.assertEqual(len(atm.form2.get_users_with_permission()), 0)


class HistoryTestCase(TestCase):
    def setUp(self):
        # Every test needs access to the request factory.
        self.client = Client()
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@...",
            password="Even More Secr3t",
            is_staff=True,
            is_superuser=True,
        )
        self.admin.save()
        self.assertEqual(self.admin.is_superuser, True)
        login = self.client.login(username="admin", password="Even More Secr3t")
        self.assertTrue(login, "Could not login")

    def test_history_test(self):
        atm = TestSplitJoin()
        response = self.client.get(f"/dashboard/{atm._db.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("split_again = flow.Split()", response.content.decode("utf8"))

    def test_no_traceback_test(self):
        atm = TestSplitJoin()
        response = self.client.get(
            f"/dashboard/{atm._db.id}/traceback/{atm._db.automationtaskmodel_set.first().id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("No traceback available", response.content.decode("utf8"))

    def test_traceback_test(self):
        atm = BogusAutomation1()
        response = self.client.get(
            f"/dashboard/{atm._db.id}/traceback/{atm._db.automationtaskmodel_set.first().id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Darn, this is not good", response.content.decode("utf8"))

    def test_error_view(self):
        BogusAutomation1()
        response = self.client.get("/errors")
        self.assertEqual(response.status_code, 200)
        self.assertIn("BogusAutomation1", response.content.decode("utf8"))


test_signal = django.dispatch.Signal()


@flow.on_signal(test_signal)
class SignalAutomation(flow.Automation):
    def started_by_signal(self, *args, **kwargs):
        self.data["started"] = "yeah!"
        self.save()

    start = flow.Execute().AfterWaitingFor(datetime.timedelta(days=1))
    end = flow.End()

    def receive_new_user(self, token, data=None):
        self.data["token"] = token
        self.save()
        return "received"


class SendMessageAutomation(flow.Automation):
    start = flow.SendMessage(SignalAutomation, "new_user", "12345678")
    to_nowhere = flow.SendMessage(
        "automations.tests.test_automations.FormTest", "this_receiver_does_not_exist"
    )
    end = flow.End()


class SignalTestCase(TestCase):
    def test_signal(self):
        self.assertEqual(
            0,
            len(
                AutomationModel.objects.filter(
                    automation_class="automations.tests.test_automations.SignalAutomation",
                )
            ),
        )

        test_signal.send(self.__class__)

        inst = AutomationModel.objects.filter(
            automation_class="automations.tests.test_automations.SignalAutomation",
        )
        self.assertEqual(1, len(inst))
        self.assertEqual(inst[0].data.get("started", ""), "yeah!")
        SendMessageAutomation()
        inst = AutomationModel.objects.filter(
            automation_class="automations.tests.test_automations.SignalAutomation",
        )
        self.assertEqual(1, len(inst))
        self.assertEqual(inst[0].data.get("token", ""), "12345678")
        self.assertEqual(
            SignalAutomation.dispatch_message(1, "new_user", "", None), "received"
        )
        self.assertEqual(
            SignalAutomation.dispatch_message(2, "new_user", "", None), None
        )
        self.assertEqual(
            SignalAutomation.dispatch_message("non-existing-key", "new_user", "", None),
            None,
        )
        self.assertGreater(len(inst[0].automationtaskmodel_set.all()), 0)


class RepeatTest(TestCase):
    def test_repeat(self):
        atm = Looping()
        tasks = atm._db.automationtaskmodel_set.filter(finished=None)
        self.assertEqual(len(tasks), 3)
        atm.run()
        tasks = atm._db.automationtaskmodel_set.filter(finished=None)
        self.assertEqual(len(tasks), 3)

    def test_get_automations(self):
        self.assertEqual(len(flow.get_automations()), 0)
        self.assertEqual(len(flow.get_automations("automations.flow")), 1)
        tpl = flow.get_automations("automations.tests.test_automations")
        self.assertIn("Allow to split and join", (name for _, name in tpl))


class ManagementCommandStepTest(TestCase):
    def test_managment_step_command(self):
        with patch("sys.stdout", new=StringIO()) as fake_out:
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
        self.assertGreater(
            len(AutomationTaskModel.objects.filter(automation_id=db_id)), 0
        )
        atm.kill()
        self.assertEqual(
            len(AutomationTaskModel.objects.filter(automation_id=db_id)), 0
        )


class ManagementCommandDeleteTest(TestCase):
    def test_managment_delete_command(self):
        with patch("sys.stdout", new=StringIO()) as fake_out:
            atm = TestSplitJoin()
            execute_from_command_line(["manage.py", "automation_delete_history", "0"])
        output = fake_out.getvalue().splitlines()
        self.assertIn(
            "18 total objects deleted, including 1 AutomationModel instances, and 17 "
            "AutomationTaskModel instances",
            output,
        )
        self.assertEqual(AutomationModel.objects.count(), 0)
        self.assertEqual(AutomationTaskModel.objects.count(), 0)
        atm.kill()


class ExecutionErrorTest(TestCase):
    def test_managment_command(self):
        with patch("sys.stdout", new=StringIO()) as fake_out:
            BoundToFail()
        output = fake_out.getvalue().splitlines()
        self.assertEqual(output[0], "start Will divide by zero.")
        self.assertEqual(output[-1], "error_node Oh dear")
        self.assertNotIn("never This should NOT be printed", output)
        self.assertNotIn("never_reached Will not reach this", output)


class SingletonTest(TestCase):
    def test_singleton(self):
        inst1 = SingletonAutomation(autorun=False)
        self.assertEqual(
            len(
                AutomationModel.objects.filter(
                    automation_class="automations.tests.test_automations.SingletonAutomation"
                )
            ),
            1,
        )
        inst2 = SingletonAutomation(autorun=False)
        self.assertEqual(
            len(
                AutomationModel.objects.filter(
                    automation_class="automations.tests.test_automations.SingletonAutomation"
                )
            ),
            1,
        )
        self.assertEqual(inst1._db, inst2._db)
        self.assertNotEqual(inst1, inst2)

    def test_rel_singleton(self):
        inst1 = ByEmailSingletonAutomation(email="none@nowhere.com", autorun=False)
        atm_name = inst1.get_automation_class_name()
        self.assertEqual(atm_name.rsplit(".", 1)[-1], inst1.end.get_automation_name())
        self.assertEqual(
            len(AutomationModel.objects.filter(automation_class=atm_name)), 1
        )
        inst2 = ByEmailSingletonAutomation(email="nowhere@none.com", autorun=False)
        self.assertEqual(
            len(AutomationModel.objects.filter(automation_class=atm_name)), 2
        )
        self.assertNotEqual(inst1._db, inst2._db)
        inst3 = ByEmailSingletonAutomation(email="nowhere@none.com", autorun=False)
        self.assertEqual(
            len(AutomationModel.objects.filter(automation_class=atm_name)), 2
        )
        self.assertEqual(inst2._db, inst3._db)

        self.assertTrue(
            ByEmailSingletonAutomation.satisfies_data_requirements(
                "test", dict(email="test", mails="2")
            )
        )
        self.assertTrue(
            ByEmailSingletonAutomation.satisfies_data_requirements(
                "test", dict(email="test", mails=2)
            )
        )
        self.assertFalse(
            ByEmailSingletonAutomation.satisfies_data_requirements(
                "test", dict(email="test", mails="t2")
            )
        )
        self.assertFalse(
            ByEmailSingletonAutomation.satisfies_data_requirements(
                "test", dict(mails="t2")
            )
        )
        self.assertFalse(
            ByEmailSingletonAutomation.satisfies_data_requirements(
                "nonexistent", dict(mails="t2")
            )
        )

        ByEmailSingletonAutomation.create_on_message(
            "test", None, dict(email="new", mails=2)
        )
        self.assertEqual(
            len(
                AutomationModel.objects.filter(
                    automation_class="automations.tests.test_automations.ByEmailSingletonAutomation"
                )
            ),
            3,
        )

        ByEmailSingletonAutomation.create_on_message(
            "test", None, dict(email="also_new")
        )
        self.assertEqual(
            len(
                AutomationModel.objects.filter(
                    automation_class="automations.tests.test_automations.ByEmailSingletonAutomation"
                )
            ),
            3,
        )

        AutomationModel.run()


class BogusAutomation1(flow.Automation):
    start = flow.Execute(this.test).OnError(this.error)
    end = flow.End()
    error = flow.Execute(this.test)

    def test(self, task):
        raise SyntaxError("Darn, this is not good")

    def time(self, task):
        return True  # not a datetime


class BogusAutomation2(flow.Automation):
    start = flow.Execute(this.test)
    mid = flow.Execute(this.test).AfterWaitingUntil(this.time)
    end = flow.End().AfterWaitingUntil(this.time)

    def test(self, task):
        return "Truth"

    def time(self, task):
        return True  # not a datetime


class ErrorTest(TestCase):
    def test_errors(self):
        atm = BogusAutomation1()
        self.assertTrue(atm.finished())
        self.assertEqual(len(atm._db.automationtaskmodel_set.all()), 2)
        self.assertEqual(
            atm._db.automationtaskmodel_set.all()[1].message,
            "SyntaxError('Darn, this is not good')",
        )
        self.assertIn(
            "error",
            atm._db.automationtaskmodel_set.all()[1].result,
        )
        self.assertIn(
            "html",
            atm._db.automationtaskmodel_set.all()[1].result,
        )
        atm = BogusAutomation2()
        self.assertTrue(atm.finished())
        self.assertEqual(len(atm._db.automationtaskmodel_set.all()), 2)
        self.assertEqual(atm._db.automationtaskmodel_set.all()[0].result, "Truth")
        self.assertEqual(
            atm._db.automationtaskmodel_set.all()[1].message,
            "TypeError(\"'<' not supported between instances of 'bool' and 'datetime.datetime'\")",
        )


class SkipAutomation(flow.Automation):
    start = Print("NOT SKIPPED").SkipIf(lambda x: False)
    second = (
        Print("SKIPPED").SkipIf(True).AsSoonAs(False)
    )  # precedence of SkipIf over AsSoonAs
    third = Print("Clearly printed")
    forth = flow.Execute()  # Noop
    end = flow.End()


class SkipTest(TestCase):
    def test_skipif(self):
        with patch("sys.stdout", new=StringIO()) as fake_out:
            atm = SkipAutomation()
        output = fake_out.getvalue().splitlines()
        self.assertEqual(atm.get_key(), atm.get_key())
        self.assertTrue(atm.finished())
        self.assertEqual(len(output), 2)
        self.assertEqual(output[0], "start NOT SKIPPED")
        self.assertEqual(output[-1], "third Clearly printed")


@override_settings(
    AUTH_USER_MODEL="automations_tests.TestUser",
    ATM_GROUP_MODEL="automations_tests.TestGroup",
    ATM_USER_WITH_PERMISSIONS_FORM_METHOD="automations.tests.methods.temp_get_users_with_permission_form",
    ATM_USER_WITH_PERMISSIONS_MODEL_METHOD="automations.tests.methods.temp_get_users_with_permission_model",
)
class ModelSwapTestCase(TestCase):
    def setUp(self):
        from ..tests.models import TestGroup, TestPermission, TestUser

        # Every test needs access to the request factory.
        self.factory = RequestFactory()

        self.group = TestGroup.objects.create(name="Main Group")
        self.user = TestUser.objects.create(
            username="jacob", email="jacob@...", group=self.group, password="top_secret"
        )
        self.admin = TestUser.objects.create(
            username="admin",
            email="admin@...",
            password="Even More Secr3t",
            is_staff=True,
        )

        self.permission = TestPermission.objects.create(slug="some-critical-permission")
        self.permission.groups.add(self.group)
        self.permissions = [
            self.permission.slug,
        ]

    def test_swappable_models(self):
        """The current group model can be retrieved when overridden"""
        from django.conf import settings

        from ..settings import get_group_model

        # Get models again based on overridden settings
        # noinspection PyPep8Naming
        UserModel = get_user_model()
        # noinspection PyPep8Naming
        GroupModel = get_group_model(settings=settings)

        self.assertEqual(self.permission.groups.count(), 1)
        self.assertEqual(self.group.test_permissions.count(), 1)

        group = GroupModel.objects.first()
        self.assertEqual(group.name, "Main Group")
        self.assertEqual(GroupModel.__name__, "TestGroup")

        user = UserModel.objects.get(username="admin")
        self.assertEqual(user.is_staff, True)
        self.assertEqual(user.email, "admin@...")
        self.assertEqual(UserModel.__name__, "TestUser")

    def test_method_swaps(self):
        from django.conf import settings

        from .. import flow

        # Manually call these here because they are not automatically re-run during tests after we override settings
        flow.swap_users_with_permission_form_method(settings_conf=settings)
        models.swap_users_with_permission_model_method(
            AutomationTaskModel, settings_conf=settings
        )

        atm = FormTest(autorun=False)
        atm.form._user = dict(id=self.user.id)  # Fake User

        form_method = inspect.getsource(atm.form.get_users_with_permission)
        self.assertIn("ABC", form_method)

        model_method = inspect.getsource(AutomationTaskModel.get_users_with_permission)
        self.assertIn("XYZ", model_method)


class AutomationReprTest(TestCase):
    def test_automation_repr(self):
        class TinyAutomation(flow.Automation):
            start = flow.Execute(this.init)
            intermediate = flow.Execute(this.end)
            end = flow.End()

            def init(self, task, *args, **kwargs):
                print("Hello world!")

        automation_dict = str(TinyAutomation.__dict__)

        self.assertIn(
            "'__module__': 'automations.tests.test_automations'", automation_dict
        )
        self.assertIn("'start': <unbound Execute node>", automation_dict)
        self.assertIn("'intermediate': <unbound Execute node>", automation_dict)
        self.assertIn("'end': <unbound End node>", automation_dict)
        self.assertIn(
            "'init': <function AutomationReprTest.test_automation_repr.",
            automation_dict,
        )
