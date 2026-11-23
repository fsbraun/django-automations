import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from automations.models import AutomationModel, AutomationTaskModel


class Command(BaseCommand):
    help = (
        "Re-link tasks that lost their previous task because they followed a "
        "skipped node (bug in versions up to 0.9.4). Only reports what it would "
        "do unless --apply is given."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the changes to the database (default: dry run)",
        )
        parser.add_argument(
            "--automation-id",
            type=int,
            action="append",
            dest="automation_ids",
            help="Restrict to this automation id (can be given more than once)",
        )
        parser.add_argument(
            "--max-gap",
            type=float,
            default=10.0,
            help="Maximum number of seconds between the skip and the creation of "
            "the orphaned task (default: 10)",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        max_gap = datetime.timedelta(seconds=options["max_gap"])

        # Only automations with more than one root task are of interest
        roots = AutomationTaskModel.objects.filter(previous=None)
        if options["automation_ids"]:
            roots = roots.filter(automation_id__in=options["automation_ids"])
        automation_ids = (
            roots.values("automation_id")
            .annotate(roots=Count("id"))
            .filter(roots__gt=1)
            .order_by("automation_id")
            .values_list("automation_id", flat=True)
        )

        relinked = unresolved = 0
        for automation in AutomationModel.objects.filter(id__in=list(automation_ids)):
            with transaction.atomic():
                for orphan, parent in self.find_parents(automation, max_gap):
                    label = f"Automation {automation.id}: task {orphan.id} ({orphan.status})"
                    if parent is None:
                        unresolved += 1
                        self.stdout.write(
                            f"{label} left alone: no matching skipped task"
                        )
                    else:
                        relinked += 1
                        self.stdout.write(
                            f"{label} -> previous task {parent.id} ({parent.status})"
                        )
                        if apply:
                            orphan.previous = parent
                            orphan.save(update_fields=["previous"])

        self.stdout.write(
            f"{relinked} task(s) {'re-linked' if apply else 'can be re-linked'}, "
            f"{unresolved} left alone."
        )
        if relinked and not apply:
            self.stdout.write("Dry run: nothing changed. Use --apply to write changes.")

    @staticmethod
    def find_parents(automation, max_gap):
        """Yields (orphan, parent) for all root tasks of the automation but its
        earliest one. Parent is None if it cannot be determined safely.

        The bug left a fingerprint: the skipped task was finished with the message
        "skipped", it never got a following task, and the orphan was created
        right after within the same run. Only such a task is accepted as parent.
        This does not depend on which task finished last, and hence also holds
        if other paths of a Split() were finishing tasks in the meantime."""

        tasks = list(automation.automationtaskmodel_set.order_by("created", "id"))
        by_id = {task.id: task for task in tasks}
        has_next = {task.previous_id for task in tasks if task.previous_id}
        orphans = [task for task in tasks if task.previous_id is None][1:]

        def follows(task, ancestor):
            seen = set()
            while task is not None and task.id not in seen:
                if task.id == ancestor.id:
                    return True
                seen.add(task.id)
                task = by_id.get(task.previous_id)
            return False

        for orphan in orphans:
            candidates = [
                task
                for task in tasks
                if task.message == "skipped"
                and task.finished is not None
                and task.id not in has_next
                and datetime.timedelta(0) <= orphan.created - task.finished <= max_gap
                and not follows(task, orphan)  # Never create a loop
            ]
            if not candidates:
                yield orphan, None
                continue
            parent = max(candidates, key=lambda task: (task.finished, task.id))
            has_next.add(parent.id)  # One following task per skipped task
            orphan.previous_id = parent.id  # Keep `follows` correct for the next
            yield orphan, parent
