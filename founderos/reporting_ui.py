"""Compact, real reporting upload / preview / confirmation controls."""
import hashlib
import json
import pandas as pd
import streamlit as st
from .reporting import REPORTS, REPORT_LABELS, template_bytes, prepare_import, prepare_frames
from .periods import METRICS, MODES, compare_metrics, metric_values, support_records, delivery_records
from .dashboard import reporting_weeks, format_eur, format_percent
from .evidence import dataset_version
from .presentation import readable_table

@st.cache_data(show_spinner=False)
def downloadable_template(report,data):
    return template_bytes(report,data)

def reporting_section(report,data,store):
    label=REPORT_LABELS[report]
    with st.expander('Reporting data · '+label):
        st.caption('Download the template, complete its data sheets, then validate and preview. Existing IDs update complete rows; new IDs append. Omitted rows are preserved.')
        st.download_button('Download Template',downloadable_template(report,data),file_name=label.replace(' & ','_').replace(' ','_')+'_Reporting.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='download_'+report)
        upload=st.file_uploader('Upload '+label+' Excel report',type=['xlsx'],key='xlsx_'+report)
        prefix='import_'+report
        if upload:
            content=upload.getvalue(); signature=hashlib.sha256(content).hexdigest()+dataset_version(data)
            if st.button('Validate Report',key='validate_'+report):
                st.session_state[prefix]=(signature,prepare_import(content,report,data,upload.name))
            saved=st.session_state.get(prefix)
            if saved and saved[0]==signature:
                plan=saved[1]
                if plan.errors:
                    st.error('Report rejected. Correct these rows and validate again. No records have changed.')
                    st.dataframe(pd.DataFrame(plan.errors),hide_index=True,width='stretch')
                else:
                    counts=plan.changes.Operation.value_counts().to_dict() if not plan.changes.empty else {}
                    st.success(f"Validated: {counts.get('Append',0)} new, {counts.get('Update',0)} changed, {counts.get('Unchanged',0)} unchanged records.")
                    st.dataframe(plan.changes,hide_index=True,width='stretch')
                    for name,frame in plan.frames.items():
                        if len(frame):
                            st.caption(name.replace('_',' ').title()+' · submitted rows')
                            st.dataframe(readable_table(frame.head(30)),hide_index=True,width='stretch')
                    st.caption('Corrections restate the current dataset, including historical reports. Prior imported revisions remain available in Data Management. Review dates and event history before confirming.')
                    left,right=st.columns(2)
                    if left.button('Confirm Import',type='primary',key='confirm_'+report,disabled=not counts.get('Append',0) and not counts.get('Update',0)):
                        try:
                            version=store.commit(plan,confirmed=True); st.session_state[prefix]=None; st.session_state['reporting_notice']='Report imported. Dashboard recalculated · dataset '+version; st.session_state.pop('working_data',None); st.rerun()
                        except ValueError as exc: st.error(str(exc))
                    if right.button('Cancel preview',key='cancel_'+report): st.session_state.pop(prefix,None); st.rerun()
            elif saved: st.info('Workbook or reporting data changed. Validate again to refresh the preview.')

def comparison_controls(data,week):
    mode=st.selectbox('Compare with',MODES,key='comparison_mode')
    selected=None
    if mode==MODES[3]:
        prior=[w for w in reporting_weeks(data) if w<pd.Timestamp(week)]
        if prior: selected=st.selectbox('Historical comparison week',prior,index=len(prior)-1,format_func=lambda w:pd.Timestamp(w).strftime('%d %b %Y'),key='comparison_selected')
        else: st.info('No earlier reporting week is available.')
    rows,dates=compare_metrics(data,week,mode,selected)
    label=' / '.join(pd.Timestamp(w).strftime('%d %b') for w in dates) if dates else 'unavailable · insufficient history'
    st.caption('Comparison: '+label+'. Weekly flows compare weekly activity; stocks compare ending balances. Four-week averages require all four calendar weeks and valid denominators.')
    return {row['key']:row for row in rows}

def formatted(value,unit):
    if value is None or pd.isna(value): return 'N/A'
    return format_eur(value) if unit=='eur' else format_percent(value) if unit=='rate' else f'{value:,.1f} {unit}' if unit in ['hours','days'] else f'{value:,.1f}'.removesuffix('.0')

def cards(keys,comparisons,metric):
    for start in range(0,len(keys),3):
        for col,key in zip(st.columns(3),keys[start:start+3]):
            row=comparisons[key]; unit=row['unit']; d=row['Change']
            delta='Comparison unavailable' if d is None else ('+' if d>0 else '')+(f'{d*100:.1f} pp' if unit=='rate' else formatted(d,unit))
            relative=row['Relative change']
            note=f"Comparison {formatted(row['Comparison'],unit)} · {delta}"+(f' ({relative:+.1%})' if relative is not None else '')+' · '+row['Movement']
            metric(col,row['Metric'],formatted(row['Current'],unit),note,True if row['Movement']=='Favorable' else False if row['Movement']=='Unfavorable' else None)

def explanations(keys):
    with st.expander('KPI definitions · calculation and interpretation'):
        for key in keys:
            label,*_=METRICS[key]
            st.markdown('**'+label+'**'); st.write(METRICS[key][-1]); st.caption('Period convention: '+METRICS[key][-2]+'. Four-week comparison uses the arithmetic mean of four weekly values, including ending stocks and weekly ratios.')

def import_history(store):
    history=store.history()
    if not history: st.info('No confirmed Excel reports yet.'); return
    rows=[]
    for row in history:
        operations=json.loads(row['summary_json']); counts={op:sum(x['Operation']==op for x in operations) for op in ['Append','Update']}
        rows.append({'Revision':row['id'],'Imported at (UTC)':row['imported_at'],'Report':row['report'],'Workbook':row['filename'],'New records':counts['Append'],'Updated records':counts['Update'],'Dataset':row['version']})
    st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
    selected=st.selectbox('Inspect a saved reporting revision',[r['id'] for r in history])
    if st.button('Inspect revision data'):
        old=store.revision(selected); st.caption('Read-only saved revision; active dashboard data is unchanged.')
        for name,frame in old.items():
            with st.expander(name.replace('_',' ').title()): st.dataframe(frame,hide_index=True,width='stretch')

def account_investigation(data,week):
    with st.expander('Account investigation · support and delivery evidence'):
        tickets=support_records(data,week); projects,milestones=delivery_records(data,week)
        ids=sorted(set(tickets.customer_id)|set(projects.loc[projects.overdue.gt(0),'customer_id']))
        if not ids: st.info('No open support or overdue delivery account is available.'); return
        selected=st.selectbox('Investigate customer',ids)
        st.caption('Records at the selected cutoff. A shared customer ID enables investigation; co-occurrence does not establish a common cause.')
        from .presentation import readable_table
        st.write('Open support cases'); st.dataframe(readable_table(tickets[tickets.customer_id.eq(selected)]),hide_index=True,width='stretch')
        affected=projects[projects.customer_id.eq(selected)]
        st.write('Implementation projects'); st.dataframe(readable_table(affected),hide_index=True,width='stretch')
        st.write('Milestone commitments'); st.dataframe(readable_table(milestones[milestones.project_id.isin(affected.project_id)]),hide_index=True,width='stretch')
