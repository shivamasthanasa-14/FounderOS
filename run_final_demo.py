"""Reproducible real-workbook and report-export demonstrations, isolated from live tasks."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import pandas as pd
from founderos.config import ROOT, DATA_DIR
from founderos.analytics import load_data
from founderos.reporting import ReportingStore, REPORTS, REPORT_LABELS, prepare_import, apply_frames, template_bytes
from founderos.business import demo_finance, weekly_business, monthly_view, simple_issues, related_accounts
from founderos.weekly_brief import BriefStore, brief_context, generate_brief, export_pdf, export_html, export_markdown
from founderos.actions import ActionStore
from run_reporting_demo import populated, create_reports

def scenario_workbooks(data):
    # Reuse the validated sales fixture, adding the related financial journal
    # changes so the new subscription remains coherent with the posted month.
    old=create_reports(data)
    plan=prepare_import(old['scenario_a_sales.xlsx'],'Revenue & Sales',data)
    candidate=apply_frames(data,plan.frames); finance=demo_finance(candidate)
    originals=data['financial_entries'].set_index('entry_id')
    changed=finance[finance.apply(lambda r:r.entry_id not in originals.index or abs(r.amount-originals.loc[r.entry_id,'amount'])>.005,axis=1)]
    sheets={sheet:plan.frames[name].to_dict('records') for sheet,name in REPORTS['Revenue & Sales'].items()}
    sheets['Financial Entries']=changed.to_dict('records')
    sales=populated('Revenue & Sales',data,sheets)
    support=[{'ticket_id':f'FINAL-SUPPORT-{i:02d}','customer_id':'CUS-091','created_at':pd.Timestamp('2026-09-21'),'priority':'high','status':'open','resolved_at':None,'sla_hours':24,'category':'Product issue'} for i in range(25)]
    return {'new_reporting.xlsx':sales,'support_deterioration.xlsx':populated('Customer Support',data,{'Tickets':support}),'invalid_report.xlsx':old['scenario_c_invalid.xlsx']}

def main():
    data=load_data(DATA_DIR); folder=ROOT/'final_demo_reports'; folder.mkdir(exist_ok=True)
    for name,report in REPORTS.items(): (ROOT/'templates'/(REPORT_LABELS[name].replace(' & ','_').replace(' ','_')+'_Reporting.xlsx')).write_bytes(template_bytes(name,data))
    workbooks=scenario_workbooks(data)
    for filename,content in workbooks.items(): (folder/filename).write_bytes(content)
    with TemporaryDirectory(prefix='founderos-final-demo-') as temporary:
        working=ReportingStore(Path(temporary)/'reporting.db',DATA_DIR); actions=ActionStore(Path(temporary)/'actions.db'); briefs=BriefStore(Path(temporary)/'briefs.db')
        initial=weekly_business(data,'2026-09-21'); result={'initial':initial}
        for filename,report in [('new_reporting.xlsx','Revenue & Sales'),('support_deterioration.xlsx','Customer Support')]:
            current=working.load(); plan=prepare_import(workbooks[filename],report,current,filename); assert not plan.errors,plan.errors
            working.commit(plan,confirmed=True); result[filename]={'changes':plan.changes.to_dict('records'),'weekly':weekly_business(working.load(),'2026-09-21')}
        now=working.load(); assert weekly_business(now,'2026-09-21')['new_customers']==initial['new_customers']+1
        assert weekly_business(now,'2026-09-21')['open_tickets']==initial['open_tickets']+25
        assert related_accounts(now,'2026-09-21')['shared_open_tickets']==25
        result['relationship']=related_accounts(now,'2026-09-21'); result['issues']=simple_issues(now,'2026-09-21')
        context=brief_context(now,'2026-09-21','2026-08-01',actions); saved=briefs.save(generate_brief(context)); saved=briefs.edit(saved['brief_id'],'Management review note: ask the support owner to review the overdue cases for the delayed onboarding account. This shared account requires investigation; it does not prove causation.')
        export=ROOT/'output'/'pdf'; export.mkdir(parents=True,exist_ok=True)
        (export/'RelayOps_Weekly_Brief.pdf').write_bytes(export_pdf(saved)); (export/'RelayOps_Weekly_Brief.html').write_text(export_html(saved),encoding='utf-8'); (export/'RelayOps_Weekly_Brief.md').write_text(export_markdown(saved),encoding='utf-8')
        task=actions.create_followup('Review the shared support and onboarding account','CS-01','2026-10-20',context['dataset_version'],context['reporting_week']); actions.update_followup(task['action_id'],'complete','CS-01','2026-10-20','Completed in isolated verification.')
        result['brief']={'mode':saved['mode'],'edited':saved['human_edited'],'exported':['PDF','HTML','Markdown'],'data_version':context['dataset_version']}
        result['followup']={'business_status':actions.get(task['action_id'])['execution_status'],'history_count':len(actions.history(task['action_id'])),'notification_events':len(actions.event_for_action(task['action_id'])),'isolated_database':True}
        result['finance']=monthly_view(now,'2026-08-01','2026-09-21')[0]; result['import_history_count']=len(working.history())
        (ROOT/'local-validation'/'final-redesign'/'scenario-results.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
        # ActionStore is the existing service. Release its short-lived SQLite
        # connection objects before Windows removes the isolated demo directory.
        import gc; gc.collect()
    print('Real workbook imports, changed business metrics/issues, edited brief exports and isolated follow-up completion verified.')

if __name__=='__main__': main()
