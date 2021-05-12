How-to guides
#############

How to modify automations already running
*****************************************

Automations can be updated, improved and changed even when they are running if a few rules are followed.

Each automation instance is represented by a model instance of ``models.AutomationModel``. For each task that is executed an instance of ``models.AutomationTaskModel`` is created. For each unfinished automation there is at least one unfinished task. If the automations contains ``Split()`` nodes there might be more than one unfinished task. Typically these tasks are waiting either for a user interaction, a condition to become true, or until a certain amount of time passes.

This implies that **it is always possible to add nodes** to the automation. New nodes will be executed as soon as an previous task is finished and the automation pointer moves forward to the new node.

Also, **it is possible to change existing nodes**. However, this will only affect automation instances that have not yet processed the node. This leaves a record for the automations where the same node name corresponds to a different task and may render evaluation of automation results difficult.

.. warning::

    Nodes can only be removed from an automation if no instance is pointing to that node. Since this is difficult to guarantee the following process ensures integrity.

Hence, to remove a node from an automation with existing instances follow this process:

1. Change the node you want to remove from an automation to ``flow.Execute()`` without any modifiers. This is a no-operation.

2. Run ``./manage.py automation_step``. This causes all automation instances with an open task at the node you want to delete to process the no-op and move to the next task.

3. Remove the node. Removing is save now since an automation instance coming to the node immediately will execute to no-op and move to the next task.