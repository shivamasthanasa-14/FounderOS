"""Executable end-to-end automation demo using the FounderOS production modules."""
from pathlib import Path
from founderos.config import DATA_DIR
from founderos.analytics import load_data
from founderos.dashboard import reporting_weeks
from founderos.alerts import detect_alerts
from founderos.ai_service import run
from founderos.actions import ActionStore
from founderos.workflows import MockNotificationReceiver, dispatch_event

db=Path("data/stage4_demo.db")
if db.exists(): db.unlink()
data=load_data(DATA_DIR); weeks=reporting_weeks(data); week=weeks[-1]; alert=next(a for a in detect_alerts(data,week,weeks[-2]) if a['alert_id']=="support_backlog")
analysis=run(data,week,"Why did our support backlog increase?",alert); recommendation=analysis.recommendations[0]
store=ActionStore(db)
action=store.propose(recommendation['proposed_intervention'],recommendation['business_problem'],"CS-01","2026-09-28",4,analysis.dataset_version,analysis.reporting_week,alert['occurrence_id'],analysis.evidence_references)
approved=store.transition(action['action_id'],"approved","Founder approval recorded in demo.")
event=store.event_for_action(approved['action_id'])[0]; receiver=MockNotificationReceiver(); result=dispatch_event(store,event,receiver)
store.transition(approved['action_id'],"in_progress","Customer Success Lead began triage.")
print("Support alert:",alert['occurrence_id'])
print("Action:",approved['action_id'],"owner:",approved['owner'],"status:",store.get(approved['action_id'])['execution_status'])
print("Dispatch:",result['status'],"notifications received:",len(receiver.received))
print("Workflow summary:",store.workflow_summary("2026-09-21"))
