"""Durable outbox dispatchers; n8n can call the same payload contracts."""
from __future__ import annotations
import json, urllib.request
from collections import defaultdict

class MockNotificationReceiver:
 def __init__(self,fail=False): self.fail=fail; self.received=[]
 def send(self,payload):
  if self.fail: raise RuntimeError("Mock receiver rejected the notification.")
  self.received.append(payload); return {"receipt_id":f"MOCK-{len(self.received):03d}"}

def assignment_message(payload):
 return {"type":"founderos_assignment","action_id":payload["action_id"],"owner":payload["owner"],"subject":f"RelayOps action: {payload['description']}","body":f"You have an approved priority-{payload['priority']} action due {payload['due_date']}. Context: {payload['rationale']}","idempotency_key":payload.get("idempotency_key")}

def dispatch_event(store,event,receiver=None,n8n_webhook=None):
 if event["status"]=="dispatched": return {"status":"suppressed_duplicate","event_id":event["event_id"]}
 payload=json.loads(event["payload_json"]); payload["idempotency_key"]=event["idempotency_key"]
 try:
  message=assignment_message(payload) if event["event_type"]=="approved_action_dispatch" else {"type":"founderos_overdue_digest",**payload,"idempotency_key":event["idempotency_key"]}
  if n8n_webhook:
   request=urllib.request.Request(n8n_webhook,data=json.dumps(message).encode(),headers={"Content-Type":"application/json","Idempotency-Key":event["idempotency_key"]},method="POST")
   with urllib.request.urlopen(request,timeout=10) as r: result=r.read().decode()
   destination="n8n_webhook"
  elif receiver:
   result=receiver.send(message); destination="mock_receiver"
  else: raise RuntimeError("No dispatch destination configured.")
  store.record_execution(event["event_id"],destination,"dispatched",json.dumps(result)); return {"status":"dispatched","event_id":event["event_id"],"message":message}
 except Exception as exc:
  store.record_execution(event["event_id"],"n8n_webhook" if n8n_webhook else "mock_receiver","failed",str(exc)); return {"status":"failed","event_id":event["event_id"],"error":str(exc)}

def dispatch_pending(store,receiver=None,n8n_webhook=None): return [dispatch_event(store,e,receiver,n8n_webhook) for e in store.pending_events()]
