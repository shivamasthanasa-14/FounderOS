"""Presentation adapters and safe upload validation for the Streamlit dashboard."""
from __future__ import annotations
from copy import deepcopy
import pandas as pd
from .analytics import DATE_COLUMNS, weekly_snapshot
from .alerts import detect_alerts

REQUIRED_COLUMNS = {
 "customers": ["customer_id","company_name","segment","plan","owner","created_at"],
 "subscription_events": ["event_id","customer_id","event_date","event_type","mrr_before","mrr_after","reason"],
 "leads": ["lead_id","created_at","source","status"],
 "opportunities": ["opportunity_id","lead_id","created_at","stage","pipeline_value","closed_at"],
 "opportunity_stage_events": ["stage_event_id","opportunity_id","event_date","stage","pipeline_value"],
 "support_tickets": ["ticket_id","customer_id","created_at","priority","status","resolved_at","sla_hours","category"],
 "implementation_projects": ["project_id","customer_id","start_date","target_go_live","status","owner"],
 "implementation_milestones": ["milestone_id","project_id","milestone","due_date","completed_at","status"],
 "team": ["employee_id","function","role","weekly_capacity_hours"],
 "team_capacity": ["week_start","employee_id","function","allocated_hours","capacity_hours"],
 "financial_entries": ["entry_id","entry_date","entry_type","amount","customer_id","description"],
}
ID_COLUMN = {"customers":"customer_id","subscription_events":"event_id","leads":"lead_id","opportunities":"opportunity_id","opportunity_stage_events":"stage_event_id","support_tickets":"ticket_id","implementation_projects":"project_id","implementation_milestones":"milestone_id","team":"employee_id","financial_entries":"entry_id"}
FK_RULES = {"subscription_events":("customer_id","customers","customer_id"),"opportunities":("lead_id","leads","lead_id"),"opportunity_stage_events":("opportunity_id","opportunities","opportunity_id"),"support_tickets":("customer_id","customers","customer_id"),"implementation_projects":("customer_id","customers","customer_id"),"implementation_milestones":("project_id","implementation_projects","project_id"),"team_capacity":("employee_id","team","employee_id")}

def reporting_weeks(data):
    dates=set(pd.to_datetime(data['team_capacity'].week_start).dropna())
    if not dates: return []
    first=min(dates)
    for name,col in [('customers','created_at'),('leads','created_at'),('opportunities','created_at'),('support_tickets','created_at'),('subscription_events','event_date')]:
        for value in pd.to_datetime(data[name][col]).dropna():
            monday=value.normalize()-pd.Timedelta(days=value.dayofweek)
            if monday>=first: dates.add(monday)
    return sorted(dates)

def active_customers(data, week):
    events=data["subscription_events"]; end=pd.Timestamp(week)+pd.Timedelta(days=7)
    latest=events[events.event_date<end].sort_values(["customer_id","event_date","event_id"]).groupby("customer_id").tail(1)
    return int((latest.mrr_after>0).sum())

def overview(data, week):
    weeks=reporting_weeks(data); i=weeks.index(pd.Timestamp(week)); prior=weeks[max(0,i-1)]
    now=weekly_snapshot(data,week); before=weekly_snapshot(data,prior)
    return {"week":pd.Timestamp(week),"previous_week":pd.Timestamp(prior),"snapshot":now,"previous":before,"active_customers":active_customers(data,week),"previous_customers":active_customers(data,prior),"alerts":detect_alerts(data,week,prior) if i else []}

def weekly_trend(data):
    rows=[]
    for week in reporting_weeks(data):
        s=weekly_snapshot(data,week)
        rows.append({"week":week,"MRR":s["revenue"]["mrr"],"Net new MRR":s["revenue"]["net_new_mrr"],"Leads":s["sales"]["leads"],"Backlog":s["support"]["backlog"],"SLA adherence":s["support"]["sla_adherence"],"Milestone completion":s["operations"]["milestone_completion_rate"],"Capacity utilization":s["operations"]["capacity_utilization"],"CS utilization":s["operations"]["cs_capacity_utilization"]})
    return pd.DataFrame(rows)

def validate_upload(dataset, frame, current_data):
    """Return typed copy and errors; input data is never mutated."""
    if dataset not in REQUIRED_COLUMNS: return None,["Unknown dataset."]
    errors=[]; required=REQUIRED_COLUMNS[dataset]; missing=[c for c in required if c not in frame.columns]
    if missing: return None,[f"Missing required columns: {', '.join(missing)}."]
    candidate=frame[required].copy()
    for col in DATE_COLUMNS.get(dataset,[]):
        candidate[col]=pd.to_datetime(candidate[col],errors="coerce")
        if candidate[col].isna().any() and col not in ["closed_at","resolved_at","completed_at"]: errors.append(f"{col} contains invalid or missing dates.")
    for col in ["mrr_before","mrr_after","pipeline_value","sla_hours","allocated_hours","capacity_hours","weekly_capacity_hours","amount"]:
        if col in candidate:
            candidate[col]=pd.to_numeric(candidate[col],errors="coerce")
            if candidate[col].isna().any(): errors.append(f"{col} must be numeric.")
    id_col=ID_COLUMN.get(dataset)
    if id_col and (candidate[id_col].isna().any() or candidate[id_col].duplicated().any()): errors.append(f"{id_col} must be present and unique.")
    if dataset in FK_RULES:
        col,parent,parent_col=FK_RULES[dataset]; invalid=set(candidate[col].dropna())-set(current_data[parent][parent_col].dropna())
        if invalid: errors.append(f"{col} has {len(invalid)} invalid reference(s) to {parent}.")
    if dataset=="team_capacity":
        if (candidate.allocated_hours<0).any(): errors.append("allocated_hours cannot be negative.")
        if (candidate.capacity_hours<=0).any(): errors.append("capacity_hours must be greater than zero.")
        if candidate.duplicated(["week_start","employee_id"]).any(): errors.append("Only one weekly capacity record per employee is allowed.")
    if dataset=="subscription_events":
        if (candidate[["mrr_before","mrr_after"]]<0).any().any(): errors.append("Subscription MRR cannot be negative.")
        valid={"opening","new","expansion","contraction","churn"}
        if not set(candidate.event_type).issubset(valid): errors.append("Subscription event_type is invalid.")
        for _, group in candidate.sort_values(["customer_id","event_date","event_id"]).groupby("customer_id"):
            if len(group)>1 and not (group.mrr_before.iloc[1:].reset_index(drop=True).round(2)==group.mrr_after.iloc[:-1].reset_index(drop=True).round(2)).all(): errors.append(f"Contradictory MRR history for {group.customer_id.iloc[0]}."); break
            if ((group.event_type.eq("churn")) & (group.mrr_after.ne(0))).any(): errors.append("A churn event must end at zero MRR.")
    if dataset=="support_tickets":
        invalid=candidate.resolved_at.notna() & (candidate.resolved_at<candidate.created_at)
        if invalid.any(): errors.append("resolved_at cannot precede created_at.")
        if (candidate.sla_hours<=0).any(): errors.append("sla_hours must be greater than zero.")
    if dataset=="implementation_milestones":
        invalid=candidate.completed_at.notna() & (candidate.completed_at<candidate.due_date-pd.Timedelta(days=365))
        if invalid.any(): errors.append("completed_at is implausibly earlier than due_date.")
    return (candidate if not errors else None),errors

def replacement_data(data, dataset, frame):
    candidate, errors=validate_upload(dataset,frame,data)
    if errors: return None,errors
    updated=deepcopy(data); updated[dataset]=candidate
    return updated,[]

def format_percent(value): return "—" if value is None or pd.isna(value) else f"{value:.1%}"
def format_eur(value): return "—" if value is None or pd.isna(value) else f"€{value:,.0f}"
