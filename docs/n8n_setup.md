# n8n workflow setup

Import the two JSON files in `n8n/` through **Workflows → Import from File**. Configure `FOUNDEROS_NOTIFICATION_RECEIVER_URL` to a local mock receiver for a no-cost demonstration. The dispatcher accepts an approved-action event containing `action_id`, `owner`, `due_date`, `description`, `rationale`, `priority`, and `idempotency_key`. The review workflow receives `reference_date`, `overdue_by_owner`, and `idempotency_key`.

FounderOS writes a durable event to SQLite when an action is approved; it does not rely on a Streamlit session or a transient request. The Python dispatcher can post that event to the n8n webhook when `FOUNDEROS_N8N_WEBHOOK_URL` is set. n8n retries its outbound HTTP notification three times. FounderOS records the result or failure, and only a successful notification becomes `dispatched`. A notification never changes the action's business completion status.

For local Docker n8n, publish n8n port 5678 and ensure it can reach the notification receiver host/port. On Docker Desktop, use `host.docker.internal` rather than `localhost` for a receiver running on the host. Slack/email are optional future destinations and need credentials configured in n8n; no real recipients are configured by this project.
