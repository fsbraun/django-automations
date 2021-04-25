from logging import getLogger

from django.core.management import BaseCommand

from automations.models import AutomationModel


logger = getLogger(__name__)


class Command(BaseCommand):
    help = 'Touch every automation to proceed.'

    def handle(self, *args, **options):
        AutomationModel.run()