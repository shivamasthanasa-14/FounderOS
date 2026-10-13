"""Pandas KPI calculations. Calculations are deterministic; no AI is used in Stage 1."""
from __future__ import annotations
import pandas as pd
import numpy as np

DATE_COLUMNS = {
    "subscription_events": ["event_date"], "leads": ["created_at"], "opportunities": ["created_at","closed_at"],
    "opportunity_stage_events": ["event_date"],
    "support_tickets": ["created_at","resolved_at"], "implementation_projects": ["start_date","target_go_live"],
    "implementation_milestones": ["due_date","completed_at"], "team_capacity": ["week_start"], "customers": ["created_at"],
    "financial_entries": ["entry_date"],
}

def load_data(data_dir) -> dict[str,pd.DataFrame]:
    names=["customers","subscription_events","leads","opportunities","opportunity_stage_events","support_tickets","implementation_projects","implementation_milestones","team","team_capacity"]
    data={n:pd.read_csv(f"{data_dir}/{n}.csv") for n in names}
    from pathlib import Path
    from .business import FINANCE_COLUMNS
    finance=Path(data_dir)/'financial_entries.csv'
    data['financial_entries']=pd.read_csv(finance) if finance.exists() else pd.DataFrame(columns=FINANCE_COLUMNS)
    for name, cols in DATE_COLUMNS.items():
        for col in cols: data[name][col]=pd.to_datetime(data[name][col])
    return data

def _safe_div(n, d):
    return 0.0 if d == 0 or pd.isna(d) else float(n/d)

def _mrr_as_of(events, as_of):
    e=events[events.event_date<=as_of].sort_values(["customer_id","event_date","event_id"])
    return e.groupby("customer_id").tail(1).mrr_after.sum()

def revenue_kpis(events:pd.DataFrame, week:pd.Timestamp, previous_week:pd.Timestamp|None=None) -> dict:
    week=pd.Timestamp(week); previous_week=pd.Timestamp(previous_week) if previous_week is not None else week-pd.Timedelta(days=7)
    mrr=_mrr_as_of(events, week+pd.Timedelta(days=7)-pd.Timedelta(nanoseconds=1)); prior=_mrr_as_of(events, week-pd.Timedelta(nanoseconds=1))
    changes=events[(events.event_date>=week)&(events.event_date<week+pd.Timedelta(days=7))].copy(); changes["delta"]=changes.mrr_after-changes.mrr_before
    new=changes.loc[changes.event_type.eq("new"),"delta"].sum(); expansion=changes.loc[changes.event_type.eq("expansion"),"delta"].sum()
    contraction=-changes.loc[changes.event_type.eq("contraction"),"delta"].sum(); churn=-changes.loc[changes.event_type.eq("churn"),"delta"].sum()
    return {"mrr":float(mrr),"net_new_mrr":float(mrr-prior),"mrr_growth":_safe_div(mrr-prior,prior),"new_mrr":float(new),"expansion_mrr":float(expansion),"contraction_mrr":float(contraction),"churn_mrr":float(churn),"gross_revenue_churn":_safe_div(contraction+churn,prior),"net_revenue_retention":_safe_div(prior+expansion-contraction-churn,prior)}

def sales_kpis(leads, opportunities, week, as_of=None, stage_events=None) -> dict:
    week=pd.Timestamp(week); end=week+pd.Timedelta(days=7); as_of=pd.Timestamp(as_of or end)
    # Coercion keeps the public function safe for empty uploads whose CSV schema
    # has not inferred a datetime dtype yet.
    leads=leads.copy(); opportunities=opportunities.copy()
    leads["created_at"]=pd.to_datetime(leads["created_at"], errors="coerce")
    opportunities["created_at"]=pd.to_datetime(opportunities["created_at"], errors="coerce")
    ls=leads[(leads.created_at>=week)&(leads.created_at<end)]; opp=opportunities[(opportunities.created_at>=week)&(opportunities.created_at<end)]
    qualified=int(ls.status.eq("qualified").sum())
    # The stage event log, when present, is the sole source of as-of pipeline state.
    if stage_events is not None:
        se=stage_events.copy(); se["event_date"]=pd.to_datetime(se["event_date"],errors="coerce")
        latest=se[se.event_date<end].sort_values(["opportunity_id","event_date","stage_event_id"]).groupby("opportunity_id").tail(1)
        current_period=latest[latest.opportunity_id.isin(opp.opportunity_id)]
        wins=int(current_period.stage.eq("won").sum()); closed=int(current_period.stage.isin(["won","lost"]).sum())
        open_opp=latest[latest.stage.isin(["discovery","proposal"])].merge(opportunities[["opportunity_id","created_at"]],on="opportunity_id",how="left")
        open_opp["pipeline_value"]=open_opp.pipeline_value.astype(float)
    else:
        # Backward-compatible fallback is explicitly current-state only.
        wins=int(opp.stage.eq("won").sum()); closed=int(opp.stage.isin(["won","lost"]).sum()); open_opp=opportunities[opportunities.stage.isin(["discovery","proposal"])]
    age=(as_of-open_opp.created_at).dt.days
    return {"leads":len(ls),"qualified_leads":qualified,"opportunities":len(opp),"lead_to_qualified_conversion":_safe_div(qualified,len(ls)),"qualified_to_opportunity_conversion":_safe_div(len(opp),qualified),"win_rate":_safe_div(wins,closed),"pipeline_value":float(open_opp.pipeline_value.sum()),"average_open_deal_age_days":float(age.mean()) if len(age) else 0.0,"deals_over_30_days":int((age>30).sum())}

def support_kpis(tickets, week, as_of=None) -> dict:
    week=pd.Timestamp(week); end=week+pd.Timedelta(days=7); as_of=pd.Timestamp(as_of or end)
    created=tickets[(tickets.created_at>=week)&(tickets.created_at<end)]
    resolved=tickets[(tickets.resolved_at>=week)&(tickets.resolved_at<end)]
    backlog=tickets[(tickets.created_at<end)&((tickets.resolved_at.isna())|(tickets.resolved_at>=end))]
    within=resolved[(resolved.resolved_at-resolved.created_at).dt.total_seconds()/3600 <= resolved.sla_hours]
    age=(as_of-backlog.created_at).dt.days
    age_hours=(as_of-backlog.created_at).dt.total_seconds()/3600
    durations=(resolved.resolved_at-resolved.created_at).dt.total_seconds()/3600
    return {"ticket_volume":len(created),"tickets_resolved":len(resolved),"net_backlog_movement":len(created)-len(resolved),"backlog":len(backlog),"open_sla_breaches":int((age_hours>backlog.sla_hours).sum()),"average_resolution_hours":float(durations.mean()) if len(resolved) else 0.0,"resolution_rate":_safe_div(len(resolved),len(created)),"sla_adherence":_safe_div(len(within),len(resolved)),"average_backlog_age_days":float(age.mean()) if len(age) else 0.0,"backlog_over_7_days":int((age>7).sum())}

def operations_kpis(milestones, capacity, week, as_of=None) -> dict:
    week=pd.Timestamp(week); end=week+pd.Timedelta(days=7); as_of=pd.Timestamp(as_of or end)
    due=milestones[(milestones.due_date>=week)&(milestones.due_date<end)]; done=((due.completed_at.notna())&(due.completed_at<end)).sum()
    # Completion after the reporting cut-off remains open at that historical point.
    overdue=milestones[(milestones.due_date<end)&((milestones.completed_at.isna())|(milestones.completed_at>=end))]
    cap=capacity[capacity.week_start.eq(week)]
    on_time=int((due.completed_at.notna() & (due.completed_at<=due.due_date) & (due.completed_at<end)).sum())
    completed=milestones[(milestones.completed_at>=week)&(milestones.completed_at<end)]
    return {"milestones_due":len(due),"completed_milestones":len(completed),"on_time_completion_rate":_safe_div(on_time,len(due)),"delayed_projects":overdue.project_id.nunique() if 'project_id' in overdue else 0,"milestone_completion_rate":_safe_div(done,len(due)),"overdue_milestones":len(overdue),"project_delay_rate":_safe_div(len(overdue),len(milestones)),"capacity_utilization":_safe_div(cap.allocated_hours.sum(),cap.capacity_hours.sum()),"cs_capacity_utilization":_safe_div(cap[cap.function.eq("Customer Success")].allocated_hours.sum(),cap[cap.function.eq("Customer Success")].capacity_hours.sum())}

def weekly_snapshot(data, week) -> dict:
    return {"revenue":revenue_kpis(data["subscription_events"],week),"sales":sales_kpis(data["leads"],data["opportunities"],week,stage_events=data.get("opportunity_stage_events")),"support":support_kpis(data["support_tickets"],week),"operations":operations_kpis(data["implementation_milestones"],data["team_capacity"],week)}
