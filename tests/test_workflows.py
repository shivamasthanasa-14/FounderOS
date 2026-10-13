from founderos.actions import ActionStore
from founderos.workflows import MockNotificationReceiver, dispatch_event, dispatch_pending

def approved(store, due='2026-09-20', description='Triage support backlog'):
    a=store.propose(description,'Evidence','CS-01',due,4,'version-a','2026-09-14','alert-a',[])
    return store.transition(a['action_id'],'approved')

def test_approval_creates_durable_event(tmp_path):
    s=ActionStore(tmp_path/'workflow.db'); a=approved(s); events=s.event_for_action(a['action_id'])
    assert len(events)==1 and events[0]['status']=='pending' and events[0]['idempotency_key']

def test_unapproved_dispatch_blocked(tmp_path):
    s=ActionStore(tmp_path/'workflow.db'); a=s.propose('Unapproved','Evidence','CS-01','2026-09-20',4,'v','2026-09-14')
    import pytest
    with pytest.raises(ValueError): s.create_dispatch_event(a['action_id'])

def test_idempotency_and_notification_suppression(tmp_path):
    s=ActionStore(tmp_path/'workflow.db'); a=approved(s); event=s.event_for_action(a['action_id'])[0]; receiver=MockNotificationReceiver()
    assert dispatch_event(s,event,receiver)['status']=='dispatched'
    assert dispatch_event(s,s.event_for_action(a['action_id'])[0],receiver)['status']=='suppressed_duplicate'
    assert len(receiver.received)==1 and s.get(a['action_id'])['execution_status']=='approved'

def test_failure_persists_and_retries(tmp_path):
    s=ActionStore(tmp_path/'workflow.db'); a=approved(s); e=s.event_for_action(a['action_id'])[0]
    assert dispatch_event(s,e,MockNotificationReceiver(fail=True))['status']=='failed'
    retry=s.event_for_action(a['action_id'])[0]; assert retry['status']=='retry_scheduled' and retry['attempt_count']==1
    assert dispatch_event(s,retry,MockNotificationReceiver())['status']=='dispatched'

def test_overdue_digest_and_completed_exclusion(tmp_path):
    s=ActionStore(tmp_path/'workflow.db'); a=approved(s,'2026-07-01'); done=approved(s,'2026-07-02','Close completed ticket run'); s.transition(done['action_id'],'in_progress'); s.transition(done['action_id'],'complete')
    digest=s.create_overdue_digest_event('2026-07-08'); assert a['action_id'] in digest['payload_json'] and done['action_id'] not in digest['payload_json']
    assert dispatch_event(s,digest,MockNotificationReceiver())['status']=='dispatched'

def test_dataset_version_preserved_in_event(tmp_path):
    s=ActionStore(tmp_path/'workflow.db'); a=approved(s); e=s.event_for_action(a['action_id'])[0]
    assert 'version-a' in e['payload_json']
