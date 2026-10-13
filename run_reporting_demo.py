"""Exercise real Excel parsing, transactions and KPI changes in an isolated workspace."""
from io import BytesIO
from pathlib import Path
import json
import tempfile
import pandas as pd
from openpyxl import load_workbook
from founderos.analytics import load_data
from founderos.config import DATA_DIR, ROOT
from founderos.reporting import template_bytes, prepare_import, ReportingStore
from founderos.periods import metric_values
from founderos.dashboard import overview
from founderos.evidence import dataset_version

def populated(report,data,rows):
    wb=load_workbook(BytesIO(template_bytes(report,data)))
    for sheet,records in rows.items():
        columns=[c.value for c in wb[sheet][1]]
        for record in records:
            wb[sheet].append([None if pd.isna(record.get(c)) else record[c].to_pydatetime() if isinstance(record[c],pd.Timestamp) else record[c] for c in columns])
    out=BytesIO(); wb.save(out); return out.getvalue()

def create_reports(data):
    at=pd.Timestamp('2026-09-21')
    sales={'Customers':[dict(customer_id='REVIEW-CUS',company_name='Reporting demonstration account',segment='SMB',plan='Growth',owner='CS-01',created_at=at)],
           'Subscription Events':[dict(event_id='REVIEW-SUB',customer_id='REVIEW-CUS',event_date=at,event_type='new',mrr_before=0,mrr_after=900,reason='New synthetic subscription')],
           'Leads':[dict(lead_id='REVIEW-LEAD',created_at=at,source='Inbound',status='qualified')],
           'Opportunities':[dict(opportunity_id='REVIEW-OPP',lead_id='REVIEW-LEAD',created_at=at,stage='discovery',pipeline_value=10800,closed_at=None)],
           'Opportunity Stage Events':[dict(stage_event_id='REVIEW-STAGE',opportunity_id='REVIEW-OPP',event_date=at,stage='discovery',pipeline_value=10800)]}
    support=[dict(ticket_id=f'REVIEW-TICKET-{i:02d}',customer_id='CUS-001',created_at=at,priority='high',status='open',resolved_at=None,sla_hours=24,category='Product issue') for i in range(25)]
    invalid=[dict(support[0],customer_id='UNKNOWN-CUSTOMER'),dict(support[0],resolved_at=at-pd.Timedelta(days=1),status='resolved')]
    return {'scenario_a_sales.xlsx':populated('Revenue & Sales',data,sales),'scenario_b_support.xlsx':populated('Customer Support',data,{'Tickets':support}),'scenario_c_invalid.xlsx':populated('Customer Support',data,{'Tickets':invalid})}

def main():
    data=load_data(DATA_DIR); output=ROOT/'demo_reports'; output.mkdir(exist_ok=True); files=create_reports(data)
    for name,content in files.items(): (output/name).write_bytes(content)
    with tempfile.TemporaryDirectory(prefix='founderos-report-demo-') as temp:
        store=ReportingStore(Path(temp)/'reporting.db',DATA_DIR); week=pd.Timestamp('2026-09-21'); original=metric_values(data,week)
        plan=prepare_import(files['scenario_a_sales.xlsx'],'Revenue & Sales',store.load(),'scenario_a_sales.xlsx'); assert not plan.errors,plan.errors; store.commit(plan,confirmed=True)
        a=metric_values(store.load(),week); assert a['mrr']==original['mrr']+900 and a['active']==original['active']+1 and a['pipeline']==original['pipeline']+10800
        plan=prepare_import(files['scenario_b_support.xlsx'],'Customer Support',store.load(),'scenario_b_support.xlsx'); assert not plan.errors,plan.errors; store.commit(plan,confirmed=True)
        b=metric_values(store.load(),week); assert b['tickets']==original['tickets']+25 and b['backlog']==original['backlog']+25 and b['breaches']==original['breaches']+25
        before=dataset_version(store.load()); plan=prepare_import(files['scenario_c_invalid.xlsx'],'Customer Support',store.load(),'scenario_c_invalid.xlsx'); assert plan.errors
        try: store.commit(plan,confirmed=True)
        except ValueError: pass
        else: raise AssertionError('Invalid report was accepted')
        assert dataset_version(store.load())==before and len(store.history())==2
        result={'scenario_a':{'before':original,'after':a},'scenario_b':{'after':b,'alerts':overview(store.load(),week)['alerts']},'scenario_c':{'errors':plan.errors,'atomic_rejection':True},'history':store.history(),'historical_week_unchanged':metric_values(store.load(),'2026-09-14')['mrr']==metric_values(data,'2026-09-14')['mrr']}
        folder=ROOT/'local-validation'/'assignment-06a'; folder.mkdir(parents=True,exist_ok=True); (folder/'scenario-results.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
        print('A: MRR +900 EUR, customers +1, pipeline +10,800 EUR. B: new/open/SLA-breaching tickets +25. C: rejected atomically. Import history: 2 records. Historical MRR unchanged.')

if __name__=='__main__': main()
