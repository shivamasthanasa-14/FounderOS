"""Display-only adapters. The analytical engine and stored records are unchanged."""
import pandas as pd
from .alerts import _score
from .dashboard import weekly_trend, format_eur, format_percent

STATUS_LABELS = {'proposed':'Awaiting approval','approved':'Approved','in_progress':'In progress','blocked':'Blocked','complete':'Completed','deferred':'Deferred','rejected':'Rejected','pending':'Automation pending','dispatched':'Automation dispatched','failed':'Automation failed','retry_scheduled':'Automation failed · retry scheduled','not queued':'Not queued'}
LABELS = {'action_id':'Action ID','description':'Action','owner':'Owner','due_date':'Deadline','priority':'Priority','approval_state':'Approval state','execution_status':'Business status','dispatch_status':'Automation status','last_workflow_attempt':'Last dispatch attempt','reporting_week':'Reporting week','occurred_at':'Date and time','event':'Activity','note':'Details','event_id':'Event ID','event_type':'Event type','attempt_count':'Attempts','last_attempt_at':'Last attempt','result_detail':'Result','created_at':'Created','completed_at':'Completed','destination':'Destination','attempt_number':'Attempt','detail':'Details','status':'Status','ticket_id':'Ticket ID','customer_id':'Customer ID','age_days':'Age (days)','sla_hours':'SLA (hours)','resolved_at':'Resolved','project_id':'Project ID','milestone_id':'Milestone ID','due_date':'Deadline','employee_id':'Team member','function':'Function','capacity_hours':'Capacity (hours)','allocated_hours':'Allocated (hours)','utilization':'Utilization','event_date':'Event date','event_type':'Event type','mrr_before':'MRR before (€)','mrr_after':'MRR after (€)','movement':'Movement (€)','opportunity_id':'Opportunity ID','lead_id':'Lead ID','pipeline_value':'Pipeline value (€)','closed_at':'Closed','stage':'Stage','reason':'Reason','category':'Category','milestone':'Milestone','target_go_live':'Target go-live'}
EVIDENCE_LABELS = {'current_backlog':'Open support tickets','previous_backlog':'Prior-week open tickets','sla_adherence':'SLA adherence','overdue_milestones':'Overdue milestones','cs_utilization':'Customer Success utilization','milestone_completion_rate':'Milestones completed on time','gross_revenue_churn':'Gross revenue churn','nrr':'Net revenue retention','net_new_mrr':'Net new MRR','leads':'New leads','previous_leads':'Prior-week leads','qualified_conversion':'Lead qualification rate'}

def readable_table(frame):
    result = frame.copy()
    for col in ['execution_status','approval_state','dispatch_status','event','status']:
        if col in result:
            result[col] = result[col].map(lambda x: STATUS_LABELS.get(x, x))
    return result.rename(columns=lambda x: LABELS.get(x, x.replace('_',' ').title()))

def rate_available(data, week, snapshot, kind):
    week = pd.Timestamp(week); end = week + pd.Timedelta(days=7)
    if kind == 'growth':
        events = data['subscription_events']; prior = events[events.event_date <= week-pd.Timedelta(days=1)].sort_values(['customer_id','event_date','event_id']).groupby('customer_id').tail(1)
        return prior.mrr_after.sum() > 0
    if kind == 'win':
        opp = data['opportunities']; ids = opp[opp.created_at.ge(week)&opp.created_at.lt(end)].opportunity_id
        if 'opportunity_stage_events' in data:
            events = data['opportunity_stage_events']; latest = events[events.event_date.lt(end)].sort_values(['opportunity_id','event_date','stage_event_id']).groupby('opportunity_id').tail(1)
            return bool((latest.opportunity_id.isin(ids)&latest.stage.isin(['won','lost'])).any())
        return bool((opp.opportunity_id.isin(ids)&opp.stage.isin(['won','lost'])).any())
    if kind == 'sla': return snapshot['support']['tickets_resolved'] > 0
    if kind == 'milestone': return snapshot['operations']['milestones_due'] > 0
    cap = data['team_capacity']; cap = cap[cap.week_start.eq(week)]
    if kind == 'cs': cap = cap[cap.function.eq('Customer Success')]
    return cap.capacity_hours.sum() > 0

def display_rate(value, available):
    return format_percent(value) if available and pd.notna(value) else 'N/A'

def comparison(current, previous, unit='', available=True, higher_better=True):
    if not available or pd.isna(current) or pd.isna(previous): return 'No comparable prior week', None
    delta = current-previous
    arrow = '↑' if delta > 0 else '↓' if delta < 0 else '→'
    display_unit = unit[:-1] if abs(delta)==1 and unit in ['customers','tickets'] else unit
    text = f'{abs(delta)*100:.1f} pp' if unit == 'pp' else format_eur(abs(delta)) if unit == 'eur' else f'{abs(delta):,.0f} {display_unit}'.strip()
    favorable = None if delta == 0 or higher_better is None else (delta > 0) == higher_better
    return f'{arrow} {text} vs prior week', favorable

def priority_components(alert):
    keys = ['business_impact','urgency','trend_deterioration','evidence_confidence']
    rows = []
    for index, key in enumerate(keys):
        basis = [0,0,0,0]; basis[index] = 1
        maximum, _ = _score(*basis)
        rows.append({'Component':key.replace('_',' ').title(),'Contribution':round(alert['scoring_factors'][key]*maximum,1),'Maximum':maximum})
    return pd.DataFrame(rows)

def evidence_value(key, value):
    if key == 'net_new_mrr': return format_eur(value)
    if key in ['sla_adherence','cs_utilization','milestone_completion_rate','gross_revenue_churn','nrr','qualified_conversion']: return format_percent(value)
    return f'{value:,.0f}' if isinstance(value,(int,float)) else str(value)

def trend_for_display(data, week):
    frame = weekly_trend(data)
    frame = frame[frame.week.le(pd.Timestamp(week))].copy()
    from .analytics import weekly_snapshot
    for index, row in frame.iterrows():
        snapshot = weekly_snapshot(data,row.week)
        for col, kind in [('SLA adherence','sla'),('Milestone completion','milestone'),('Capacity utilization','capacity'),('CS utilization','cs')]:
            if not rate_available(data,row.week,snapshot,kind): frame.loc[index,col] = float('nan')
    return frame
