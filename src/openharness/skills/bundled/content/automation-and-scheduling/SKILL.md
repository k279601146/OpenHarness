---
name: automation-and-scheduling
description: Use when the user asks for scheduled, recurring, automated, background, reminder, monitoring, or time-triggered work in OpenHarness SaaS. Prefer creating a SaaS ScheduledTask for low-frequency AI work, and use durable backend jobs for high-frequency deterministic polling.
category: productivity
aliases:
  - scheduling
  - automation
  - recurring tasks
---

# Automation and Scheduling

Use this skill before creating automations, recurring tasks, reminders, monitors, or background workflows.

## OpenHarness SaaS Route

For low-frequency tasks that need AI judgment, writing, research, connector-aware work, or workspace context, create an OpenHarness SaaS `ScheduledTask`.

- Bind the task to the current `AgentThread` when the user is working inside a conversation.
- Preserve model, selected skills, selected connectors, media model preferences, and context thread.
- Use `continue_thread` when historical context matters; use `new_thread` when each run should be isolated.
- Store history in `ScheduledTaskRun` so the user can inspect success, failure, output summary, and the generated workspace.
- If the user enables skip confirmation, state that routine scheduled steps can proceed without repeated confirmation, while connector and platform safety boundaries still apply.

## When Not To Use ScheduledTask

Do not use a full AI scheduled run for minute-level or high-frequency deterministic polling. For rule-based checks, webhooks, and frequent monitors, implement a durable backend workflow with the existing project stack:

- FastAPI endpoint for events or webhooks.
- Celery beat/worker for periodic jobs.
- Database state for cursors, processed IDs, retries, and audit history.
- Optional UI for managing parameters and viewing runs.

Use a scheduled AI task only when the run genuinely needs agent reasoning or connector-aware execution.

## Chat Creation Behavior

When the user asks in chat to create a scheduled task, the expected OpenHarness SaaS behavior is:

1. Parse the requested cadence and action.
2. Create `ScheduledTask` through the SaaS API.
3. Write a `scheduled_task_card` event back into the current chat.
4. Show the card with title, prompt summary, repeat schedule, next run, status, skip confirmation, and actions.
5. Let the user run now, pause/resume, edit, open all scheduled tasks, or delete from the card.

See `references/openharness-scheduled-task-flow.md` for implementation details.
