# Bahew Scheduled Task Flow

Bahew stores recurring AI automations in database tables instead of external Manus schedules.

Core flow:

- `ScheduledTask` stores owner, prompt, cron expression, timezone, enabled state, run mode, context thread, model, skills, connectors, and next run time.
- `ScheduledTaskRun` stores every dispatch attempt, status, error, output summary, generated thread, and Celery task id.
- Celery beat runs `dispatch_due_scheduled_tasks`, which scans due enabled tasks and dispatches agent work.
- Chat creation uses `/api/v1/scheduled-tasks/from-chat`, which creates the task and writes a `scheduled_task_card` chat event in the same transaction.
- The workspace renders `scheduled_task_card` as a Manus-style card and opens a right-side details panel for history and controls.

Safety:

- Skip confirmation is stored as task preference and reflected in the trusted scheduled prompt.
- Existing connector approval and platform safety controls remain authoritative.
- User ownership is checked for every task, thread, and run.
