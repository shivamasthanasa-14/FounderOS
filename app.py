import io
from html import escape
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from founderos.config import DATA_DIR
from founderos.analytics import load_data
from founderos.dashboard import overview, reporting_weeks, weekly_trend, validate_upload, replacement_data, format_eur, format_percent, REQUIRED_COLUMNS
from founderos.ai_service import run as run_chief
from founderos.evidence import dataset_version, evidence_package
from founderos.presentation import STATUS_LABELS, EVIDENCE_LABELS, readable_table, rate_available, display_rate, comparison, priority_components, evidence_value, trend_for_display
from founderos.actions import ActionStore
from founderos.workflows import MockNotificationReceiver, dispatch_event
from founderos.config import ROOT
from founderos.reporting import ReportingStore, REPORTS, prepare_frames
from founderos.reporting_ui import reporting_section, comparison_controls, cards, explanations, import_history, account_investigation
from founderos.periods import support_records, delivery_records, open_pipeline, metric_values
from founderos import business_views
from founderos.business import completed_months, simple_issues

st.set_page_config(page_title="FounderOS | RelayOps", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
st.html("""<style>
 .stApp {background:#f4f6fa;color:#172033}.block-container {padding:1.5rem 2.5rem 3rem;max-width:1500px}
 section[data-testid='stSidebar'] {background:#101c30}
 section[data-testid='stSidebar'] h1,section[data-testid='stSidebar'] p,section[data-testid='stSidebar'] label {color:#e8eef8}
 section[data-testid='stSidebar'] .stRadio label:has(input:checked) {background:#244571;border-radius:6px}
 section[data-testid='stSidebar'] .stRadio label {padding:.35rem .55rem}
 section[data-testid='stSidebar'] [data-testid='stExpander'] {background:#17263d;color:#e8eef8}
 h1 {font-size:2rem!important;letter-spacing:-.04em} h3 {font-size:1.2rem!important}
 .kpi-card {background:#fff;border:1px solid #e2e7ef;border-radius:10px;padding:1rem;min-height:138px;margin-bottom:.6rem}
 .kpi-label {font-size:.82rem;color:#596579;font-weight:650}.kpi-value {font-size:1.8rem;font-weight:750;margin:.35rem 0;color:#172033}
 .subtle {font-size:.8rem;color:#596579;line-height:1.5}.good {color:#087f5b}.bad {color:#b63d32}
 [data-testid='stVerticalBlockBorderWrapper'] {border-radius:10px}
 .stButton>button {border-radius:7px;font-weight:600}
 @media(max-width:1100px) {.block-container {padding:1rem 1.25rem}.kpi-value {font-size:1.5rem}.kpi-card {min-height:145px}}
</style>""")

@st.cache_data(show_spinner=False)
def canonical(): return load_data(DATA_DIR)
def get_data():
    return reporting_store().load()
def reporting_store(): return ReportingStore(ROOT / 'data' / 'reporting_workspace.db',DATA_DIR)
def reset_data():
    reporting_store().restore(confirmed=True)
    st.session_state.pop('working_data',None)
    st.session_state.pop('upload_preview',None)
def action_store(): return ActionStore(ROOT / "data" / "founderos_actions.db")
def title(name, text):
    st.caption("RELAYOPS / WORKSPACE")
    st.title(name)
    st.write(text)

def metric(col,label,value,delta=None,favorable=None,helptext=""):
    tone="" if favorable is None else ("good" if favorable else "bad")
    note = delta or "Selected reporting week"
    tooltip=f" <span title='{escape(helptext,quote=True)}' aria-label='{escape(helptext,quote=True)}'>ⓘ</span>" if helptext else ""
    col.html(f"<div class='kpi-card'><div class='kpi-label'>{escape(label)}{tooltip}</div><div class='kpi-value'>{escape(str(value))}</div><div class='subtle {tone}'>{escape(note)}</div></div>")

def weeks_selector(data):
    weeks=reporting_weeks(data)
    if 'reporting_week' in st.session_state and st.session_state.reporting_week not in weeks: st.session_state.reporting_week=weeks[-1]
    return st.selectbox("Reporting week",weeks,index=len(weeks)-1,format_func=lambda x:pd.Timestamp(x).strftime("Week of %d %b %Y"),key="reporting_week")

def chart(df,x,y,title_,percent=False):
    unit = "Share (%)" if percent else "MRR (€)" if y in ["MRR","Net new MRR"] else "Records"
    fig=px.line(df,x=x,y=y,markers=True,template="plotly_white",title=title_,color_discrete_sequence=["#2967b1","#677d99"],labels={x:"Reporting week", "value":unit})
    fig.update_layout(margin=dict(l=12,r=12,t=44,b=12),height=290,legend_title_text="",legend=dict(orientation="h",y=-.3),paper_bgcolor="#ffffff",hovermode="x unified")
    fig.update_xaxes(title="Reporting week",tickformat="%d %b")
    fig.update_yaxes(title=unit,tickformat=".0%" if percent else ",.0f")
    if percent:
        columns = y if isinstance(y,list) else [y]
        maximum = df[columns].max().max()
        fig.update_yaxes(range=[0,max(1.05,float(maximum)*1.1) if pd.notna(maximum) else 1.05])
    elif len(df)==1:
        fig.update_yaxes(rangemode="tozero")
    fig.update_traces(hovertemplate="%{y:.1%}<extra>%{fullData.name}</extra>" if percent else "%{y:,.0f}<extra>%{fullData.name}</extra>",connectgaps=False)
    st.plotly_chart(fig,width="stretch")

def table(frame, **kwargs):
    st.dataframe(readable_table(frame),width="stretch",hide_index=True,**kwargs)

def alerts_panel(info):
    if not info["alerts"]: st.success("No material operational issue meets the current alert thresholds."); return
    for alert in info["alerts"]:
        with st.container(border=True):
            st.markdown(f"**{alert['title']}**")
            st.caption(f"{alert['area']} · {alert['severity'].title()}")
            st.write(alert['recommendation'])

NAVIGATION = {
    'Business Overview':['Executive Overview'],
    'Business Performance':['Revenue & Sales','Customer Support','Delivery & Capacity'],
    'Management Reporting':['Weekly Business Brief','Data Management'],
    'Additional Tools':['Action Center','Workflow Monitor'],
    'Advanced tools':['Management Issues','AI Chief of Staff','Action Center','Workflow Monitor'],
}
NAV_KEYS={'Business Overview':'nav_Overview','Business Performance':'nav_Business Performance','Management Reporting':'nav_Administration','Additional Tools':'nav_Additional Tools','Advanced tools':'nav_Decision Intelligence'}
PAGE_LABELS={'Delivery & Capacity':'Customer Onboarding & Projects','Data Management':'Data Uploads','Action Center':'Action Tracker','Management Issues':'Advanced issue evidence','AI Chief of Staff':'Advanced AI investigation'}
ICONS={'Executive Overview':'◈','Revenue & Sales':'↗','Customer Support':'◎','Delivery & Capacity':'▦','Weekly Business Brief':'▤','Data Management':'⇧','Action Center':'✓','Workflow Monitor':'⇄','Management Issues':'⚑','AI Chief of Staff':'✦'}
if 'page' not in st.session_state: st.session_state.page='Executive Overview'

def navigate(section):
    st.session_state.page=st.session_state[NAV_KEYS[section]]
    for other in NAVIGATION:
        if other!=section: st.session_state[NAV_KEYS[other]]=None

with st.sidebar:
    st.title('FounderOS'); st.caption('RelayOps Workspace'); st.divider()
    for section,routes in NAVIGATION.items():
        key=NAV_KEYS[section]
        if key not in st.session_state: st.session_state[key]=st.session_state.page if section!='Advanced tools' and st.session_state.page in routes else None
        if section=='Advanced tools':
            with st.expander('Optional advanced tools'):
                st.radio('Advanced features',routes,index=None,key=key,on_change=navigate,args=(section,),format_func=lambda name:PAGE_LABELS.get(name,'Advanced '+name))
        else:
            st.radio(section,routes,index=None,key=key,on_change=navigate,args=(section,),format_func=lambda name:f"{ICONS[name]}  {PAGE_LABELS.get(name,name)}")
    with st.expander('About this demo'):
        st.write('RelayOps is a synthetic 20-person subscription software business. Financial assumptions, reporting coverage and limitations are documented in README. No real company records or notifications are included by default.')

page=st.session_state.page

data=get_data(); week=weeks_selector(data); info=overview(data,week); now,prev=info['snapshot'],info['previous']
if st.session_state.get('reporting_notice'): st.success(st.session_state.pop('reporting_notice'))
month=None
if page in ['Executive Overview','Revenue & Sales','Weekly Business Brief']:
    months=completed_months(data,week)
    if months:
        if 'financial_month' in st.session_state and st.session_state.financial_month not in months: st.session_state.financial_month=months[-1]
        month=st.selectbox('Completed financial month',months,index=len(months)-1,format_func=lambda m:pd.Timestamp(m).strftime('%B %Y'),key='financial_month')
    else: st.caption('Monthly financial reporting: N/A · no completed financial month is available at this cutoff.')

if page=='Executive Overview':
    title('Executive Overview','Revenue, bank cash, customers and the operational work needing attention.')
    business_views.executive(data,week,month,metric)
elif page=='Revenue & Sales':
    title('Revenue & Sales','Understand earnings, customer acquisition, sales conversion and retention.')
    business_views.revenue(data,week,month,metric,reporting_store())
elif page=='Customer Support':
    title('Customer Support','Incoming requests, completed resolutions and customers still waiting.')
    business_views.support(data,week,metric,reporting_store())
elif page=='Delivery & Capacity':
    title('Customer Onboarding & Projects','Customer onboarding progress, completed work and missed commitments.')
    business_views.projects(data,week,metric,reporting_store())
elif page=='Weekly Business Brief':
    title('Weekly Business Brief','Prepare, edit and export a grounded management report for the selected week.')
    business_views.brief_page(data,week,month,ROOT,action_store())
elif page=='Management Issues':
    title('Operational issue evidence','Inspect factual support and account-level relationships behind important issues.')
    business_views.issue_panel(data,week); account_investigation(data,week)
elif page=="AI Chief of Staff":
    title("AI Chief of Staff","Investigate evidence, compare interventions and prepare decisions under human control.")
    from founderos.decision_workspace import render_workspace
    render_workspace(data,week,info['alerts'],action_store)
elif page=='Action Center':
    title('Action Tracker','Record a follow-up, assign an owner and track it to completion.')
    business_views.action_tracker(data,week,action_store())
    with st.expander('Advanced approval and assignment controls'):
        store=action_store(); actions=store.list(); reference_date=str(pd.Timestamp(week).date())
        if not actions: st.info("No actions yet. Propose one from the AI Chief of Staff workspace.")
        else:
            status=st.selectbox("Filter business status",["All"]+sorted({a['execution_status'] for a in actions}),format_func=lambda x:STATUS_LABELS.get(x,x)); shown=[a for a in actions if status=="All" or a['execution_status']==status]
            rows=[]
            for x in shown:
                events=store.event_for_action(x['action_id']); x={**x,"dispatch_status":events[0]['status'] if events else 'not queued',"last_workflow_attempt":events[0]['last_attempt_at'] if events else None}
                x['Deadline status'] = 'Overdue' if x['action_id'] in {item['action_id'] for item in store.overdue(reference_date)} else 'Completed' if x['execution_status']=='complete' else 'Within reporting deadline'
                rows.append(x)
            table(pd.DataFrame(rows)[['description','owner','due_date','execution_status','Deadline status','dispatch_status']])
            selected_id=st.selectbox("Action detail",[a['action_id'] for a in shown],format_func=lambda aid:next(a['description'] for a in shown if a['action_id']==aid)); action=store.get(selected_id)
            st.subheader(action['description'])
            a,b,c=st.columns(3)
            metric(a,"Business status",STATUS_LABELS.get(action['execution_status'],action['execution_status']),"Recorded lifecycle state")
            metric(b,"Owner",action['owner'] or "Unassigned",f"Deadline: {action['due_date'] or 'Not set'}")
            metric(c,"Approval state",STATUS_LABELS.get(action['approval_state'],action['approval_state']),"Recorded approval decision")
            if action['execution_status']=='complete': st.success("Completed · business follow-through is recorded.")
            elif action['execution_status']=='blocked': st.warning("Blocked · review the action rationale and resolve the constraint before proceeding.")
            elif action['execution_status']=='proposed': st.info("Awaiting approval · assignment automation is not authorized yet.")
            st.write("**Action rationale**")
            st.write(action['rationale'] or "No rationale recorded.")
            st.caption(f"Action ID: {selected_id} · Reporting week: {action['reporting_week']} · Dataset: {action['dataset_version']}")
            if selected_id in {a['action_id'] for a in store.overdue(reference_date)}: st.warning("Overdue as of the selected reporting week.")
            options=sorted(__import__('founderos.actions',fromlist=['VALID']).VALID[action['execution_status']])
            if options:
                target=st.selectbox("Update business status",options,format_func=lambda x:STATUS_LABELS.get(x,x))
                note=st.text_input("Completion / change note")
                if st.button("Apply status change"):
                    try: store.transition(selected_id,target,note); st.rerun()
                    except ValueError as e: st.error(str(e))
            events=store.event_for_action(selected_id)
            if events:
                event=events[0]; st.subheader("Assignment automation")
                st.write(f"**{STATUS_LABELS.get(event['status'],event['status'])}** · Attempts: {event['attempt_count']}")
                if event['status'] in ['failed','retry_scheduled']: st.warning("Assignment delivery failed. Review the result before retrying.")
                elif event['status']=='dispatched': st.success("Assignment dispatched. Business completion is tracked separately above.")
                st.caption("Delivery status is separate from business completion. This demo uses a local mock receiver.")
                if event['result_detail']: st.caption(event['result_detail'])
                if event['status'] in ['pending','retry_scheduled'] and st.button("Dispatch assignment / retry"):
                    result=dispatch_event(store,event,MockNotificationReceiver()); st.success(f"Workflow {result['status']}: {result['event_id']}"); st.rerun()
                st.write("**Workflow execution history**"); table(pd.DataFrame(store.executions(event['event_id'])))
            st.subheader("Business action history"); table(pd.DataFrame(store.history(selected_id)))
            overdue=store.overdue(reference_date)
            if overdue: st.warning(f"{len(overdue)} open action(s) are overdue as of the selected reporting date.")
elif page=="Workflow Monitor":
    title("Workflow Monitor","Whether approved decisions are being assigned, followed through and reviewed.")
    store=action_store(); summary=store.workflow_summary(str(pd.Timestamp(week).date())); cols=st.columns(5)
    for col,(label,value) in zip(cols,[("Awaiting dispatch",summary['awaiting_dispatch']),("Assignments dispatched",summary['dispatched']),("Retries needed",summary['failed']),("Overdue actions",summary['overdue']),("Completed actions",summary['completed'])]): metric(col,label,str(value))
    st.subheader("Overdue action review")
    reference=st.date_input("Reference date",value=pd.Timestamp(week).date(),key="overdue_reference")
    if st.button("Prepare and dispatch overdue review"):
        event=store.create_overdue_digest_event(str(reference)); result=dispatch_event(store,event,MockNotificationReceiver()); st.success(f"Overdue review {result['status']}.")
    st.subheader("Workflow event log"); table(pd.DataFrame(store._all_events()).drop(columns=['payload_json','idempotency_key'],errors='ignore'))
else:
    title('Data Uploads','Download departmental templates, validate reports and review confirmed imports.')
    st.caption('Confirmed Excel imports persist locally across browser sessions. Canonical CSVs and the action database remain intact. Corrections restate reports for the active revision; saved revisions remain inspectable.')
    for report in REPORTS: reporting_section(report,data,reporting_store())
    st.subheader('Import history'); import_history(reporting_store())
    with st.expander('CSV reporting · existing format'):
        st.caption('Existing CSV formats remain supported. New IDs append and existing IDs update complete rows. Omitted records are preserved; imports are validated and persisted with the same safeguards as Excel.')
        dataset=st.selectbox('Dataset',list(REQUIRED_COLUMNS)); upload=st.file_uploader('Upload a CSV replacement',type='csv')
        st.caption('Required columns: '+', '.join(REQUIRED_COLUMNS[dataset]))
        if upload:
            try:
                frame=pd.read_csv(upload)
                if set(frame.columns)!=set(REQUIRED_COLUMNS[dataset]): st.error('Use exactly the required columns shown above.')
                else:
                    frame.index=range(2,len(frame)+2)
                    report=next(name for name,sheets in REPORTS.items() if dataset in sheets.values())
                    plan=prepare_frames({dataset:frame},report,data,filename=upload.name)
                    if plan.errors: st.dataframe(pd.DataFrame(plan.errors),hide_index=True,width='stretch')
                    else:
                        st.success(f'Validated {len(frame):,} records.'); st.dataframe(plan.changes,hide_index=True,width='stretch'); table(plan.frames[dataset].head(20))
                        if st.button('Confirm CSV import',disabled=plan.changes.empty or plan.changes.Operation.eq('Unchanged').all()):
                            reporting_store().commit(plan,confirmed=True); st.session_state['reporting_notice']='CSV report imported; dashboard recalculated.'; st.rerun()
            except Exception as exc: st.error('Cannot read CSV: '+str(exc))
    st.subheader('Restore demonstration data')
    st.caption('Restores operational reporting data only. Existing actions, their dataset associations, action audit history and import history are preserved.')
    confirmed=st.checkbox('I confirm restoring the original demonstration reporting dataset.')
    if st.button('Restore canonical demonstration data',disabled=not confirmed): reset_data(); st.session_state['reporting_notice']='Original demonstration reporting data restored.'; st.rerun()
