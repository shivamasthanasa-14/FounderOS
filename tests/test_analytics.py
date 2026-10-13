import pandas as pd
import pytest
from founderos.analytics import revenue_kpis, support_kpis, sales_kpis, load_data
from founderos.alerts import detect_alerts
from founderos.config import DATA_DIR

@pytest.fixture(scope="module")
def data(): return load_data(DATA_DIR)

def test_revenue_reconciliation(data):
    week=data["team_capacity"].week_start.max(); prior=week-pd.Timedelta(days=7)
    k=revenue_kpis(data["subscription_events"],week,prior)
    assert k["mrr"] == pytest.approx(k["net_new_mrr"] + sum([]) + revenue_kpis(data["subscription_events"],prior,prior)["mrr"])

def test_zero_denominators():
    empty=pd.DataFrame(columns=["lead_id","created_at","status"])
    opp=pd.DataFrame(columns=["opportunity_id","created_at","stage","pipeline_value"])
    assert sales_kpis(empty,opp,"2026-01-05")["win_rate"] == 0

def test_missing_resolution_is_backlog():
    t=pd.DataFrame({"ticket_id":["1"],"created_at":pd.to_datetime(["2026-01-01"]),"resolved_at":[pd.NaT],"sla_hours":[24]})
    assert support_kpis(t,"2026-01-05",pd.Timestamp("2026-01-12"))["backlog"] == 1

def test_duplicate_ids_detectable(data):
    assert not data["support_tickets"].ticket_id.duplicated().any()
    duplicated=pd.concat([data["support_tickets"].head(1),data["support_tickets"].head(1)])
    assert duplicated.ticket_id.duplicated().any()

def test_ticket_backlog_consistency(data):
    week=data["team_capacity"].week_start.max(); end=week+pd.Timedelta(days=7)
    expected=data["support_tickets"][(data["support_tickets"].created_at<end)&((data["support_tickets"].resolved_at.isna())|(data["support_tickets"].resolved_at>=end))]
    assert support_kpis(data["support_tickets"],week)["backlog"] == len(expected)

def test_unusual_spike_detected(data):
    weeks=sorted(data["team_capacity"].week_start.unique()); current,previous=weeks[-1],weeks[-2]
    alerts=detect_alerts(data,current,previous)
    assert any(x["alert_id"] == "support_backlog" for x in alerts)

def test_contradictory_signals_detected(data):
    weeks=sorted(data["team_capacity"].week_start.unique()); alerts=detect_alerts(data,weeks[-1],weeks[-2])
    assert any(x["alert_id"] == "capacity_delivery_contradiction" for x in alerts)

def test_alert_ranking(data):
    weeks=sorted(data["team_capacity"].week_start.unique()); alerts=detect_alerts(data,weeks[-1],weeks[-2])
    assert [a["priority_score"] for a in alerts] == sorted([a["priority_score"] for a in alerts],reverse=True)
