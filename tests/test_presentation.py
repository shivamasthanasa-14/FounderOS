import pandas as pd
from founderos.analytics import load_data, weekly_snapshot
from founderos.config import DATA_DIR
from founderos.dashboard import overview
from founderos.presentation import comparison, display_rate, rate_available, priority_components, readable_table, trend_for_display

def test_denominator_states_do_not_change_engine_values():
    data=load_data(DATA_DIR); week=pd.Timestamp('2026-09-21')
    snapshot=weekly_snapshot(data,week)
    assert not rate_available(data,week,snapshot,'win')
    assert display_rate(snapshot['sales']['win_rate'],False)=='N/A'
    assert snapshot['sales']['win_rate']==0
    snapshot['support']['tickets_resolved']=0
    assert not rate_available(data,week,snapshot,'sla')
    snapshot['operations']['milestones_due']=0
    assert not rate_available(data,week,snapshot,'milestone')
    assert display_rate(float('nan'),True)=='N/A'

def test_comparison_units_and_business_direction():
    assert comparison(.7,.6,'pp')==('↑ 10.0 pp vs prior week',True)
    assert comparison(84,73,'tickets',higher_better=False)[1] is False
    assert comparison(.8,.7,'pp',higher_better=None)[1] is None
    assert comparison(1,1)[1] is None
    assert comparison(1,0,available=False)==('No comparable prior week',None)

def test_priority_contributions_match_published_engine_factors():
    data=load_data(DATA_DIR); alert=overview(data,pd.Timestamp('2026-09-21'))['alerts'][0]
    components=priority_components(alert)
    assert components.Maximum.tolist()==[35,30,20,15]
    assert abs(components.Contribution.sum()-alert['priority_score']) <= 1

def test_trends_respect_cutoff_and_tables_preserve_records():
    data=load_data(DATA_DIR); week=pd.Timestamp('2026-07-20')
    frame=trend_for_display(data,week)
    assert frame.week.max()==week
    original=pd.DataFrame([{'action_id':'ACT-1','execution_status':'complete','dispatch_status':'pending'}])
    display=readable_table(original)
    assert display.iloc[0].to_dict()=={'Action ID':'ACT-1','Business status':'Completed','Automation status':'Automation pending'}
    assert original.execution_status.iloc[0]=='complete'

def test_navigation_week_and_action_controls_use_isolated_records(tmp_path, monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from founderos.actions import ActionStore
    from founderos import config
    monkeypatch.setattr(config,'ROOT',tmp_path)
    store=ActionStore(tmp_path/'data'/'founderos_actions.db')
    action=store.propose('Temporary UI validation','Verify controls','CS-01','2026-09-28',3,'test-version','2026-09-21')
    app=AppTest.from_file(Path(__file__).parents[1]/'app.py').run(timeout=30)
    first_week=app.selectbox(key='reporting_week').options[0]
    app.selectbox(key='reporting_week').select(first_week).run(timeout=30)
    app.radio(key='nav_Decision Intelligence').set_value('Action Center').run(timeout=30)
    assert not app.exception
    target=next(box for box in app.selectbox if box.label=='Update business status')
    target.set_value('approved')
    next(button for button in app.button if button.label=='Apply status change').click().run(timeout=30)
    assert not app.exception
    assert store.get(action['action_id'])['execution_status']=='approved'
    assert store.event_for_action(action['action_id'])[0]['status']=='pending'
    assert app.selectbox(key='reporting_week').value==pd.Timestamp('2026-07-06')
    app.radio(key='nav_Business Performance').set_value('Customer Support').run(timeout=30)
    assert not app.exception
    assert app.session_state['page']=='Customer Support'
    assert app.radio(key='nav_Decision Intelligence').value is None
