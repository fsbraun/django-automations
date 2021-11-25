from logging import getLogger

from django.core.management.base import BaseCommand

from automations.models import AutomationModel

logger = getLogger(__name__)


class Command(BaseCommand):
    help = "Delete Automations older than the specified number of days (default=30)"

    def add_arguments(self, parser):
        parser.add_argument(
            "days_old",
            type=int,
            nargs="?",
            help="The minumum age of an Automation (in days) before it is deleted",
            default=30,
        )

    def handle(self, *args, **kwargs):
        days_old = kwargs["days_old"]
        total, info_dict = AutomationModel.delete_history(days_old)

        automation_count = info_dict.get("automations.AutomationModel", 0)
        task_count = info_dict.get("automations.AutomationTaskModel", 0)

        self.stdout.write(
            f"{total} total objects deleted, including {automation_count} AutomationModel "
            f"instances, and {task_count} AutomationTaskModel instances"
        )
