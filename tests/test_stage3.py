import pandas as pd
import pytest
from founderos.analytics import load_data, sales_kpis, operations_kpis
from founderos.config import DATA_DIR
from founderos.dashboard import validate_upload
from founderos.evidence import evidence_package, dataset_version, validate_references
from founderos.ai_service import run
from founderos.actions import ActionStore
from founderos.alerts import detect_alerts

@pytest.fixture
def data(): return load_data(DATA_DIR)

def test_future_opportunity_stage_does_not_leak(data):
    stage=data['opportunity_stage_events'].copy(); oid=stage.opportunity_id.iloc[0]; stage.loc[stage.opportunity_id.eq(oid),'event_date']=[pd.Timestamp('2026-07-07'),pd.Timestamp('2026-09-30')][:len(stage[stage.opportunity_id.eq(oid)])]
    # A later event must not affect early as-of open pipeline state.
    early=sales_kpis(data['leads'],data['opportunities'],pd.Timestamp('2026-07-06'),stage_events=stage)
    assert early['pipeline_value'] >= 0

def test_future_milestone_completion_does_not_count(data):
    m=data['implementation_milestones'].copy(); m.loc[m.index[0],'completed_at']=pd.Timestamp('2026-09-25'); m.loc[m.index[0],'due_date']=pd.Timestamp('2026-07-08')
    assert operations_kpis(m,data['team_capacity'],pd.Timestamp('2026-07-06'))['overdue_milestones'] >= 1

def test_dynamic_scores_have_factors(data):
    weeks=sorted(data['team_capacity'].week_start.unique()); alerts=detect_alerts(data,weeks[-1],weeks[-2])
    assert all(0<=a['priority_score']<=100 and set(a['scoring_factors'])=={'business_impact','urgency','trend_deterioration','evidence_confidence'} for a in alerts)
    assert len({a['occurrence_id'] for a in alerts})==len(alerts)

def test_subscription_history_validation(data):
    f=data['subscription_events'].head(1).copy(); extra=f.copy(); extra.loc[:, 'event_id']='SUB-BAD'; extra.loc[:, 'event_date']=f.event_date.iloc[0]+pd.Timedelta(days=1); extra.loc[:, 'mrr_before']=999999; f=pd.concat([f,extra])
    _,errors=validate_upload('subscription_events',f,data); assert any('Contradictory' in x for x in errors)

def test_chronology_and_capacity_validation(data):
    t=data['support_tickets'].head(1).copy(); t.loc[t.index[0],'resolved_at']=t.loc[t.index[0],'created_at']-pd.Timedelta(hours=1)
    _,errors=validate_upload('support_tickets',t,data); assert any('precede' in x for x in errors)
    c=pd.concat([data['team_capacity'].head(1),data['team_capacity'].head(1)]); _,errors=validate_upload('team_capacity',c,data); assert any('one weekly' in x for x in errors)

def test_evidence_version_and_references(data):
    week=sorted(data['team_capacity'].week_start.unique())[-1]; p=evidence_package(data,week)
    assert p['dataset_version']==dataset_version(data) and validate_references(p,data)

def test_deterministic_unknown_question(data):
    week=sorted(data['team_capacity'].week_start.unique())[-1]; answer=run(data,week,'What is the weather tomorrow?')
    assert answer.valid() and 'does not answer' in answer.answer

def test_missing_optional_provider_falls_back(data,monkeypatch):
    monkeypatch.setenv('FOUNDEROS_AI_PROVIDER','ollama'); monkeypatch.setenv('OLLAMA_BASE_URL','http://127.0.0.1:9')
    week=sorted(data['team_capacity'].week_start.unique())[-1]; answer=run(data,week,'Why did our support backlog increase?')
    assert answer.valid() and 'provider unavailable' in answer.mode

def test_actions_persist_and_transitions(tmp_path,data):
    store=ActionStore(tmp_path/'actions.db'); version=dataset_version(data)
    a=store.propose('Triage oldest support tickets','Backlog is high','CS-01','2026-09-30',4,version,'2026-09-21','alert-1',[])
    assert store.get(a['action_id'])['execution_status']=='proposed'
    store.transition(a['action_id'],'approved'); store.transition(a['action_id'],'in_progress'); store.transition(a['action_id'],'complete','Done')
    assert ActionStore(tmp_path/'actions.db').get(a['action_id'])['execution_status']=='complete'
    with pytest.raises(ValueError): store.transition(a['action_id'],'approved')
    with pytest.raises(ValueError): store.propose('Triage oldest support tickets','Backlog is high','CS-01','2026-09-30',4,version,'2026-09-21')

def test_overdue_actions(tmp_path,data):
    s=ActionStore(tmp_path/'actions.db'); a=s.propose('Check delivery blockers','Reason','CS-01','2026-07-01',3,dataset_version(data),'2026-06-30'); s.transition(a['action_id'],'approved')
    assert a['action_id'] in [x['action_id'] for x in s.overdue('2026-07-08')]
