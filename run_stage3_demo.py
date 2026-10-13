"""Executable demonstrations for the Stage 3 operating workflow."""
from copy import deepcopy
from pathlib import Path
from founderos.config import DATA_DIR
from founderos.analytics import load_data
from founderos.dashboard import reporting_weeks
from founderos.alerts import detect_alerts
from founderos.ai_service import run
from founderos.evidence import dataset_version
from founderos.actions import ActionStore

data=load_data(DATA_DIR); weeks=reporting_weeks(data); week,previous=weeks[-1],weeks[-2]
demo_db=Path("data") / "stage3_demo_actions.db"
if demo_db.exists(): demo_db.unlink()  # This file is owned solely by this repeatable demonstration.
store=ActionStore(demo_db)
alerts=detect_alerts(data,week,previous)

support=next(a for a in alerts if a['alert_id']=='support_backlog')
r1=run(data,week,"Why did our support backlog increase?",support)
a1=store.propose(r1.recommendations[0]['proposed_intervention'],r1.recommendations[0]['business_problem'],r1.recommendations[0]['suggested_owner'],"2026-09-28",4,r1.dataset_version,r1.reporting_week,support['occurrence_id'],r1.evidence_references)
store.transition(a1['action_id'],'approved','Approved in demonstration.')
print("Scenario 1 | support backlog |",support['priority_score'],"|",a1['action_id'],store.get(a1['action_id'])['execution_status'])

delivery=next(a for a in alerts if a['alert_id']=='implementation_capacity')
r2=run(data,week,"Is implementation capacity becoming a constraint?",delivery)
a2=store.propose(r2.recommendations[0]['proposed_intervention'],"Investigate capacity and blockers; correlation is not proof of causation.","CS-01","2026-09-29",4,r2.dataset_version,r2.reporting_week,delivery['occurrence_id'],r2.evidence_references)
print("Scenario 2 | delivery and capacity |",delivery['priority_score'],"|",a2['action_id'],store.get(a2['action_id'])['execution_status'])

changed=deepcopy(data); changed['support_tickets']=changed['support_tickets'].copy(); mask=changed['support_tickets'].status.eq('open'); changed['support_tickets'].loc[mask,'resolved_at']=changed['support_tickets'].loc[mask,'created_at']+__import__('pandas').Timedelta(hours=2); changed['support_tickets'].loc[mask,'status']='resolved'
r3=run(changed,week,"Why did our support backlog increase?")
print("Scenario 3 | changed data version |",dataset_version(data),"->",dataset_version(changed),"|",r3.answer)
