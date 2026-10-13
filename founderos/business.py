"""Plain-language business facts, reconciled demonstration finances and issue views."""
from __future__ import annotations
import calendar
import pandas as pd
from .dashboard import reporting_weeks
from .analytics import weekly_snapshot
from .periods import support_records, delivery_records

FINANCE_COLUMNS=['entry_id','entry_date','entry_type','amount','customer_id','description']
FINANCE_TYPES=['recognized_revenue','direct_cost','cash_receipt','cash_payment','opening_cash','closing_cash']

def subscription_revenue(events,month):
    """Accrue EUR by exact effective-time segments, using price/month days.

    Opening events are carried balances: their mrr_before applies from the start
    of their opening month until the first observed event. No earlier month is inferred.
    This is the demonstration's declared monthly subscription accounting policy.
    """
    month=pd.Timestamp(month).to_period('M').start_time; end=month+pd.offsets.MonthBegin(1)
    result={}; denominator=(end-month).total_seconds(); histories={}
    for event in events.sort_values(['customer_id','event_date','event_id']).itertuples(index=False): histories.setdefault(event.customer_id,[]).append(event)
    for customer,history in histories.items():
        earlier=[event for event in history if event.event_date<month]; first=history[0]
        balance=float(earlier[-1].mrr_after) if earlier else float(first.mrr_before) if first.event_type=='opening' and first.event_date.to_period('M')==month.to_period('M') else 0.0
        cursor=month; amount=0.0
        for event in history:
            if event.event_date<month or event.event_date>=end: continue
            amount += balance*(event.event_date-cursor).total_seconds()/denominator
            cursor=event.event_date; balance=float(event.mrr_after)
        amount += balance*(end-cursor).total_seconds()/denominator
        if amount>0: result[customer]=round(amount,2)
    return result

def demo_finance(data):
    """Generate transparent synthetic journals; never overwrites operational sources."""
    weeks=reporting_weeks(data); first=pd.Timestamp(weeks[0]).to_period('M').start_time; last=pd.Timestamp(weeks[-1]).to_period('M').start_time
    rows=[['FIN-OPEN',first-pd.Timedelta(days=1),'opening_cash',150000,None,'Opening bank balance for the demonstration reporting window']]
    previous={}; bank=150000
    for month in pd.date_range(first,last,freq='MS'):
        date=month+pd.offsets.MonthEnd(0); tag=month.strftime('%Y%m'); recognized=subscription_revenue(data['subscription_events'],month)
        for customer,amount in recognized.items():
            rows.append([f'FIN-REV-{tag}-{customer}',date,'recognized_revenue',amount,customer,'Monthly subscription service accrued from effective contract prices'])
        for customer in sorted(set(recognized)|set(previous)):
            receipt=round(recognized.get(customer,0)*.85+previous.get(customer,0)*.15,2)
            if receipt: rows.append([f'FIN-RCT-{tag}-{customer}',date,'cash_receipt',receipt,customer,'Current-month collection plus prior-month receivable settlement'])
        hosting=round(sum(recognized.values())*.12,2)
        for category,amount in [('HOSTING',hosting),('DELIVERY',26000)]:
            rows.extend([[f'FIN-COST-{tag}-{category}',date,'direct_cost',amount,None,category.title()+' service cost recognized in the month'],[f'FIN-PAY-{tag}-{category}',date,'cash_payment',amount,None,category.title()+' service cost paid in the month']])
        rows.append([f'FIN-PAY-{tag}-OPERATING',date,'cash_payment',48000,None,'Other payroll and operating cash payments; excluded from gross service margin'])
        bank=round(bank+sum(round(recognized.get(c,0)*.85+previous.get(c,0)*.15,2) for c in set(recognized)|set(previous))-hosting-26000-48000,2)
        rows.append([f'FIN-CLOSE-{tag}',date,'closing_cash',bank,None,'Month-end bank statement balance; must reconcile to recorded cash movements'])
        previous=recognized
    return pd.DataFrame(rows,columns=FINANCE_COLUMNS)

def completed_months(data,week):
    cutoff=pd.Timestamp(week)+pd.Timedelta(days=7)
    ledger=data.get('financial_entries',pd.DataFrame(columns=FINANCE_COLUMNS))
    if ledger.empty: return []
    dates=pd.to_datetime(ledger.entry_date)
    return sorted({d.to_period('M').start_time for d in dates[ledger.entry_type.eq('closing_cash')] if d.to_period('M').end_time<cutoff})

def finance_kpis(data,month,cutoff=None):
    empty={key:None for key in ['revenue','direct_cost','gross_profit','gross_margin','cash_receipts','cash_payments','opening_cash','closing_cash']}
    if month is None: return empty
    month=pd.Timestamp(month).to_period('M').start_time; end=month+pd.offsets.MonthBegin(1)
    if cutoff is not None and end>pd.Timestamp(cutoff): return empty
    ledger=data.get('financial_entries',pd.DataFrame(columns=FINANCE_COLUMNS)).copy()
    if ledger.empty: return empty
    ledger.entry_date=pd.to_datetime(ledger.entry_date); period=ledger[ledger.entry_date.ge(month)&ledger.entry_date.lt(end)]
    if not period.entry_type.eq('closing_cash').any(): return empty
    total=lambda kind:float(period.loc[period.entry_type.eq(kind),'amount'].sum())
    revenue=total('recognized_revenue'); cost=total('direct_cost'); receipts=total('cash_receipt'); payments=total('cash_payment')
    earlier=ledger[ledger.entry_date.lt(month)]; has_opening=ledger[ledger.entry_date.lt(end)].entry_type.eq('opening_cash').any()
    opening=float(earlier.loc[earlier.entry_type.isin(['opening_cash','cash_receipt']),'amount'].sum()-earlier.loc[earlier.entry_type.eq('cash_payment'),'amount'].sum()) if has_opening else None
    return {'revenue':revenue,'direct_cost':cost,'gross_profit':revenue-cost,'gross_margin':(revenue-cost)/revenue if revenue>0 else None,'cash_receipts':receipts,'cash_payments':payments,'opening_cash':opening,'closing_cash':opening+receipts-payments if opening is not None else None}

def finance_errors(data):
    """Journal consistency; operational imports are allowed while incomplete finances
    are marked unreconciled. A submitted finance report must resolve these errors.
    """
    f=data.get('financial_entries',pd.DataFrame(columns=FINANCE_COLUMNS)); errors=[]
    if f.empty: return errors
    if f.entry_type.eq('opening_cash').sum()!=1: errors.append(('opening_cash','Exactly one opening bank balance is required.'))
    opening=f[f.entry_type.eq('opening_cash')]
    if len(opening) and f.loc[f.entry_type.ne('opening_cash'),'entry_date'].lt(opening.entry_date.iloc[0]).any(): errors.append(('entry_date','Cash/financial activity cannot precede the opening reporting balance.'))
    revenue=f[f.entry_type.eq('recognized_revenue')]; expected_months={}
    for month,group in revenue.groupby(revenue.entry_date.dt.to_period('M')):
        expected=subscription_revenue(data['subscription_events'],month.start_time); expected_months[month]=expected
        actual=group.groupby('customer_id').amount.sum().to_dict()
        for customer in set(expected)|set(actual):
            if abs(actual.get(customer,0)-expected.get(customer,0))>.011: errors.append((customer,f'Recognized subscription revenue for {month} must reconcile to contract service accrual: expected EUR {expected.get(customer,0):,.2f}.'))
        if group.customer_id.duplicated().any(): errors.append((str(month),f'Use one recognized subscription revenue entry per customer for {month}.'))
    closing=f[f.entry_type.eq('closing_cash')]
    if closing.entry_date.dt.to_period('M').duplicated().any(): errors.append(('closing_cash','Use one bank closing balance per month.'))
    for _,row in closing.iterrows():
        month=row.entry_date.to_period('M'); end=month.end_time
        if row.entry_date.normalize()!=end.normalize(): errors.append((row.entry_id,f'Closing bank balance for {month} must be dated on the last day of that month.'))
        history=f[f.entry_date.le(end)]
        expected=float(history.loc[history.entry_type.isin(['opening_cash','cash_receipt']),'amount'].sum()-history.loc[history.entry_type.eq('cash_payment'),'amount'].sum())
        if abs(expected-row.amount)>.011: errors.append((row.entry_id,f'Closing cash for {month} must reconcile to opening cash + receipts - payments: expected EUR {expected:,.2f}.'))
        expected_revenue=expected_months.get(month)
        if expected_revenue is None: expected_revenue=subscription_revenue(data['subscription_events'],month.start_time)
        month_revenue=revenue[revenue.entry_date.dt.to_period('M').eq(month)].groupby('customer_id').amount.sum().to_dict()
        if set(expected_revenue)-set(month_revenue): errors.append((row.entry_id,f'Closed month {month} is missing recognized revenue for subscription customers.'))
    return errors

def monthly_view(data,month,week):
    cutoff=pd.Timestamp(week)+pd.Timedelta(days=7); current=finance_kpis(data,month,cutoff)
    previous=finance_kpis(data,pd.Timestamp(month)-pd.offsets.MonthBegin(1),cutoff) if month is not None else finance_kpis(data,None)
    errors=finance_errors(data)
    if any(record in ['opening_cash','closing_cash','entry_date'] for record,_ in errors):
        return {key:None for key in current},{key:None for key in previous}
    # A changed contract can make a posted month unreliable without blocking a
    # valid operational import; never display the inconsistent number as revenue.
    if month is not None and any(str(pd.Timestamp(month).to_period('M')) in message for _,message in errors):
        current={key:None for key in current}
    if month is not None and any(str((pd.Timestamp(month)-pd.offsets.MonthBegin(1)).to_period('M')) in message for _,message in errors):
        previous={key:None for key in previous}
    return current,previous

def customer_kpis(data,week):
    week=pd.Timestamp(week); end=week+pd.Timedelta(days=7); events=data['subscription_events']
    before=events[events.event_date.lt(week)].sort_values(['customer_id','event_date','event_id']).groupby('customer_id').tail(1)
    latest=events[events.event_date.lt(end)].sort_values(['customer_id','event_date','event_id']).groupby('customer_id').tail(1)
    active=set(latest.loc[latest.mrr_after.gt(0),'customer_id']); opening=set(before.loc[before.mrr_after.gt(0),'customer_id'])
    changes=events[events.event_date.ge(week)&events.event_date.lt(end)]
    first_paid=events[events.mrr_after.gt(0)].sort_values(['customer_id','event_date','event_id']).groupby('customer_id').head(1)
    acquired=set(first_paid.loc[first_paid.event_type.eq('new')&first_paid.event_date.ge(week)&first_paid.event_date.lt(end),'customer_id'])
    lost=set(changes.loc[changes.event_type.eq('churn')&changes.customer_id.isin(opening),'customer_id'])-active
    return {'active_customers':len(active),'new_customers':len(acquired),'customers_lost':len(lost),'customer_churn':len(lost)/len(opening) if opening else None}

def funnel_records(data,week):
    """One created-lead cohort through linked opportunities and cutoff stage events.
    Qualification history is absent and is deliberately omitted from the funnel.
    """
    week=pd.Timestamp(week); end=week+pd.Timedelta(days=7)
    leads=data['leads'][data['leads'].created_at.ge(week)&data['leads'].created_at.lt(end)]
    opportunities=data['opportunities'][data['opportunities'].lead_id.isin(leads.lead_id)&data['opportunities'].created_at.lt(end)]
    events=data['opportunity_stage_events']; latest=events[events.event_date.lt(end)].sort_values(['opportunity_id','event_date','stage_event_id']).groupby('opportunity_id').tail(1)
    records=opportunities[['opportunity_id','lead_id','created_at']].merge(latest[['opportunity_id','stage','event_date','pipeline_value']],on='opportunity_id',how='left')
    won=records[records.stage.eq('won')]; lost=records[records.stage.eq('lost')]
    cohort=lambda frame:frame.lead_id.nunique()
    values={'leads':len(leads),'opportunities':len(records),'won':len(won),'lost':len(lost),'funnel_opportunity_leads':cohort(records),'funnel_won_leads':cohort(won),'lead_to_opportunity':cohort(records)/len(leads) if len(leads) else None,'opportunity_win_rate':len(won)/(len(won)+len(lost)) if len(won)+len(lost) else None}
    return values,leads,records

def onboarding(data,week):
    week=pd.Timestamp(week); end=week+pd.Timedelta(days=7); p,m=delivery_records(data,week)
    completions=m.groupby('project_id').agg(total=('milestone_id','count'),done=('completed_at','count'),finished_at=('completed_at','max'))
    p=p.merge(completions[['total','done','finished_at']],on='project_id',how='left')
    p['is_complete']=p.total.gt(0)&p.done.eq(p.total); p['outstanding_tasks']=p.total-p.done
    p['is_delayed']=~p.is_complete&(p.target_go_live.lt(end)|p.overdue.gt(0))
    p['status']=p.apply(lambda r:'Completed' if r.is_complete else 'Delayed' if r.is_delayed else 'In progress',axis=1)
    completed=p[p.is_complete&p.finished_at.ge(week)&p.finished_at.lt(end)]
    counts={'active_onboardings':int((~p.is_complete).sum()),'completed_onboardings':len(completed),'delayed_projects':int(p.is_delayed.sum()),'overdue_tasks':int(m.overdue.sum()),'completed_to_date':int(p.is_complete.sum())}
    return counts,p,m

def weekly_business(data,week):
    snapshot=weekly_snapshot(data,week); customers=customer_kpis(data,week); sales,_,_=funnel_records(data,week); projects,_,_=onboarding(data,week)
    return {**customers,**sales,**projects,'new_tickets':snapshot['support']['ticket_volume'],'resolved_tickets':snapshot['support']['tickets_resolved'],'open_tickets':snapshot['support']['backlog'],'overdue_tickets':snapshot['support']['open_sla_breaches']}

def simple_issues(data,week):
    """Record-grounded presentation; original alert engine remains available."""
    week=pd.Timestamp(week); weeks=reporting_weeks(data); previous=week-pd.Timedelta(days=7)
    now=weekly_business(data,week); before=weekly_business(data,previous) if previous in weeks else None; issues=[]
    def add(title,level,facts,why,investigation,refs): issues.append({'title':title,'level':level,'observations':facts,'why':why,'investigate':investigation,'evidence_refs':refs})
    if now['overdue_tickets']:
        change=now['overdue_tickets']-before['overdue_tickets'] if before else None
        add(f"{now['overdue_tickets']} support ticket{'s are' if now['overdue_tickets']!=1 else ' is'} past the resolution target",'High',[f"{now['open_tickets']} tickets remain open."]+([f"Overdue cases changed by {change:+d} versus last week."] if change is not None else []),'Customers are waiting beyond the stated service target.','Review the oldest unresolved cases and their categories.',['support.overdue_tickets','support.open_tickets'])
    if now['delayed_projects']:
        add(f"{now['delayed_projects']} customer onboarding project{'s are' if now['delayed_projects']!=1 else ' is'} behind schedule",'High',[f"{now['overdue_tasks']} tasks are overdue.",f"{now['active_onboardings']} onboardings remain active."],'Missed commitments can postpone customer activation.','Inspect project deadlines and outstanding tasks.',['onboarding.delayed_projects','onboarding.overdue_tasks'])
    if now['customers_lost']:
        add(f"{now['customers_lost']} paying customer{'s were' if now['customers_lost']!=1 else ' was'} lost this week",'Needs Attention',[f"{now['new_customers']} new customer{' was' if now['new_customers']==1 else 's were'} acquired in the same week."],'Customer losses reduce the paying customer base.','Review the dated cancellation records.',['customers.customers_lost','customers.new_customers'])
    if before and now['open_tickets']>before['open_tickets']:
        add('Unresolved support work increased','Medium',[f"Open tickets rose from {before['open_tickets']} to {now['open_tickets']}.",f"{now['new_tickets']} tickets arrived and {now['resolved_tickets']} were resolved."],'Incoming work exceeded completed resolutions.','Check which accounts and categories contribute to the increase.',['support.open_tickets','support.new_tickets','support.resolved_tickets'])
    return issues

def related_accounts(data,week):
    tickets=support_records(data,week); _,projects,_=onboarding(data,week)
    delayed=set(projects.loc[projects.is_delayed,'customer_id']); related=tickets[tickets.customer_id.isin(delayed)]
    return {'shared_customer_count':related.customer_id.nunique(),'shared_open_tickets':len(related),'delayed_customer_ids':sorted(delayed),'shared_ticket_ids':related.ticket_id.head(20).tolist()}
