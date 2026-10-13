from io import BytesIO
from copy import deepcopy
import json
from pathlib import Path
import pandas as pd
import pytest
from pypdf import PdfReader
from founderos.analytics import load_data
from founderos.config import DATA_DIR
from founderos.actions import ActionStore
from founderos.evidence import dataset_version
from founderos.weekly_brief import (BriefStore,brief_context,generate_brief,deterministic_commentary,current_brief,export_html,export_markdown,export_pdf,report_sections,validate_narrative)

@pytest.fixture
def case(tmp_path):
    data=load_data(DATA_DIR); actions=ActionStore(tmp_path/'actions.db')
    context=brief_context(data,'2026-09-21','2026-08-01',actions)
    return data,actions,context

def test_brief_has_six_grounded_sections_and_compatible_periods(case):
    _,_,context=case; brief=generate_brief(context); sections=report_sections(brief)
    assert list(sections)==['Business Performance','What Changed','What Needs Attention','Possible Explanations','Questions for Management','Follow-Up From Last Week']
    assert brief['mode']=='Deterministic summary' and brief['model'] is None
    assert context['monthly']['revenue']==78878.47 and context['weekly']['open_tickets']==84
    assert context['financial_month']=='2026-08-01' and context['previous_week']=='2026-09-14'
    assert 3<=len(brief['narrative']['questions'])<=5

def test_commentary_persists_and_regeneration_requires_confirmation(tmp_path,case):
    _,_,context=case; store=BriefStore(tmp_path/'briefs.db'); first=store.save(generate_brief(context))
    text='Ask the support owner to verify the oldest cases before the review.'
    store.edit(first['brief_id'],text); loaded=BriefStore(store.path).latest('2026-09-21','2026-08-01')
    assert loaded['commentary']==text and loaded['human_edited']
    with pytest.raises(ValueError,match='replacing edited'): store.save(generate_brief(context))
    assert store.latest('2026-09-21','2026-08-01')['commentary']==text
    regenerated=store.save(generate_brief(context),replace_edited=True); assert not regenerated['human_edited']
    with store.connect() as c: assert c.execute('select count(*) from weekly_briefs').fetchone()[0]==2

def test_new_data_marks_brief_stale_without_deleting_human_edits(tmp_path,case):
    data,actions,context=case; store=BriefStore(tmp_path/'b.db'); brief=store.save(generate_brief(context)); store.edit(brief['brief_id'],'Preserve this human note.')
    changed=deepcopy(data); changed['support_tickets'].loc[0,'sla_hours']=1
    fresh=brief_context(changed,'2026-09-21','2026-08-01',actions)
    assert not current_brief(brief,fresh) and store.latest('2026-09-21','2026-08-01')['commentary']=='Preserve this human note.'
    assert not current_brief(brief,brief_context(data,'2026-09-14','2026-08-01',actions))

def model_response(context):
    return {'possible_explanations':[{'text':'Open support work may warrant a review of the unresolved case mix.','evidence_refs':['current.open_tickets','current.overdue_tickets']}], 'questions':[{'text':'Which open cases need an owner update?','evidence_refs':['current.open_tickets']},{'text':'What is blocking delayed customer projects?','evidence_refs':['current.delayed_projects']},{'text':'What explains the recorded cash movements?','evidence_refs':['monthly.closing_cash']}]}

def test_real_provider_adapter_boundary_with_test_double(case):
    _,_,context=case; seen=[]
    def provider(package,question,name,**kwargs):
        seen.append((package,question,name,kwargs)); return model_response(package)
    b=generate_brief(context,'ollama','test-double',invoke=provider)
    assert b['mode']=='Ollama commentary' and b['model']=='test-double'
    assert b['context']['monthly']['revenue']==context['monthly']['revenue']
    assert seen[0][0]['dataset_version']==context['dataset_version']
    assert seen[0][3]['schema']['additionalProperties'] is False

@pytest.mark.parametrize('text',['Revenue will increase next week.','Support was caused by delayed onboarding.','Support increased by 500 tickets.','A fifty percent gain is forecast.'])
def test_unsupported_model_claims_use_labeled_fallback(case,text):
    _,_,context=case; payload=model_response(context); payload['possible_explanations'][0]['text']=text
    b=generate_brief(context,'ollama',invoke=lambda *args,**kwargs:payload)
    assert b['mode']=='Deterministic summary' and 'rejected' in b['error']
    assert b['context']['monthly']['revenue']==78878.47

def test_unknown_evidence_and_model_unavailability(case):
    _,_,context=case; payload=model_response(context); payload['questions'][0]['evidence_refs']=['invented.metric']
    b=generate_brief(context,'ollama',invoke=lambda *args,**kwargs:payload); assert b['mode']=='Deterministic summary' and b['error']
    def unavailable(*args,**kwargs): raise ConnectionError('local service unavailable')
    b=generate_brief(context,'ollama',invoke=unavailable); assert b['mode']=='Deterministic summary' and 'unavailable' in b['error']

def test_exports_contain_verified_facts_and_escaped_human_commentary(case):
    _,_,context=case; brief=generate_brief(context); brief['commentary']='Management note: inspect the oldest cases. <script>alert(1)</script>'; brief['human_edited']=True
    html=export_html(brief); md=export_markdown(brief); pdf=export_pdf(brief); reader=PdfReader(BytesIO(pdf)); text='\n'.join(p.extract_text() for p in reader.pages)
    assert '<script>' not in html and '&lt;script&gt;' in html
    for export in [html,md,text]:
        assert '78,878.47' in export and '122,558.70' in export and '2026-09-21' in export
        assert 'inspect the oldest cases' in export and 'Questions for Management' in export
    assert len(reader.pages)>=2 and all(p.mediabox.width>500 for p in reader.pages)

def test_routine_followup_creation_completion_and_no_dispatch(tmp_path,case):
    data,store,context=case; version=dataset_version(data)
    task=store.create_followup('Check the oldest support cases','CS-01','2026-10-20',version,'2026-09-14')
    assert task['execution_status']=='in_progress' and not store.event_for_action(task['action_id'])
    original_version=task['dataset_version']; store.update_followup(task['action_id'],'complete','CS-01','2026-10-20','Owner confirmed review.')
    assert ActionStore(store.path).get(task['action_id'])['dataset_version']==original_version
    c=brief_context(data,'2026-09-21','2026-08-01',store); assert c['followups']['Completed'][0]['description']=='Check the oldest support cases'
    assert not current_brief(generate_brief(context),c)
    assert len(store.history(task['action_id']))==2 and not store.event_for_action(task['action_id'])

def test_brief_ui_edit_regenerate_and_export_guards(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from founderos import config
    monkeypatch.setattr(config,'ROOT',tmp_path)
    app=AppTest.from_file(Path(__file__).parents[1]/'app.py').run(timeout=30)
    app.radio(key='nav_Administration').set_value('Weekly Business Brief').run(timeout=30)
    next(b for b in app.button if b.label=='Generate Weekly Brief').click().run(timeout=30)
    assert not app.exception
    area=next(a for a in app.text_area if a.label=='Edit explanatory commentary')
    area.set_value('Human note preserved through reruns.').run(timeout=30)
    store=BriefStore(tmp_path/'data'/'weekly_briefs.db'); brief=store.latest('2026-09-21','2026-08-01')
    assert brief['human_edited'] and brief['commentary']=='Human note preserved through reruns.'
    next(b for b in app.button if b.label=='Generate Weekly Brief').click().run(timeout=30)
    assert store.latest('2026-09-21','2026-08-01')['brief_id']==brief['brief_id']
    app.checkbox(key='brief_replace_edits').check().run(timeout=30)
    next(b for b in app.button if b.label=='Generate Weekly Brief').click().run(timeout=30)
    assert not app.exception and store.latest('2026-09-21','2026-08-01')['brief_id']!=brief['brief_id']
