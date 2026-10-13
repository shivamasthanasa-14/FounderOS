from copy import deepcopy
import json
import pandas as pd
import pytest
from founderos.analytics import load_data
from founderos.config import DATA_DIR
from founderos.dashboard import overview
from founderos.actions import ActionStore
from founderos.decision_service import build_context, offline_payload, validate_response, analyse, decision_brief, approve_decision, recent_analysis

@pytest.fixture
def case():
    data=load_data(DATA_DIR); week=pd.Timestamp('2026-09-21')
    alert=next(a for a in overview(data,week)['alerts'] if a['area']=='Support')
    return data,week,alert

def model_double(context,question,provider,**kwargs):
    payload=offline_payload(context)
    payload['interpretation']='Backlog and service pressure warrant targeted investigation; causes remain uncertain.'
    payload['challenge_response']='Ticket complexity and recurring categories could explain pressure; inspect these before attributing it to capacity.'
    payload['constraint_response']='Reassign existing work and investigate demand while preserving coverage; defer hiring-dependent choices.'
    if 'challenge_evaluation' in kwargs.get('schema',{}).get('properties',{}):
        detail={'counter_evidence':{'text':'Customer Success utilization challenges an underuse explanation.','kind':'correlation','evidence_refs':['current.operations.cs_capacity_utilization']},'unsupported_assumptions':['Reallocation feasibility has not been established.'],'what_would_change_recommendation':'Confirm the work mix and dependency status.','revised_conclusion':'Investigate blockers before attributing delays to unused capacity.','constraint_implications':'Use existing staff only; reprioritization can delay other work.'}
        return {'challenge_evaluation':detail,'options':payload['options']}
    return payload

def test_complete_investigation_to_explicit_decision(case,tmp_path):
    data,week,alert=case
    response=analyse(data,week,alert,provider='ollama',invoke=model_double)
    assert response.mode=='ollama' and not response.error
    brief=decision_brief(response,'option-1')
    assert brief['Observed problem']==alert['title'] and brief['Supporting facts']
    store=ActionStore(tmp_path/'actions.db')
    with pytest.raises(ValueError,match='approval'):
        approve_decision(store,response,data,week,alert,'option-1','Triage aged tickets','CS-01','2026-09-28',4)
    assert not store.list()
    action=approve_decision(store,response,data,week,alert,'option-1','Triage aged tickets','CS-01','2026-09-28',4,True)
    assert action['execution_status']=='approved'
    assert store.event_for_action(action['action_id'])[0]['status']=='pending'
    assert store.executions(store.event_for_action(action['action_id'])[0]['event_id'])==[]

def test_evidence_is_bounded_referenced_and_names_omitted(case):
    context=build_context(*case)
    assert len(context['records'])<=6
    assert {fact['period'] for fact in context['facts']}=={'2026-09-21','2026-09-14'}
    encoded=json.dumps(context)
    assert 'company_name' not in encoded and 'employee_id' not in encoded
    assert any(f['id']=='current.support.backlog' and f['value']==84 for f in context['facts'])

@pytest.mark.parametrize('bad_text',['This saves €5000','Failure probability is 90 percent','Capacity will double','Productivity improves 20%','This saves fifty hours'])
def test_unsupported_numeric_claims_rejected(case,bad_text):
    context=build_context(*case); payload=offline_payload(context); payload['options'][0]['mechanism']=bad_text
    with pytest.raises(ValueError,match='numerical'): validate_response(payload,context)

def test_observation_numbers_must_match_cited_python_facts(case):
    context=build_context(*case); payload=offline_payload(context)
    payload['observations']=[{'text':'Backlog increased from 73 to 84 tickets','kind':'observation','evidence_refs':['current.support.backlog','previous.support.backlog']}]
    validate_response(payload,context)
    payload['observations'][0]['text']='Backlog increased to 99 tickets'
    with pytest.raises(ValueError,match='number absent'): validate_response(payload,context)
    payload['observations'][0]['text']='SLA adherence is 84%'
    with pytest.raises(ValueError,match='number absent'): validate_response(payload,context)
    payload['observations'][0]['text']='Backlog will improve by 84 tickets'
    with pytest.raises(ValueError,match='forecast'): validate_response(payload,context)
    payload['observations'][0]={'text':'Backlog exceeds 84 tickets','kind':'observation','evidence_refs':['current.support.backlog']}
    with pytest.raises(ValueError,match='comparison contradicts'): validate_response(payload,context)

@pytest.mark.parametrize('mutation',['unknown_reference','duplicate_option','missing_option_field','extra_authority'])
def test_option_schema_and_authority(case,mutation):
    context=build_context(*case); payload=offline_payload(context)
    if mutation=='unknown_reference': payload['observations'][0]['evidence_refs']=['fabricated-record']
    elif mutation=='duplicate_option': payload['options'][1]['id']=payload['options'][0]['id']
    elif mutation=='missing_option_field': del payload['options'][0]['risks']
    else: payload['approve_action']=True
    with pytest.raises(Exception): validate_response(payload,context)

def test_model_unavailable_and_invalid_response_are_not_ai(case):
    def unavailable(*args,**kwargs): raise OSError('Local model not running')
    response=analyse(*case,provider='ollama',invoke=unavailable)
    assert response.mode=='offline evidence preview' and response.error
    response=analyse(*case,provider='ollama',invoke=lambda *args,**kwargs:{'interpretation':'incomplete'})
    assert response.mode=='offline evidence preview' and 'rejected' in response.error

def test_new_constraints_reach_model_with_prior_analysis(case):
    response=analyse(*case,provider='ollama',invoke=model_double)
    received=[]
    def reconsider(context,question,provider,**kwargs):
        received.append(question)
        payload=model_double(context,question,provider,**kwargs)
        payload['options'][0]['title']='Prioritize existing work under the staffing constraint'
        return payload
    revised=analyse(*case,stage='challenge',constraints='We cannot hire additional employees this quarter.',challenge='What other causes could explain this?',previous=response,provider='ollama',invoke=reconsider)
    assert 'cannot hire' in received[0] and 'prior_interpretation' in received[0]
    assert revised.payload['options'][0]['title']!=response.payload['options'][0]['title']
    assert revised.challenge and revised.constraints
    assert revised.payload['challenge_evaluation']['counter_evidence']['evidence_refs']
    assert revised.payload['interpretation']!=response.payload['interpretation']

def test_hiring_option_under_no_hiring_constraint_is_rejected(case):
    def invalid(context,*args,**kwargs):
        payload=model_double(context,*args,**kwargs)
        payload['options'][0]['intervention']='Hire additional support staff'
        return payload
    response=analyse(*case,constraints='We cannot hire additional employees this quarter.',provider='ollama',invoke=invalid)
    assert response.mode=='offline evidence preview' and 'no-hiring' in response.error

def test_unmeasured_cause_is_rejected_in_revised_conclusion(case):
    previous=analyse(*case,provider='ollama',invoke=model_double)
    def unsupported(context,question,provider,**kwargs):
        payload=model_double(context,question,provider,**kwargs)
        payload['challenge_evaluation']['revised_conclusion']='Delays are caused by project dependencies.'
        return payload
    response=analyse(*case,stage='challenge',challenge='Could dependencies explain delays?',previous=previous,provider='ollama',invoke=unsupported)
    assert response.mode=='offline evidence preview' and 'unverified cause' in response.error

def test_decision_ui_approval_boundary(tmp_path,monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from founderos import config
    monkeypatch.setattr(config,'ROOT',tmp_path)
    app=AppTest.from_file(Path(__file__).parents[1]/'app.py').run(timeout=40)
    app.radio(key='nav_Decision Intelligence').set_value('AI Chief of Staff').run(timeout=40)
    next(button for button in app.button if button.label=='Investigate evidence').click().run(timeout=40)
    assert not app.exception
    app.radio(key='decision_step').set_value('Prepare Decision').run(timeout=40)
    assert not app.exception
    button=next(button for button in app.button if button.label=='Approve and create action')
    assert button.disabled
    app.text_input(key='decision_owner').set_value('CS-01').run(timeout=40)
    assert next(button for button in app.button if button.label=='Approve and create action').disabled
    app.checkbox(key='decision_confirmed').check().run(timeout=40)
    next(button for button in app.button if button.label=='Approve and create action').click().run(timeout=40)
    assert not app.exception
    store=ActionStore(tmp_path/'data'/'founderos_actions.db')
    assert len(store.list())==1 and store.list()[0]['execution_status']=='approved'
    app.text_area(key='decision_constraints').set_value('We cannot hire this quarter.').run(timeout=40)
    assert not any(button.label=='Approve and create action' for button in app.button)

def test_dataset_change_blocks_action_and_reusing_analysis(case,tmp_path):
    response=analyse(*case,provider='ollama',invoke=model_double)
    data,week,alert=case; changed=deepcopy(data)
    changed['support_tickets'].loc[0,'category']='Updated evidence'
    assert not response.current(changed,week,alert)
    store=ActionStore(tmp_path/'actions.db')
    with pytest.raises(ValueError,match='stale'):
        approve_decision(store,response,changed,week,alert,'option-1','Investigate','CS-01','2026-09-28',3,True)
    assert not store.list()

def test_saved_analysis_resumes_only_for_matching_current_context(case,tmp_path):
    response=analyse(*case,provider='ollama',invoke=model_double)
    store=ActionStore(tmp_path/'actions.db'); run_id=store.save_ai_run(response)
    invalid=deepcopy(response); invalid.payload={'unauthorized_action':True}
    store.save_ai_run(invalid)
    saved=recent_analysis(store,*case,'ollama',response.model)
    assert saved[0]==run_id and saved[1].payload==response.payload
    assert recent_analysis(store,*case,'ollama','different-model') is None
    data,week,alert=case; changed=deepcopy(data)
    changed['support_tickets'].loc[0,'category']='Changed evidence'
    assert recent_analysis(store,changed,week,alert,'ollama',response.model) is None

def test_missing_data_blocks_inference(case):
    data,week,alert=case; incomplete=deepcopy(data); del incomplete['support_tickets']
    with pytest.raises(ValueError,match='Missing'): analyse(incomplete,week,alert,provider='ollama',invoke=model_double)

def test_undefined_rate_is_not_a_citable_numerical_fact(case):
    data,week,alert=case; changed=deepcopy(data)
    changed['support_tickets']['resolved_at']=pd.NaT
    alert=next(a for a in overview(changed,week)['alerts'] if a['area']=='Support')
    context=build_context(changed,week,alert)
    fact=next(f for f in context['facts'] if f['id']=='current.support.sla_adherence')
    assert fact['value']==0 and fact['available'] is False
    payload=offline_payload(context)
    payload['observations'][0]['evidence_refs']=['current.support.sla_adherence']
    with pytest.raises(Exception): validate_response(payload,context)

def test_conflicting_evidence_is_exposed(case):
    data,week,alert=case; changed=deepcopy(data)
    # A later open ticket can have an impossible future resolution that still lands in the evidence sample.
    ref=build_context(data,week,alert)['evidence_references'][0]['record_id']
    i=changed['support_tickets'].index[changed['support_tickets'].ticket_id.eq(ref)][0]
    changed['support_tickets'].loc[i,'created_at']=pd.Timestamp('2026-10-02')
    changed['support_tickets'].loc[i,'resolved_at']=pd.Timestamp('2026-10-01')
    # Missing chronology is surfaced on the selected dataset, independent of whether the row is in the sample.
    from founderos.dashboard import validate_upload
    _,errors=validate_upload('support_tickets',changed['support_tickets'],changed)
    assert any('precede' in error for error in errors)
    with pytest.raises(ValueError,match='Conflicting or invalid evidence'):
        analyse(changed,week,alert,provider='ollama',invoke=model_double)

def test_week_or_issue_change_is_stale(case):
    response=analyse(*case,provider='ollama',invoke=model_double)
    data,week,alert=case
    other=next(a for a in overview(data,week)['alerts'] if a['area']=='Operations')
    assert not response.current(data,week,other)
    assert not response.current(data,week-pd.Timedelta(days=7),alert)
