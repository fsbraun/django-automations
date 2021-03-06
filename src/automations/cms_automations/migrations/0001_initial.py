# Generated by Django 3.1.8 on 2021-05-02 11:09

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("cms", "0022_auto_20180620_1551"),
    ]

    operations = [
        migrations.CreateModel(
            name="AutomationHookPlugin",
            fields=[
                (
                    "cmsplugin_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        related_name="cms_automations_automationhookplugin",
                        serialize=False,
                        to="cms.cmsplugin",
                    ),
                ),
                (
                    "automation",
                    models.CharField(max_length=128, verbose_name="Automation"),
                ),
                (
                    "token",
                    models.CharField(
                        blank=True, max_length=128, verbose_name="Optional token"
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=("cms.cmsplugin",),
        ),
        migrations.CreateModel(
            name="AutomationStatusPlugin",
            fields=[
                (
                    "cmsplugin_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        related_name="cms_automations_automationstatusplugin",
                        serialize=False,
                        to="cms.cmsplugin",
                    ),
                ),
                (
                    "template",
                    models.CharField(max_length=128, verbose_name="Task data"),
                ),
                ("name", models.CharField(blank=True, max_length=128)),
            ],
            options={
                "abstract": False,
            },
            bases=("cms.cmsplugin",),
        ),
        migrations.CreateModel(
            name="AutomationTasksPlugin",
            fields=[
                (
                    "cmsplugin_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        related_name="cms_automations_automationtasksplugin",
                        serialize=False,
                        to="cms.cmsplugin",
                    ),
                ),
                (
                    "template",
                    models.CharField(
                        choices=[
                            ("automations/includes/task_list.html", "Default template")
                        ],
                        default="automations/includes/task_list.html",
                        max_length=128,
                        verbose_name="Template",
                    ),
                ),
                (
                    "always_inform",
                    models.BooleanField(
                        default=True,
                        help_text="If deactivated plugin will out output anything if no task is available.",
                        verbose_name="Always inform",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=("cms.cmsplugin",),
        ),
    ]
