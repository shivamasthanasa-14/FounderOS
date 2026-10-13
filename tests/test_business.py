import pandas as pd
import pytest
from founderos.analytics import load_data
from founderos.config import DATA_DIR
from founderos.business import (demo_finance,finance_kpis,finance_errors,completed_months,monthly_view,customer_kpis,funnel_records,onboarding,simple_issues,related_accounts,subscription_revenue)
from founderos.reporting import prepare_frames, ReportingStore, template_bytes, prepare_import

@pytest.fixture
def data(): return load_data(DATA_DIR)

def test_demonstration_finances_reconcile_to_contracts_and_bank(data):
    assert not finance_errors(data)
    for month in ['2026-07-01','2026-08-01','2026-09-01']:
        k=finance_kpis(data,month)
        assert k['revenue']==pytest.approx(sum(subscription_revenue(data['subscription_events'],month).values()))
        assert k['gross_profit']==pytest.approx(k['revenue']-k['direct_cost'])
        assert k['closing_cash']==pytest.approx(k['opening_cash']+k['cash_receipts']-k['cash_payments'])
        bank=data['financial_entries']; row=bank[bank.entry_type.eq('closing_cash')&bank.entry_date.dt.to_period('M').eq(pd.Period(month,'M'))].iloc[0]
        assert k['closing_cash']==pytest.approx(row.amount)
    assert finance_kpis(data,'2026-08-01')['cash_receipts']!=finance_kpis(data,'2026-08-01')['revenue']

def test_financial_cutoff_excludes_incomplete_future_month(data):
    assert completed_months(data,'2026-09-21')==[pd.Timestamp('2026-07-01'),pd.Timestamp('2026-08-01')]
    assert all(v is None for v in finance_kpis(data,'2026-09-01','2026-09-28').values())
    assert not completed_months(data,'2026-07-06')
    now,before=monthly_view(data,'2026-08-01','2026-09-21'); assert now['revenue']==finance_kpis(data,'2026-08-01')['revenue']
    assert before['revenue']==finance_kpis(data,'2026-07-01')['revenue']

def test_exact_time_proration_and_opening_balance_policy():
    events=pd.DataFrame([['e1','a',pd.Timestamp('2026-07-05'),'opening',310,310],['e2','a',pd.Timestamp('2026-07-16 12:00'),'churn',310,0]],columns=['event_id','customer_id','event_date','event_type','mrr_before','mrr_after'])
    assert subscription_revenue(events,'2026-07-01')['a']==155
    assert subscription_revenue(events,'2026-06-01')=={}

def test_missing_finance_and_zero_margin_denominator(data):
    d={n:f.copy() for n,f in data.items()}; d['financial_entries']=d['financial_entries'].head(0)
    assert all(v is None for v in finance_kpis(d,'2026-08-01').values())
    d['financial_entries']=pd.DataFrame([['OPEN',pd.Timestamp('2026-07-01'),'opening_cash',0,None,'Balance'],['CLOSE',pd.Timestamp('2026-07-31'),'closing_cash',0,None,'Statement']],columns=data['financial_entries'].columns)
    assert finance_kpis(d,'2026-07-01')['gross_margin'] is None

@pytest.mark.parametrize('kind',['recognized_revenue','closing_cash'])
def test_inconsistent_financial_import_rejected_atomically(tmp_path,data,kind):
    frame=data['financial_entries'][data['financial_entries'].entry_type.eq(kind)].head(1).copy(); frame['amount']+=123; frame.index=[2]
    p=prepare_frames({'financial_entries':frame},'Revenue & Sales',data)
    assert p.errors and any('reconcile' in e['Message'] for e in p.errors)
    store=ReportingStore(tmp_path/'r.db',DATA_DIR)
    with pytest.raises(ValueError): store.commit(p,confirmed=True)
    assert not store.history()

def test_financial_template_and_valid_cash_correction(tmp_path,data):
    p=prepare_import(template_bytes('Revenue & Sales',data),'Revenue & Sales',data)
    assert not p.errors and 'financial_entries' in p.frames
    f=data['financial_entries'].copy(); pay=f.entry_type.eq('cash_payment')&f.entry_date.eq(pd.Timestamp('2026-09-30')); index=f[pay].index[0]; f.loc[index,'amount']+=100
    close=f.entry_type.eq('closing_cash')&f.entry_date.eq(pd.Timestamp('2026-09-30')); f.loc[close,'amount']-=100
    changed=f.loc[[index,*f[close].index]].copy(); changed.index=[2,3]
    p=prepare_frames({'financial_entries':changed},'Revenue & Sales',data); assert not p.errors,p.errors
    s=ReportingStore(tmp_path/'r.db',DATA_DIR); s.commit(p,confirmed=True)
    assert finance_kpis(s.load(),'2026-09-01')['closing_cash']==pytest.approx(finance_kpis(data,'2026-09-01')['closing_cash']-100)

def test_customer_acquisition_churn_and_future_events(data):
    k=customer_kpis(data,'2026-09-21'); assert k['active_customers']==94 and k['customers_lost']==1 and k['new_customers']==0
    d={n:f.copy() for n,f in data.items()}; row=d['subscription_events'].iloc[0].copy(); row['event_id']='FUTURE'; row['event_date']=pd.Timestamp('2026-09-28'); row['event_type']='churn'; row['mrr_after']=0
    d['subscription_events']=pd.concat([d['subscription_events'],pd.DataFrame([row])],ignore_index=True)
    assert customer_kpis(d,'2026-09-21')==k

def test_funnel_uses_linked_lead_cohort_and_cutoff_stages(data):
    values,leads,records=funnel_records(data,'2026-07-06')
    assert set(records.lead_id).issubset(set(leads.lead_id))
    assert values['funnel_won_leads']<=values['funnel_opportunity_leads']<=values['leads']
    assert records.event_date.dropna().lt(pd.Timestamp('2026-07-13')).all()
    assert values['won']==len(records[records.stage.eq('won')])
    assert values['opportunity_win_rate'] is None # no cohort closures by early cutoff

def test_onboarding_completion_reconstructed_from_tasks(data):
    counts,p,m=onboarding(data,'2026-09-21')
    assert counts['active_onboardings']==6 and counts['delayed_projects']==6 and counts['overdue_tasks']==12
    assert p.loc[p.is_complete,'outstanding_tasks'].eq(0).all()
    d={n:f.copy() for n,f in data.items()}; d['implementation_milestones'].loc[0,'completed_at']=pd.Timestamp('2026-10-01')
    changed,projects,_=onboarding(d,'2026-09-21')
    assert changed['active_onboardings']==counts['active_onboardings']+1
    assert projects.loc[projects.project_id.eq('IMP-001'),'is_complete'].iloc[0]==False

def test_plain_issues_have_facts_and_no_numerical_score(data):
    issues=simple_issues(data,'2026-09-21'); assert issues
    assert any('6 customer onboarding projects' in i['title'] for i in issues)
    assert all('priority_score' not in i and i['observations'] and i['evidence_refs'] for i in issues)
    assert set(i['level'] for i in issues).issubset({'Needs Attention','High','Medium','Low'})
    relationship=related_accounts(data,'2026-09-21'); assert relationship['shared_open_tickets']>=relationship['shared_customer_count']

def test_changed_contract_marks_closed_finances_unreconciled(data):
    d={n:f.copy() for n,f in data.items()}; d['subscription_events'].loc[0,'mrr_after']+=50
    assert finance_errors(d)
    now,_=monthly_view(d,'2026-08-01','2026-09-21'); assert now['revenue'] is None
