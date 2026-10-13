-- founderos_actions.db
CREATE TABLE actions (action_id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE, source_alert TEXT, dataset_version TEXT NOT NULL, reporting_week TEXT NOT NULL, description TEXT NOT NULL, rationale TEXT, owner TEXT, due_date TEXT, priority INTEGER, approval_state TEXT NOT NULL, execution_status TEXT NOT NULL, completion_notes TEXT, evidence_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE action_history (id INTEGER PRIMARY KEY AUTOINCREMENT, action_id TEXT NOT NULL, event TEXT NOT NULL, note TEXT, occurred_at TEXT NOT NULL);
CREATE TABLE ai_runs (run_id TEXT PRIMARY KEY, dataset_version TEXT, reporting_week TEXT, mode TEXT, output_json TEXT, created_at TEXT);
CREATE TABLE workflow_events (event_id TEXT PRIMARY KEY, action_id TEXT, event_type TEXT NOT NULL, idempotency_key TEXT UNIQUE NOT NULL, payload_json TEXT NOT NULL, status TEXT NOT NULL, attempt_count INTEGER NOT NULL DEFAULT 0, last_attempt_at TEXT, result_detail TEXT, created_at TEXT NOT NULL, completed_at TEXT);
CREATE TABLE workflow_executions (execution_id TEXT PRIMARY KEY, event_id TEXT NOT NULL, destination TEXT, status TEXT NOT NULL, attempt_number INTEGER NOT NULL, detail TEXT, occurred_at TEXT NOT NULL);

-- reporting_workspace.db
CREATE TABLE revisions (id INTEGER PRIMARY KEY AUTOINCREMENT, version TEXT, data_json TEXT, report TEXT, filename TEXT, summary_json TEXT, imported_at TEXT);
CREATE TABLE reporting_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision_id INTEGER);

-- weekly_briefs.db
CREATE TABLE weekly_briefs (brief_id TEXT PRIMARY KEY, reporting_week TEXT, financial_month TEXT, document_json TEXT, created_at TEXT, updated_at TEXT);