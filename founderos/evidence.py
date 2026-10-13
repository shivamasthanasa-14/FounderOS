"""Bounded retrieval and versioned evidence packages for Chief of Staff analysis."""
from __future__ import annotations
import hashlib, json
import pandas as pd
from .analytics import weekly_snapshot
from .alerts import detect_alerts

METRIC_NOTES={"mrr":"Latest subscription MRR per customer at week-end.","backlog":"Tickets created before week-end and unresolved by then.","milestone_completion_rate":"Milestones due in period completed by the reporting cut-off.","capacity_utilization":"Allocated hours divided by capacity hours in reporting week."}

def dataset_version(data):
    digest=hashlib.sha256()
    for name in sorted(data): digest.update(name.encode()); digest.update(pd.util.hash_pandas_object(data[name],index=True).values.tobytes())
    return digest.hexdigest()[:16]

def _records_for_alert(data, alert, week):
    end=pd.Timestamp(week)+pd.Timedelta(days=7)
    if alert["area"]=="Support":
        t=data["support_tickets"]; return [{"dataset":"support_tickets","record_id":x.ticket_id} for _,x in t[(t.created_at<end)&((t.resolved_at.isna())|(t.resolved_at>=end))].head(12).iterrows()]
    if alert["area"]=="Operations":
        m=data["implementation_milestones"]; return [{"dataset":"implementation_milestones","record_id":x.milestone_id} for _,x in m[(m.due_date<end)&((m.completed_at.isna())|(m.completed_at>=end))].head(12).iterrows()]
    if alert["area"]=="Revenue":
        e=data["subscription_events"]; return [{"dataset":"subscription_events","record_id":x.event_id} for _,x in e[(e.event_date<end)&e.event_type.isin(["churn","contraction"])].tail(12).iterrows()]
    l=data["leads"]; return [{"dataset":"leads","record_id":x.lead_id} for _,x in l[(l.created_at>=week)&(l.created_at<end)].head(12).iterrows()]

def evidence_package(data, week, alert=None):
    from .dashboard import reporting_weeks
    weeks=reporting_weeks(data); i=weeks.index(pd.Timestamp(week)); previous=weeks[max(0,i-1)]
    alerts=detect_alerts(data,week,previous) if i else []
    chosen=alert or None
    return {"dataset_version":dataset_version(data),"reporting_week":str(pd.Timestamp(week).date()),"previous_week":str(pd.Timestamp(previous).date()),"metrics":weekly_snapshot(data,week),"previous_metrics":weekly_snapshot(data,previous),"alerts":alerts if not chosen else [chosen],"record_references":_records_for_alert(data,chosen,week) if chosen else [],"metric_definitions":METRIC_NOTES,"data_completeness":{"opportunity_lifecycle_history": "available" if "opportunity_stage_events" in data else "unavailable","all_required_datasets":True}}

def validate_references(package,data):
    for ref in package.get("record_references",[]):
        table=data.get(ref["dataset"]); id_col=next((c for c in table.columns if c.endswith("_id")),None)
        if table is None or ref["record_id"] not in set(table[id_col]): return False
    return True
