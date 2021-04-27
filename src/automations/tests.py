# coding=utf-8
from django.test import TestCase
import datetime
from . import flow, models
from .flow import this


# Create your tests here.

class TestAutomation(flow.Automation):
    start =             flow.Execute(this.init)
    intermediate =      flow.Execute("init2")
    end =               flow.End()

    def init(self, task_instance):
        if 'participants' not in self.data:
            self.data['participants'] = []
            self.save()
        return task_instance

    def init2(self, task_instance):
        self.data['more_participants'] = "test"
        self.save()
        return task_instance


class ModelTestCase(TestCase):

    def test_modelsetup(self):
        x = TestAutomation()
        qs = models.AutomationModel.objects.all()
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].automation_class, 'automations.tests.TestAutomation')
        x.run()
        self.assertIn("participants", x.data)
        self.assertIn("more_participants", x.data)
        self.assertEqual(x.data["more_participants"], "test")