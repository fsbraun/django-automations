# Changelog

## Unreleased

### Fixed

- A task following a skipped node (`.SkipIf()` or `.SkipAfter()`) was created
  with `previous=None` instead of pointing to the skipped task. This left the
  automation with more than one root task, which
  - crashed the history view of the dashboard with `MultipleObjectsReturned`,
  - made `Join()` fail with "Join() without Split()" if a node was skipped
    inside a split path,
  - let a second skip in a looping automation re-enter the already finished
    task of the first skip instead of creating a new one. Depending on the
    automation this stalled it silently or ended in an endless loop in
    `Automation.run()`.
- A skipped task released its lock twice, leaving `locked` one too low
  (`-1` for regular nodes, `-2` for forms).
- The history view of the dashboard does not fail anymore for automations with
  several root tasks (data written by earlier versions) or without any task.
  All root tasks are shown, oldest first.

Existing tasks are not changed: tasks orphaned by earlier versions keep
`previous=None`.
