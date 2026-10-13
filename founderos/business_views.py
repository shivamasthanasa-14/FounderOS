"""Founder-focused views reusing the existing Streamlit, Plotly and import services."""
from datetime import date, timedelta
import os
import pandas as pd
import plotly.express as px
import streamlit as st
from .business import (weekly_business,monthly_view,completed_months,finance_errors,funnel_records,onboarding,simple_issues)
from .dashboard import reporting_weeks,format_eur,format_percent
from .periods import support_records
from .presentation import readable_table
from .reporting_ui import reporting_section
from .weekly_brief import BriefStore,brief_context,generate_brief,current_brief,report_sections,export_html,export_markdown,export_pdf
from .evidence import dataset_version

HELP={
 'revenue':'Subscription service earned during the selected completed month. Shows earning activity; calculated from the recognized revenue journal, not MRR or cash receipts.',
 'closing_cash':'Bank balance at month end. Shows available cash; opening cash plus receipts minus payments, reconciled to the bank statement.',
 'gross_margin':'Gross service profit as a share of recognized revenue: (revenue minus direct service costs) / revenue. Shows service economics; excludes other operating payments. N/A without revenue.',
 'active_customers':'Customers paying at the reporting cutoff: latest dated subscription balance greater than zero. Shows the current paying base; future activations are excluded.',
 'new_customers':'Customers whose first paid activation occurred in the selected week. Shows acquisition; returning customers are not counted as first-time acquisitions.',
 'customers_lost':'Customers paying at the start of the week who cancelled and remain unpaid at cutoff. Shows losses from the opening paying base. Churn percentage divides losses by that opening base.',
 'new_tickets':'Support tickets opened during the selected week. Shows incoming demand; a support ticket is not necessarily a complaint.',
 'resolved_tickets':'Tickets resolved during the selected week, including older cases. Shows throughput; future resolutions are excluded.',
 'open_tickets':'Tickets created before cutoff and not resolved before it. Shows unresolved workload.',
 'overdue_tickets':'Open tickets past their recorded resolution deadline: opening timestamp plus elapsed calendar SLA hours. Shows customers waiting beyond the stated target.',
 'active_onboardings':'Projects started before cutoff with at least one required task still incomplete. Shows the current onboarding workload.',
 'completed_onboardings':'Projects whose last required task was completed during the selected week. Shows completed customer onboardings; future completions are excluded.',
 'delayed_projects':'Incomplete onboarding projects with an overdue target completion date or overdue task. Shows missed commitments; not a claim about root causes.',
 'overdue_tasks':'Incomplete project tasks whose deadline passed by cutoff. Shows commitments needing review.',
 'leads':'Leads created during the selected week. Funnel comparisons use this same cohort.',
 'opportunities':'Sales opportunities linked to the selected lead cohort and created by cutoff. Shows progression; a lead can have multiple opportunities.',
 'won':'Linked cohort opportunities whose latest dated stage is won by cutoff. Shows sales outcomes; future stage changes are excluded.',
 'lost':'Linked cohort opportunities whose latest dated stage is lost by cutoff. Shows unsuccessful outcomes; future stage changes are excluded.',
 'lead_to_opportunity':'Share of created-week leads with at least one opportunity by cutoff. Shows cohort progression without using undated qualification status.',
 'opportunity_win_rate':'Won opportunities / (won + lost) for the same linked cohort by cutoff. Shows closed-deal outcomes; N/A when the cohort has no closures.',
}

def money(value): return 'N/A' if value is None else ('-€' if value<0 else '€')+f'{abs(value):,.0f}'
def display(value,kind='count'):
    if value is None: return 'N/A'
    return money(value) if kind=='money' else format_percent(value) if kind=='rate' else f'{value:,.0f}'

def card_group(specs,current,previous,metric,period='last week'):
    for start in range(0,len(specs),3 if len(specs)==6 else min(4,len(specs))):
        size=3 if len(specs)==6 else min(4,len(specs))
        for col,(key,label,kind,higher) in zip(st.columns(size),specs[start:start+size]):
            value=current.get(key); before=previous.get(key); delta=value-before if value is not None and before is not None else None
            note='Comparison unavailable' if delta is None else 'Unchanged versus '+period if delta==0 else ('Up ' if delta>0 else 'Down ')+(f'{abs(delta)*100:.1f} percentage points' if kind=='rate' else display(abs(delta),kind))+' versus '+period
            favorable=None if delta in [None,0] or higher is None else (delta>0)==higher
            if key=='customers_lost' and current.get('customer_churn') is not None: note += ' · '+format_percent(current['customer_churn'])+' of the opening customer base'
            metric(col,label,display(value,kind),note,favorable,HELP.get(key,''))

def operating_comparison(data,week):
    previous=pd.Timestamp(week)-pd.Timedelta(days=7); label='last week'
    with st.expander('Optional period comparison'):
        mode=st.selectbox('Operating comparison',['Previous week','Choose an earlier week'],key='simple_compare_mode')
        if mode=='Choose an earlier week':
            dates=[w for w in reporting_weeks(data) if w<pd.Timestamp(week)]
            if dates:
                previous=st.selectbox('Compare with reporting week',dates,index=len(dates)-1,format_func=lambda d:pd.Timestamp(d).strftime('%d %b %Y'),key='simple_compare_week'); label='week of '+pd.Timestamp(previous).strftime('%d %b')
            else: previous=None
        st.caption('Operating measures compare weeks. Financial measures always compare completed calendar months.')
    return weekly_business(data,previous) if previous is not None and previous in reporting_weeks(data) else {},label

def line(frame,x,y,title,percent=False,money_axis=False):
    fig=px.line(frame,x=x,y=y,markers=True,title=title,template='plotly_white',color_discrete_sequence=['#2967b1','#7d94aa'])
    fig.update_layout(height=285,margin=dict(l=12,r=12,t=45,b=20),legend_title_text='',xaxis_title='',yaxis_title='EUR' if money_axis else 'Share' if percent else 'Records',paper_bgcolor='#ffffff',hovermode='x unified')
    if percent: fig.update_yaxes(tickformat='.0%')
    if x=='Month': fig.update_xaxes(dtick='M1',tickformat='%b %Y')
    if x=='Week': fig.update_xaxes(tickformat='%d %b')
    st.plotly_chart(fig,width='stretch')

def monthly_trend(data,week):
    rows=[]
    for month in completed_months(data,week):
        now,_=monthly_view(data,month,week); rows.append({'Month':month,'Monthly Revenue':now['revenue'],'Cash in Bank':now['closing_cash']})
    return pd.DataFrame(rows,columns=['Month','Monthly Revenue','Cash in Bank'])

def weekly_trend(data,week):
    return pd.DataFrame([{'Week':w,**weekly_business(data,w)} for w in reporting_weeks(data) if w<=pd.Timestamp(week)])

def funnel(data,week):
    values,leads,records=funnel_records(data,week)
    frame=pd.DataFrame({'Stage':['Leads','Leads with an opportunity','Leads with a won deal'],'Count':[values['leads'],values['funnel_opportunity_leads'],values['funnel_won_leads']]})
    st.plotly_chart(px.funnel(frame,y='Stage',x='Count',template='plotly_white',color_discrete_sequence=['#2967b1']).update_layout(height=285,margin=dict(l=12,r=12,t=20,b=12)),width='stretch')
    st.caption('The same created-week lead cohort is used throughout. A won deal is not assumed to be a paying customer; no contract-to-deal link exists in these records.')
    return values,leads,records

def issue_panel(data,week):
    issues=simple_issues(data,week)
    if not issues: st.success('No important operational issue was identified for this reporting week.')
    for issue in issues:
        with st.container(border=True):
            st.markdown('**'+issue['title']+'**'); st.caption(issue['level'])
            st.write(' '.join(issue['observations'])); st.write(issue['why'])
            with st.expander('Supporting evidence and area to review'):
                st.write(issue['investigate']); st.caption('Measures: '+', '.join(issue['evidence_refs']))

def executive(data,week,month,metric):
    now=weekly_business(data,week); before,period=operating_comparison(data,week); fin,pfin=monthly_view(data,month,week)
    # Six headline cards with mixed, clearly labeled month/week conventions.
    specs=[('revenue','Monthly Revenue','money',True),('closing_cash','Cash in Bank','money',None),('active_customers','Active Customers','count',True),('new_customers','New Customers','count',True),('customers_lost','Customer Churn','count',False),('gross_margin','Gross Margin','rate',True)]
    for start in [0,3]:
        for col,(key,label,kind,higher) in zip(st.columns(3),specs[start:start+3]):
            source=fin if key in fin else now; prior=pfin if key in fin else before; suffix='last month' if key in fin else period
            value=source.get(key); old=prior.get(key); delta=value-old if value is not None and old is not None else None
            note='Comparison unavailable' if delta is None else 'Unchanged versus '+suffix if delta==0 else ('Up ' if delta>0 else 'Down ')+(f'{abs(delta)*100:.1f} percentage points' if kind=='rate' else display(abs(delta),kind))+' versus '+suffix
            if key=='customers_lost' and now['customer_churn'] is not None: note+=' · '+format_percent(now['customer_churn'])+' churn'
            metric(col,label,display(value,kind),note,None if delta in [None,0] or higher is None else (delta>0)==higher,HELP[key])
    st.caption('Financial month: '+(pd.Timestamp(month).strftime('%B %Y') if month is not None else 'N/A · no completed month has been reported')+'. Operating measures: selected reporting week.')
    if month is not None and fin['revenue'] is None: st.warning('The selected financial month needs reconciliation. Review its Financial Entries in Revenue & Sales.')
    a,b=st.columns(2)
    with a: line(monthly_trend(data,week),'Month','Monthly Revenue','Monthly revenue',money_axis=True)
    with b: line(weekly_trend(data,week).rename(columns={'active_customers':'Active Customers'}),'Week','Active Customers','Customer growth')
    st.subheader('Sales funnel'); funnel(data,week)
    st.subheader('Operational health')
    card_group([('open_tickets','Open Support Tickets','count',False),('overdue_tickets','Overdue Support Tickets','count',False),('active_onboardings','Active Onboardings','count',None),('delayed_projects','Delayed Onboarding Projects','count',False)],now,before,metric,period)
    st.subheader('What needs attention'); issue_panel(data,week)

def revenue(data,week,month,metric,store):
    reporting_section('Revenue & Sales',data,store); now=weekly_business(data,week); before,period=operating_comparison(data,week); fin,pfin=monthly_view(data,month,week)
    st.subheader('How much are we earning?')
    card_group([('revenue','Monthly Revenue','money',True),('gross_margin','Gross Margin','rate',True),('closing_cash','Cash in Bank','money',None)],fin,pfin,metric,'last month')
    line(monthly_trend(data,week),'Month','Monthly Revenue','Monthly revenue',money_axis=True)
    with st.expander('Revenue, profit and cash breakdown'):
        st.dataframe(pd.DataFrame([{'Measure':label,'EUR':fin[key]} for key,label in [('revenue','Recognized subscription revenue'),('direct_cost','Direct service costs'),('gross_profit','Gross service profit'),('cash_receipts','Cash receipts'),('cash_payments','Cash payments'),('opening_cash','Opening bank balance'),('closing_cash','Closing bank balance')]]),hide_index=True,width='stretch')
        st.caption('Gross service profit excludes other operating costs. Bank cash includes collections and all recorded cash payments; it is not profit.')
        if month is not None:
            end=pd.Timestamp(month)+pd.offsets.MonthBegin(1); f=data['financial_entries']; st.dataframe(readable_table(f[f.entry_date.ge(month)&f.entry_date.lt(end)]),hide_index=True,width='stretch')
    st.subheader('Are we acquiring customers?'); card_group([('new_customers','New Customers','count',True),('leads','New Sales Leads','count',None)],now,before,metric,period)
    st.subheader('Are we converting leads?'); values,leads,records=funnel(data,week)
    card_group([('opportunities','Sales Opportunities','count',None),('won','Deals Won','count',True),('lost','Deals Lost','count',False),('opportunity_win_rate','Closed-deal Win Rate','rate',True)],now,before,metric,period)
    card_group([('lead_to_opportunity','Leads Reaching an Opportunity','rate',True)],now,before,metric,period)
    with st.expander('Inspect the sales cohort records'):
        st.dataframe(readable_table(leads),hide_index=True,width='stretch'); st.dataframe(readable_table(records),hide_index=True,width='stretch')
    st.subheader('Are we retaining customers?'); card_group([('active_customers','Active Customers','count',True),('customers_lost','Customers Lost','count',False)],now,before,metric,period)
    with st.expander('Advanced subscription metrics · recurring revenue'):
        from .periods import compare_metrics
        from .reporting_ui import cards,explanations
        rows,_=compare_metrics(data,week); comp={r['key']:r for r in rows}
        # Adapter retains existing card behavior, while help is supplied separately.
        from .periods import METRICS
        definitions={METRICS[key][0]:METRICS[key][-1] for key in ['mrr','net_new_mrr','gross_revenue_churn']}
        cards(['mrr','net_new_mrr','gross_revenue_churn'],comp,lambda col,label,value,delta,tone:metric(col,label,value,delta,tone,definitions[label])); explanations(['mrr','net_new_mrr','gross_revenue_churn'])
        st.caption('MRR is the recurring monthly contract run rate. It is distinct from earned service revenue and collected cash.')
        from .analytics import weekly_snapshot
        movements=weekly_snapshot(data,week)['revenue']
        st.dataframe(pd.DataFrame([{'Movement':label,'MRR (EUR)':movements[key]} for key,label in [('new_mrr','New subscriptions'),('expansion_mrr','Account expansion'),('contraction_mrr','Account contraction'),('churn_mrr','Cancellations')]]),hide_index=True,width='stretch')
        subscriptions=data['subscription_events']; end=pd.Timestamp(week)+pd.Timedelta(days=7)
        st.dataframe(readable_table(subscriptions[subscriptions.event_date.ge(week)&subscriptions.event_date.lt(end)]),hide_index=True,width='stretch')

def support(data,week,metric,store):
    reporting_section('Customer Support',data,store); now=weekly_business(data,week); before,period=operating_comparison(data,week)
    card_group([('new_tickets','New Support Tickets','count',None),('resolved_tickets','Tickets Resolved','count',True),('open_tickets','Open Tickets','count',False),('overdue_tickets','Overdue Tickets','count',False)],now,before,metric,period)
    trend=weekly_trend(data,week).rename(columns={'new_tickets':'Incoming','resolved_tickets':'Resolved','open_tickets':'Open Tickets'})
    a,b=st.columns(2)
    with a: line(trend,'Week',['Incoming','Resolved'],'Support workload')
    with b: line(trend,'Week','Open Tickets','Open ticket trend')
    tickets=data['support_tickets']; end=pd.Timestamp(week)+pd.Timedelta(days=7); period_tickets=tickets[tickets.created_at.ge(week)&tickets.created_at.lt(end)]
    st.subheader('Common customer problems'); grouped=period_tickets.groupby('category',as_index=False).size()
    st.plotly_chart(px.bar(grouped,x='category',y='size',template='plotly_white',labels={'category':'Issue category','size':'Tickets received'},color_discrete_sequence=['#2967b1']),width='stretch')
    st.caption('Support inquiries and product issues are not automatically complaints. Customer satisfaction is not measured in these records.')
    open_=support_records(data,week).merge(data['customers'][['customer_id','company_name']],on='customer_id',how='left').sort_values('age_hours',ascending=False)
    open_['Days waiting']=(open_.age_hours/24).round(2); open_['Resolution target (days)']=(open_.sla_hours/24).round(2); open_['Overdue']=open_.sla_overdue.map({True:'Yes',False:'No'})
    st.subheader('Unresolved tickets'); st.dataframe(open_[['ticket_id','company_name','category','created_at','Days waiting','Resolution target (days)','Overdue']].rename(columns={'ticket_id':'Ticket ID','company_name':'Customer','category':'Issue category','created_at':'Date opened'}),hide_index=True,width='stretch')
    st.caption('Waiting time and resolution targets both use elapsed calendar days. Overdue means the exact opening timestamp plus the target has passed.')
    with st.expander('Ticket deadlines and source records'):
        st.dataframe(readable_table(open_[['ticket_id','customer_id','sla_deadline','hours_past_deadline']]),hide_index=True,width='stretch')
        st.caption('Urgency labels are reporter categories: high = urgent, medium = normal, low = lower urgency. The recorded resolution target, rather than the label alone, determines whether a case is overdue.')
    st.subheader('What needs attention')
    for issue in simple_issues(data,week):
        if any(ref.startswith('support.') for ref in issue['evidence_refs']): st.warning(issue['title']+'. '+' '.join(issue['observations']))

def projects(data,week,metric,store):
    reporting_section('Delivery',data,store); now=weekly_business(data,week); before,period=operating_comparison(data,week)
    card_group([('active_onboardings','Active Onboardings','count',None),('completed_onboardings','Completed Onboardings','count',True),('delayed_projects','Delayed Projects','count',False),('overdue_tasks','Overdue Tasks','count',False)],now,before,metric,period)
    trend=weekly_trend(data,week).rename(columns={'completed_onboardings':'Completed Onboardings'})
    a,b=st.columns(2)
    with a: line(trend,'Week','Completed Onboardings','Onboarding completion trend')
    with b:
        status=pd.DataFrame({'Status':['Active','Completed by cutoff'],'Projects':[now['active_onboardings'],now['completed_to_date']]})
        st.plotly_chart(px.bar(status,x='Status',y='Projects',template='plotly_white',color_discrete_sequence=['#2967b1']),width='stretch')
    counts,p,m=onboarding(data,week); names=data['customers'][['customer_id','company_name']]; p=p.merge(names,on='customer_id',how='left')
    st.subheader('Project progress'); frame=p[['company_name','project_id','start_date','target_go_live','status','done','outstanding_tasks']].rename(columns={'company_name':'Customer','project_id':'Project','start_date':'Start date','target_go_live':'Target completion','status':'Status','done':'Completed tasks','outstanding_tasks':'Outstanding tasks'})
    st.dataframe(frame,hide_index=True,width='stretch')
    st.subheader('Upcoming and overdue tasks'); tasks=m[m.completed_at.isna()].merge(p[['project_id','company_name']],on='project_id',how='left')
    tasks['Status']=tasks.overdue.map({True:'Overdue',False:'Upcoming'})
    st.dataframe(tasks[['company_name','project_id','milestone_id','milestone','due_date','Status']].rename(columns={'company_name':'Customer','project_id':'Project','milestone_id':'Task ID','milestone':'Task','due_date':'Deadline'}).sort_values('Deadline'),hide_index=True,width='stretch')
    with st.expander('Advanced team workload'):
        reporting_section('Team Capacity',data,store); cap=data['team_capacity']; cap=cap[cap.week_start.eq(pd.Timestamp(week))].copy(); cap['Utilization']=cap.allocated_hours/cap.capacity_hours
        st.dataframe(readable_table(cap),hide_index=True,width='stretch'); st.caption('Allocated work does not establish that capacity caused a delay. Completion is inferred from required tasks; project status alone is not used historically.')

def create_followup_form(data,week,store,key):
    with st.form('followup_'+key,clear_on_submit=True):
        description=st.text_input('Follow-up task',key='task_description_'+key)
        owners=list(data['team'].employee_id); owner=st.selectbox('Owner',owners,key='task_owner_'+key)
        deadline=st.date_input('Deadline',date.today()+timedelta(days=7),key='task_deadline_'+key)
        if st.form_submit_button('Record Follow-up'):
            try:
                task=store.create_followup(description,owner,str(deadline),dataset_version(data),str(pd.Timestamp(week).date())); st.success('Follow-up recorded. No notification was sent.'); return task
            except ValueError as exc: st.error(str(exc))

def action_tracker(data,week,store):
    with st.expander('Record a follow-up task'): create_followup_form(data,week,store,'tracker')
    tasks=store.list()
    if not tasks: st.info('No follow-up tasks have been recorded.'); return
    labels={'proposed':'Awaiting review','approved':'Open','in_progress':'Open','blocked':'Blocked','complete':'Completed','deferred':'Deferred','rejected':'Rejected'}
    frame=pd.DataFrame([{'Task':a['description'],'Owner':a['owner'],'Deadline':a['due_date'],'Status':labels.get(a['execution_status'],a['execution_status'])} for a in tasks]); st.dataframe(frame,hide_index=True,width='stretch')
    selected=st.selectbox('Follow-up to update',[a['action_id'] for a in tasks],format_func=lambda aid:next(a['description'] for a in tasks if a['action_id']==aid),key='simple_action_selected')
    action=store.get(selected)
    with st.form('update_routine_followup'):
        states=['in_progress','blocked','complete','deferred']; status=st.selectbox('Task status',states,index=states.index(action['execution_status']) if action['execution_status'] in states else 0,format_func=lambda s:labels[s])
        owners=list(data['team'].employee_id); owner=st.selectbox('Task owner',owners,index=owners.index(action['owner']) if action['owner'] in owners else 0)
        deadline=st.date_input('Task deadline',pd.Timestamp(action['due_date']).date() if action.get('due_date') else date.today()+timedelta(days=7)); note=st.text_input('Task update note')
        if st.form_submit_button('Save Task Changes'): store.update_followup(selected,status,owner,str(deadline),note); st.success('Task updated.'); st.rerun()
    with st.expander('Task history'): st.dataframe(readable_table(pd.DataFrame(store.history(selected))),hide_index=True,width='stretch')

def brief_page(data,week,month,root,action_store):
    store=BriefStore(root/'data'/'weekly_briefs.db'); context=brief_context(data,week,month,action_store); brief=store.latest(week,month)
    with st.expander('Narrative options'):
        provider=st.selectbox('Brief narrative',['deterministic','ollama','hosted'],format_func=lambda p:{'deterministic':'Deterministic summary · no model inference','ollama':'Local Ollama commentary','hosted':'Configured hosted commentary'}[p],key='brief_provider')
        model=st.text_input('Local model',os.getenv('OLLAMA_MODEL','qwen3:1.7b'),key='brief_model')
        st.caption('The optional model writes explanatory commentary. KPI facts and comparisons always come from Python. Local CPU inference can take several minutes.')
    edited=bool(brief and brief['human_edited']); replace=False
    if edited:
        st.info('This brief contains edited commentary. It is saved and will not be replaced automatically.')
        replace=st.checkbox('Replace my edited commentary when generating a new brief.',key='brief_replace_edits')
    if st.button('Generate Weekly Brief',type='primary'):
        if edited and not replace: st.warning('Confirm replacement above before regenerating. Your edited brief is unchanged.')
        else:
            with st.spinner('Preparing the weekly management report…'):
                result=generate_brief(context,provider,model)
                try: store.save(result,replace_edited=replace); st.rerun()
                except ValueError as exc: st.warning(str(exc))
    if not brief: st.info('Generate the brief to prepare a management report from the selected reporting week.'); return
    fresh=current_brief(brief,context)
    if not fresh: st.warning('Reporting data, period or follow-up records changed. This saved brief is stale. Generate a fresh brief before export; your commentary remains saved.')
    st.caption(brief['mode']+(' · '+brief['model'] if brief.get('model') else '')+' · Reporting week '+brief['context']['reporting_week'])
    if brief['error']: st.warning(brief['error']+' A deterministic summary is shown.')
    sections=report_sections(brief)
    for heading in ['Business Performance','What Changed','What Needs Attention']:
        st.subheader(heading)
        for paragraph in sections[heading]: st.write(paragraph)
    st.subheader('Possible Explanations'); st.write(sections['Possible Explanations'][0])
    def save_commentary(): store.edit(brief['brief_id'],st.session_state['commentary_'+brief['brief_id']])
    st.text_area('Edit explanatory commentary',value=brief['commentary'],height=180,max_chars=15000,key='commentary_'+brief['brief_id'],on_change=save_commentary)
    st.caption('Commentary saves when you leave the field. Human edits remain separate from verified facts.')
    # Reload the persisted edit before assembling any export in this rerun.
    brief=store.latest(week,month); sections=report_sections(brief)
    for heading in ['Questions for Management','Follow-Up From Last Week']:
        st.subheader(heading)
        for paragraph in sections[heading]: st.write(paragraph)
    with st.expander('Supporting evidence'):
        st.dataframe(pd.DataFrame(brief['context']['facts']),hide_index=True,width='stretch')
        st.dataframe(pd.DataFrame(brief['context']['records']),hide_index=True,width='stretch')
        st.caption('Numbers are calculated for the selected week and completed financial month. Commentary is provisional; shared account records do not prove causation.')
    st.subheader('Export management report'); base='RelayOps_Weekly_Brief_'+str(pd.Timestamp(week).date())
    a,b,c=st.columns(3)
    a.download_button('Export PDF',export_pdf(brief),base+'.pdf',mime='application/pdf',disabled=not fresh)
    b.download_button('Export HTML',export_html(brief),base+'.html',mime='text/html',disabled=not fresh)
    c.download_button('Export Markdown',export_markdown(brief),base+'.md',mime='text/markdown',disabled=not fresh)
    with st.expander('Optional follow-up'): create_followup_form(data,week,action_store,'brief')
