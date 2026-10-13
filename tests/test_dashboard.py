import pandas as pd
import pytest
from founderos.analytics import load_data
from founderos.config import DATA_DIR
from founderos.dashboard import (overview, reporting_weeks, weekly_trend, validate_upload, replacement_data, format_percent, format_eur)

@pytest.fixture
def data(): return load_data(DATA_DIR)

def test_selected_week_uses_existing_engine(data):
    week=reporting_weeks(data)[-1]; result=overview(data,week)
    assert result['snapshot']['revenue']['mrr'] == 79717.5
    assert result['alerts'] == sorted(result['alerts'],key=lambda x:x['priority_score'],reverse=True)

def test_trend_has_every_reporting_week(data):
    trend=weekly_trend(data)
    assert len(trend)==12 and {'MRR','Backlog','SLA adherence'}.issubset(trend.columns)

def test_valid_upload_recalculates_support(data):
    original=overview(data,reporting_weeks(data)[-1])['snapshot']['support']['backlog']
    changed=data['support_tickets'].copy(); changed.loc[changed.status.eq('open'),'resolved_at']=changed.loc[changed.status.eq('open'),'created_at']+pd.Timedelta(hours=2); changed.loc[changed.status.eq('open'),'status']='resolved'
    updated,errors=replacement_data(data,'support_tickets',changed)
    assert not errors
    assert overview(updated,reporting_weeks(updated)[-1])['snapshot']['support']['backlog'] < original

def test_invalid_schema_is_safe(data):
    candidate,errors=validate_upload('support_tickets',pd.DataFrame({'ticket_id':['x']}),data)
    assert candidate is None and 'Missing required columns' in errors[0]
    assert len(data['support_tickets'])==366

def test_invalid_foreign_key_rejected(data):
    frame=data['support_tickets'].head(1).copy(); frame.loc[:, 'customer_id']='CUS-999'
    _,errors=validate_upload('support_tickets',frame,data)
    assert any('invalid reference' in e for e in errors)

def test_duplicate_identifiers_rejected(data):
    frame=pd.concat([data['leads'].head(1),data['leads'].head(1)])
    _,errors=validate_upload('leads',frame,data)
    assert any('unique' in e for e in errors)

def test_missing_data_formatting():
    assert format_percent(None)=='—' and format_eur(float('nan'))=='—'

def test_materially_different_revenue_scenario(data):
    before=overview(data,reporting_weeks(data)[-1])['snapshot']['revenue']['mrr']
    events=data['subscription_events'].copy(); events.loc[events.event_type.eq('churn'),'event_type']='expansion'; events.loc[events.event_type.eq('expansion'),'mrr_after']=1800
    updated,errors=replacement_data(data,'subscription_events',events)
    assert not errors
    assert overview(updated,reporting_weeks(updated)[-1])['snapshot']['revenue']['mrr'] > before
