"""Comparable weekly facts, with explicit unavailable denominators and cutoffs."""
import pandas as pd
from .analytics import weekly_snapshot
from .dashboard import active_customers, reporting_weeks
from .presentation import rate_available

# label, snapshot area/key, format, movement, period type, explanation
METRICS = {
 'mrr':('Monthly Recurring Revenue','revenue','mrr','eur',True,'ending stock','Latest paid subscription MRR per customer before next Monday. Indicates recurring run rate, not accounting revenue or cash. Higher normally supports growth; excludes one-off revenue.'),
 'net_new_mrr':('Net New MRR','revenue','net_new_mrr','eur',True,'weekly flow','New plus expansion minus contraction and churn MRR in the selected Monday–Sunday week. Higher supports growth; it is not cash or recognized revenue.'),
 'active':('Active Paying Customers',None,None,'count',True,'ending stock','Count of customers whose latest subscription event before next Monday has positive MRR. Higher normally signals growth; free users and future activations are excluded.'),
 'gross_revenue_churn':('Gross Revenue Churn','revenue','gross_revenue_churn','rate',False,'weekly ratio','Contraction plus churn MRR during the week divided by MRR immediately before Monday. Lower indicates better gross retention; new/expansion MRR is excluded. N/A if opening MRR is zero.'),
 'pipeline':('Qualified Sales Pipeline','sales','pipeline_value','eur',None,'ending stock','Unweighted EUR contract value of discovery/proposal opportunities from the latest stage event before next Monday. Opportunities originate from qualified leads. Higher may signal potential demand but is not a forecast, MRR or booked revenue.'),
 'overdue':('Overdue Implementation Milestones','operations','overdue_milestones','count',False,'ending stock','Milestones due before next Monday with no completion before that cutoff. Lower indicates fewer missed commitments; not a unique project count. Milestones lack a separate record-created timestamp.'),
 'new_mrr':('New MRR','revenue','new_mrr','eur',True,'weekly flow','Sum of new-event MRR increases during Monday–Sunday. Higher indicates acquisition; excludes expansion.'),
 'expansion_mrr':('Expansion MRR','revenue','expansion_mrr','eur',True,'weekly flow','Sum of expansion-event MRR increases during Monday–Sunday. Higher indicates account growth; does not imply collected cash.'),
 'contraction_mrr':('Contraction MRR','revenue','contraction_mrr','eur',False,'weekly flow','Positive MRR lost to contractions during Monday–Sunday. Lower indicates less contraction; excludes cancellations.'),
 'churn_mrr':('Churned MRR','revenue','churn_mrr','eur',False,'weekly flow','Positive MRR lost to cancellations during Monday–Sunday. Lower indicates less cancellation; excludes contractions.'),
 'leads':('New Leads','sales','leads','count',None,'weekly flow','Leads created during Monday–Sunday. More volume is context-dependent; does not establish quality.'),
 'qualification':('Lead Qualification Rate','sales','lead_to_qualified_conversion','rate',True,'weekly cohort ratio','Qualified status among leads created in the week divided by all leads created in that week. Higher generally signals quality; status has no dated history, so this is a latest-known cohort proxy, not historical qualification activity.'),
 'conversion':('Qualified-to-Opportunity Conversion','sales','qualified_to_opportunity_conversion','rate',None,'weekly cohort ratio','Opportunities created during the week divided by qualified leads created during the week. Timing mismatch can exceed one hundred percent; not a matched-lead conversion probability.'),
 'win':('Sales Win Rate','sales','win_rate','rate',True,'weekly cohort ratio','Won divided by won plus lost for opportunities created in the week, using stage history before next Monday. Higher generally indicates success; recent cohorts may have no closed deals (N/A).'),
 'deal_age':('Average Open Deal Age','sales','average_open_deal_age_days','days',False,'ending stock average','Mean elapsed days since creation for open discovery/proposal opportunities at cutoff. Lower generally supports faster sales; age alone does not show deal quality. N/A with no open opportunities.'),
 'old_deals':('Open Deals Over 30 Days','sales','deals_over_30_days','count',None,'ending stock','Open opportunities more than thirty elapsed days old at cutoff. Movement needs context; older deals can still be viable.'),
 'tickets':('New Tickets','support','ticket_volume','count',None,'weekly flow','Tickets created Monday–Sunday. More demand requires context; support tickets are not automatically complaints.'),
 'resolved':('Resolved Tickets','support','tickets_resolved','count',True,'weekly flow','Tickets resolved Monday–Sunday, including earlier-created cases. Higher indicates throughput, not guaranteed service quality.'),
 'net_backlog':('Net Backlog Movement','support','net_backlog_movement','count',False,'weekly flow','New tickets minus tickets resolved in Monday–Sunday. Lower reduces pressure; a negative value means backlog shrank.'),
 'backlog':('Open Tickets at Cutoff','support','backlog','count',False,'ending stock','Tickets created before next Monday and not resolved before that cutoff. Lower indicates less unresolved workload; excludes future resolutions.'),
 'breaches':('Open Tickets Breaching SLA','support','open_sla_breaches','count',False,'ending stock','Open tickets whose elapsed age at cutoff exceeds their resolution SLA hours. Lower indicates fewer overdue cases; elapsed calendar hours, not business hours.'),
 'sla':('Resolved-Ticket SLA Compliance','support','sla_adherence','rate',True,'weekly ratio','Tickets resolved within their SLA divided by all tickets resolved during Monday–Sunday. Higher supports service reliability; distinct from open breaches. N/A without resolved tickets.'),
 'resolution_time':('Average Resolution Time','support','average_resolution_hours','hours',False,'weekly resolved-case average','Mean elapsed hours from creation to resolution among tickets resolved Monday–Sunday. Lower generally indicates faster service; affected by case mix and excludes open tickets. N/A without resolutions.'),
 'due':('Milestones Due','operations','milestones_due','count',None,'weekly flow','Milestone deadlines in Monday–Sunday. More commitments needs context; deadlines use the supplied timestamp.'),
 'completed':('Completed Milestones','operations','completed_milestones','count',True,'weekly flow','Milestones completed Monday–Sunday regardless of their due week. Higher indicates throughput; does not establish on-time delivery.'),
 'on_time':('On-time Milestone Completion','operations','on_time_completion_rate','rate',True,'weekly due-cohort ratio','Milestones due in the week completed by their deadline and before cutoff divided by milestones due in the week. Higher supports reliability; N/A with no due milestones.'),
 'delayed':('Projects with Overdue Milestones','operations','delayed_projects','count',False,'ending stock','Distinct project IDs with overdue incomplete milestones at cutoff. Lower indicates fewer affected projects; not necessarily missed go-live dates.'),
 'capacity':('Capacity Utilization','operations','capacity_utilization','rate',None,'weekly ratio','Allocated divided by available hours for reporting-week team records. Context-dependent; high utilization does not establish a cause of delay. N/A with no capacity.'),
}
MODES=['Previous reporting week','Four weeks earlier','Previous four-week average','Selected historical week']

def metric_values(data,week):
    s=weekly_snapshot(data,week); values={k:(active_customers(data,week) if area is None else s[area][field]) for k,(_,area,field,*_) in METRICS.items()}
    availability={'gross_revenue_churn':rate_available(data,week,s,'growth'),'win':rate_available(data,week,s,'win'),'sla':rate_available(data,week,s,'sla'),'on_time':rate_available(data,week,s,'milestone'),'capacity':rate_available(data,week,s,'capacity'),'qualification':s['sales']['leads']>0,'conversion':s['sales']['qualified_leads']>0,'deal_age':bool(open_pipeline(data,week).shape[0]),'resolution_time':s['support']['tickets_resolved']>0}
    for k,available in availability.items():
        if not available: values[k]=None
    return values

def comparison_weeks(data,week,mode,selected=None):
    week=pd.Timestamp(week); prior=[pd.Timestamp(w) for w in reporting_weeks(data) if w<week]
    if mode==MODES[0]: return prior[-1:] if prior and prior[-1]==week-pd.Timedelta(days=7) else []
    if mode==MODES[1]: return [week-pd.Timedelta(days=28)] if week-pd.Timedelta(days=28) in prior else []
    if mode==MODES[2]:
        wanted=[week-pd.Timedelta(days=7*i) for i in range(1,5)]
        return sorted(wanted) if all(w in prior for w in wanted) else []
    return [pd.Timestamp(selected)] if selected is not None and pd.Timestamp(selected) in prior else []

def compare_metrics(data,week,mode=MODES[0],selected=None):
    current=metric_values(data,week); dates=comparison_weeks(data,week,mode,selected); historical=[metric_values(data,w) for w in dates]; rows=[]
    for key,(label,area,field,unit,higher,kind,definition) in METRICS.items():
        values=[h[key] for h in historical]; before=sum(values)/len(values) if values and all(v is not None for v in values) else None
        value=current[key]; delta=value-before if value is not None and before is not None else None
        relative=delta/abs(before) if delta is not None and before!=0 and unit!='rate' else None
        movement='Unavailable' if delta is None else 'Unchanged' if delta==0 else 'Context-dependent' if higher is None else 'Favorable' if (delta>0)==higher else 'Unfavorable'
        rows.append({'key':key,'Metric':label,'Current':value,'Comparison':before,'Change':delta,'Relative change':relative,'Movement':movement,'unit':unit,'Period type':kind})
    return rows,dates

def open_pipeline(data,week):
    end=pd.Timestamp(week)+pd.Timedelta(days=7); events=data['opportunity_stage_events']; latest=events[events.event_date.lt(end)].sort_values(['opportunity_id','event_date','stage_event_id']).groupby('opportunity_id').tail(1)
    return latest[latest.stage.isin(['discovery','proposal'])].merge(data['opportunities'][['opportunity_id','lead_id','created_at']],on='opportunity_id').assign(age_days=lambda x:(end-x.created_at).dt.total_seconds()/86400)

def support_records(data,week):
    end=pd.Timestamp(week)+pd.Timedelta(days=7); t=data['support_tickets']; open_=t[t.created_at.lt(end)&(t.resolved_at.isna()|t.resolved_at.ge(end))].copy()
    open_['age_hours']=(end-open_.created_at).dt.total_seconds()/3600
    open_['sla_deadline']=open_.created_at+pd.to_timedelta(open_.sla_hours,unit='h')
    open_['sla_overdue']=open_.sla_deadline.lt(end)
    open_['hours_past_deadline']=((end-open_.sla_deadline).dt.total_seconds()/3600).clip(lower=0)
    # Suppress future state and resolutions from historical record displays.
    open_['status']='open'; open_['resolved_at']=pd.NaT
    return open_.merge(data['customers'][['customer_id','segment']],on='customer_id',how='left')

def delivery_records(data,week):
    end=pd.Timestamp(week)+pd.Timedelta(days=7); p=data['implementation_projects']; p=p[p.start_date.lt(end)].copy(); m=data['implementation_milestones']; m=m[m.project_id.isin(p.project_id)].copy()
    m.loc[m.completed_at.ge(end),'completed_at']=pd.NaT; m['status']=m.completed_at.notna().map({True:'complete',False:'open'}); m['overdue']=m.due_date.lt(end)&m.completed_at.isna()
    p=p.drop(columns='status').merge(m.groupby('project_id').agg(milestones=('milestone_id','count'),completed=('completed_at','count'),overdue=('overdue','sum')).reset_index(),on='project_id',how='left')
    p['delivery_state']=p.overdue.gt(0).map({True:'Overdue commitments',False:'No overdue commitments'})
    return p,m
