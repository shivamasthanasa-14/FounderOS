"""Streamlit views for the existing Chief of Staff page."""
import os
import pandas as pd
import streamlit as st
from .decision_service import analyse, decision_brief, approve_decision, recent_analysis
from .presentation import EVIDENCE_LABELS
from .dashboard import format_eur, format_percent

def fact_table(facts):
    rows=[]
    percent_keys={'sla_adherence','milestone_completion_rate','capacity_utilization','cs_capacity_utilization','gross_revenue_churn','net_revenue_retention','lead_to_qualified_conversion','win_rate'}
    for fact in facts:
        key=fact['id'].split('.')[-1]
        label={'cs_capacity_utilization':'Customer Success utilization','mrr':'Recurring revenue (MRR)','tickets_resolved':'Resolved support tickets','milestones_due':'Milestones due this week','ticket_volume':'Incoming support tickets'}.get(key,EVIDENCE_LABELS.get(key,key.replace('_',' ').title()))
        value=format_percent(fact['value']) if key in percent_keys else format_eur(fact['value']) if key in ['mrr','net_new_mrr','pipeline_value'] else f"{fact['value']:,.0f}"
        if not fact.get('available',True): value='N/A · no denominator'
        rows.append({'Metric':label,'Value':value,'Reporting week':fact['period'],'Evidence ID':fact['id']})
    return pd.DataFrame(rows)

def display_evidence(analysis):
    st.subheader('Verified facts · Python')
    st.dataframe(fact_table(analysis.context['facts']),hide_index=True,width='stretch',height=260)
    st.caption('Rates use the unchanged analytical engine. Zero-denominator rates are not reliable; check the supporting counts and evidence limitations.')
    with st.expander('Source records and evidence limitations'):
        st.caption('Only a bounded sample is supplied to the model. No customer names or employee names are sent.')
        for warning in analysis.context['warnings']: st.write('• '+warning)
        st.dataframe(pd.DataFrame(analysis.context['evidence_references']),hide_index=True,width='stretch')
    st.subheader('Interpretation · '+('AI model' if analysis.mode in ['ollama','hosted'] else 'Offline template'))
    st.caption('Interpretation is provisional. Valid evidence references do not prove causation or confirm that an intervention is feasible.')
    st.write(analysis.payload['interpretation'])
    for item in analysis.payload['observations']:
        st.markdown('**'+('Model-proposed ' if analysis.mode in ['ollama','hosted'] else '')+item['kind'].title()+'** — '+item['text'])
        st.caption('Evidence: '+', '.join(item['evidence_refs']))
    for label,key in [('Missing evidence','missing_information'),('Further investigations','further_investigations')]:
        with st.expander(label):
            for item in analysis.payload[key]: st.write('• '+item)

def render_workspace(data,week,alerts,store_factory):
    st.caption('Investigate → Compare Options → Challenge Assumptions → Prepare Decision')
    st.info('Python verifies the numbers. The model suggests interpretations. You choose and approve decisions. Assignment dispatch remains a separate authorized step in Action Center.')
    if not alerts:
        st.success('No operational alert is available for this reporting week. Select a week with an issue to investigate.')
        return
    chosen=st.selectbox('Focus issue',alerts,format_func=lambda a:a['title'],key='decision_issue')
    with st.expander('Model and analysis context'):
        provider=st.selectbox('Analysis provider',['deterministic','ollama','hosted'],index=['deterministic','ollama','hosted'].index(os.getenv('FOUNDEROS_AI_PROVIDER','deterministic')) if os.getenv('FOUNDEROS_AI_PROVIDER','deterministic') in ['deterministic','ollama','hosted'] else 0,format_func=lambda value:{'deterministic':'Offline evidence preview · no model inference','ollama':'Local Ollama · genuine inference','hosted':'Configured hosted provider'}[value],key='decision_provider')
        model=st.text_input('Local model',os.getenv('OLLAMA_MODEL','qwen3:1.7b'),key='decision_model')
        st.caption('Ollama must already be installed and the model downloaded. Selecting a model here does not install anything. Hosted mode sends only bounded evidence to your configured endpoint.')
        if st.button('Resume saved analysis'):
            saved=recent_analysis(store_factory(),data,week,chosen,provider,model)
            if saved:
                run_id,result=saved
                st.session_state.decision_analysis=result
                st.session_state.decision_run=run_id
                st.session_state.decision_constraints=result.constraints
                st.session_state.decision_challenge=result.challenge
                st.session_state.decision_step='Challenge Assumptions' if result.challenge else 'Investigate'
                st.session_state.pop('decision_draft',None)
                st.session_state.pop('decision_confirmed',None)
                st.rerun()
            else: st.info('No valid saved analysis matches this issue, week, dataset, provider and model.')
    constraints=st.text_area('Management constraints or new information',placeholder='For example: We cannot hire additional employees this quarter.',height=90,max_chars=1500,key='decision_constraints')
    st.caption('This is user-provided context, not a verified business fact. Apply it by running an investigation or challenge.')
    state=st.session_state.get('decision_analysis')
    evidence_current=bool(state and state.current(data,week,chosen))
    fresh=bool(state and state.current(data,week,chosen) and state.constraints==constraints and state.mode==provider and state.model==model)
    # Offline results have an explicit mode label; they remain usable for manual review.
    if provider=='deterministic' and state:
        fresh=state.current(data,week,chosen) and state.constraints==constraints and state.model==model and state.mode=='offline evidence preview'
    if state and not fresh:
        st.warning('Analysis or management context changed. Apply current constraints through Investigate or Reconsider analysis before approving. If the issue, dataset, week or provider changed, investigate again.')
    if state and state.error: st.warning(state.error)
    if fresh:
        st.caption(f"Analysis mode: {state.mode} · Model: {state.model if provider!='deterministic' else 'none'} · Reporting week: {state.context['reporting_week']} · Dataset: {state.context['dataset_version']}")
        if state.mode=='offline evidence preview': st.warning('No accepted model analysis is available. Interpretations and options below are manual planning templates.')
    def run_stage(stage,challenge='',option=''):
        try:
            with st.spinner('Reviewing bounded evidence'+(' with the local model…' if provider=='ollama' else '…')):
                result=analyse(data,week,chosen,stage,constraints,challenge,state if evidence_current and stage!='investigate' else None,option,provider,model)
            st.session_state.decision_analysis=result
            st.session_state.decision_run=store_factory().save_ai_run(result)
            st.session_state.pop('decision_confirmed',None)
            st.session_state.pop('decision_draft',None)
            st.rerun()
        except (ValueError,KeyError) as exc: st.error(str(exc))
    step=st.radio('Decision workflow',['Investigate','Compare Options','Challenge Assumptions','Prepare Decision'],horizontal=True,key='decision_step')
    if step=='Investigate':
        st.subheader('Investigate the selected issue')
        if st.button('Investigate evidence',type='primary'): run_stage('investigate')
        if fresh:
            st.caption(f"Mode: {state.mode} · Model: {state.model if provider!='deterministic' else 'none'} · Week: {state.context['reporting_week']} · Dataset: {state.context['dataset_version']}")
            display_evidence(state)
    elif not fresh and not (step=='Challenge Assumptions' and evidence_current):
        st.info('Start in Investigate and review current evidence before continuing.')
    elif step=='Compare Options':
        st.subheader('Compare practical interventions')
        if state.selected_option: st.info('Deeper evaluation: '+state.payload['interpretation'])
        if state.mode=='offline evidence preview': st.warning('These are manual planning templates. They were not generated or evaluated by an AI model.')
        for option in state.payload['options']:
            with st.container(border=True):
                st.subheader(option['title'])
                for label,key in [('Intervention','intervention'),('Why it might work','mechanism'),('Resources','resources'),('Trade-offs','tradeoffs'),('Operational risks','risks'),('Assumptions to validate','assumptions')]: st.write('**'+label+'** · '+option[key])
                st.caption('Supporting evidence: '+', '.join(option['evidence_refs']))
                st.caption('Success indicators to monitor: '+', '.join(option['success_indicators']))
        selected=st.selectbox('Option for deeper evaluation',[o['id'] for o in state.payload['options']],format_func=lambda oid:next(o['title'] for o in state.payload['options'] if o['id']==oid),key='decision_option')
        if st.button('Evaluate selected option',disabled=provider=='deterministic'): run_stage('evaluate',option=selected)
    elif step=='Challenge Assumptions':
        st.subheader('Challenge the interpretation')
        st.caption('Ask for counterevidence, alternative causes, feasibility under a constraint, or information that would change the recommendation.')
        challenge=st.text_area('Your challenge',placeholder='What evidence contradicts this explanation? Could dependencies explain the delays?',max_chars=1500,height=90,key='decision_challenge')
        if st.button('Reconsider analysis',type='primary',disabled=not challenge.strip() or provider=='deterministic'): run_stage('challenge',challenge,st.session_state.get('decision_option',''))
        if state.challenge:
            detail=state.payload.get('challenge_evaluation')
            if detail:
                st.write('**Counterevidence and evidential limits**'); st.write(detail['counter_evidence']['text'])
                st.caption('Evidence: '+', '.join(detail['counter_evidence']['evidence_refs']))
                st.write('**Unsupported assumptions**')
                for assumption in detail['unsupported_assumptions']: st.write('• '+assumption)
                st.write('**Information that would change the recommendation**'); st.write(detail['what_would_change_recommendation'])
            st.write('**Model response to the challenge**'); st.write(state.payload['challenge_response'])
            st.write('**How constraints change the options**'); st.write(state.payload['constraint_response'])
            for option in state.payload['options']: st.write('**'+option['title']+'** · '+option['tradeoffs'])
    else:
        st.subheader('Prepare a human management decision')
        selected=st.selectbox('Preferred intervention',[o['id'] for o in state.payload['options']],format_func=lambda oid:next(o['title'] for o in state.payload['options'] if o['id']==oid),key='decision_preferred')
        brief=decision_brief(state,selected)
        st.write('**Observed problem** · '+brief['Observed problem'])
        st.write('**Supporting facts**'); st.dataframe(fact_table(brief['Supporting facts']),hide_index=True,width='stretch',height=200)
        st.write('**Possible explanations**')
        for observation in brief['Possible explanations']: st.write(observation['kind'].title()+': '+observation['text'])
        st.write('**Available interventions** · '+ '; '.join(option['title'] for option in brief['Available intervention options']))
        st.write('**Trade-offs** · '+brief['Trade-offs'])
        st.write('**Unresolved questions**')
        for question in brief['Unresolved questions']: st.write('• '+question)
        st.write('**Suggested success indicators** · '+', '.join(brief['Suggested success indicators']))
        st.warning(brief['Human decision required'])
        # Key draft to evidence + option, so old edits cannot silently attach to a different decision.
        draft_key=state.context['context_id']+selected+state.constraints+state.payload['interpretation']
        if st.session_state.get('decision_draft')!=draft_key:
            st.session_state.decision_draft=draft_key
            st.session_state.decision_intervention=brief['Preferred intervention']['intervention']
            st.session_state.decision_confirmed=False
        description=st.text_area('Edit the chosen intervention',key='decision_intervention',max_chars=2000)
        a,b=st.columns(2)
        owner=a.text_input('Accountable owner',key='decision_owner')
        due=b.date_input('Review deadline',value=pd.Timestamp(week).date()+pd.Timedelta(days=7),key='decision_due')
        priority=st.slider('Action priority',1,5,4,key='decision_priority')
        confirmed=st.checkbox('I have reviewed the evidence, constraints, intervention, owner and deadline. I approve this action.',key='decision_confirmed')
        if st.button('Approve and create action',type='primary',disabled=not confirmed or not owner.strip() or not description.strip()):
            try:
                action=approve_decision(store_factory(),state,data,week,chosen,selected,description,owner,str(due),priority,confirmed)
                st.success(f"Approved {action['action_id']}. Track it in Action Center. Assignment has not been dispatched.")
            except ValueError as exc: st.error(str(exc))
