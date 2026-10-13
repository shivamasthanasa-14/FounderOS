"""Small SQLite action system with explicit state transitions and audit history."""
from __future__ import annotations
import sqlite3, hashlib, json, uuid
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, date, timezone

VALID={"proposed":{"approved","rejected","deferred"},"approved":{"in_progress","blocked","deferred"},"in_progress":{"blocked","complete","deferred"},"blocked":{"in_progress","deferred"},"deferred":{"approved","in_progress"},"complete":{"in_progress"},"rejected":set()}
SCHEMA="""CREATE TABLE IF NOT EXISTS actions (action_id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE, source_alert TEXT, dataset_version TEXT NOT NULL, reporting_week TEXT NOT NULL, description TEXT NOT NULL, rationale TEXT, owner TEXT, due_date TEXT, priority INTEGER, approval_state TEXT NOT NULL, execution_status TEXT NOT NULL, completion_notes TEXT, evidence_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS action_history (id INTEGER PRIMARY KEY AUTOINCREMENT, action_id TEXT NOT NULL, event TEXT NOT NULL, note TEXT, occurred_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_runs (run_id TEXT PRIMARY KEY, dataset_version TEXT, reporting_week TEXT, mode TEXT, output_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS workflow_events (event_id TEXT PRIMARY KEY, action_id TEXT, event_type TEXT NOT NULL, idempotency_key TEXT UNIQUE NOT NULL, payload_json TEXT NOT NULL, status TEXT NOT NULL, attempt_count INTEGER NOT NULL DEFAULT 0, last_attempt_at TEXT, result_detail TEXT, created_at TEXT NOT NULL, completed_at TEXT);
CREATE TABLE IF NOT EXISTS workflow_executions (execution_id TEXT PRIMARY KEY, event_id TEXT NOT NULL, destination TEXT, status TEXT NOT NULL, attempt_number INTEGER NOT NULL, detail TEXT, occurred_at TEXT NOT NULL);"""
class ActionStore:
 def __init__(self,path): self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self.setup()
 def connect(self): return sqlite3.connect(self.path)
 def setup(self):
  with self.connect() as c: c.executescript(SCHEMA)
 def create_followup(self,description,owner,due_date,dataset_version,reporting_week):
  """Explicit user-created routine task, with no assignment outbox event."""
  if not description.strip() or not owner.strip(): raise ValueError('Enter a follow-up and accountable owner.')
  date.fromisoformat(str(due_date))
  fingerprint=hashlib.sha1(json.dumps([dataset_version,reporting_week,description.strip().lower()],sort_keys=True).encode()).hexdigest(); aid='ACT-'+fingerprint[:10].upper(); now=datetime.now(timezone.utc).isoformat()
  with self.connect() as c:
   try:
    c.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(aid,fingerprint,None,dataset_version,reporting_week,description.strip(),'Routine follow-up recorded explicitly by the user.',owner,str(due_date),3,'approved','in_progress',None,'[]',now,now))
    c.execute('INSERT INTO action_history(action_id,event,note,occurred_at) VALUES(?,?,?,?)',(aid,'in_progress','User recorded a routine follow-up; no assignment was dispatched.',now))
   except sqlite3.IntegrityError: raise ValueError('An equivalent follow-up already exists for this reporting period.')
  return self.get(aid)
 def update_followup(self,aid,status,owner,due_date,note=''):
  """Human task update; legacy decision transitions/dispatch remain separate."""
  if status not in ['in_progress','blocked','complete','deferred']: raise ValueError('Unknown follow-up status.')
  if not owner.strip(): raise ValueError('Choose an accountable owner.')
  date.fromisoformat(str(due_date)); action=self.get(aid)
  if not action: raise ValueError('Action not found.')
  now=datetime.now(timezone.utc).isoformat()
  with self.connect() as c:
   c.execute('UPDATE actions SET execution_status=?,approval_state=?,owner=?,due_date=?,completion_notes=?,updated_at=? WHERE action_id=?',(status,'approved',owner,str(due_date),note or action.get('completion_notes'),now,aid))
   c.execute('INSERT INTO action_history(action_id,event,note,occurred_at) VALUES(?,?,?,?)',(aid,status,note or 'Updated explicitly in Action Tracker.',now))
  return self.get(aid)
 def propose(self,description,rationale,owner,due_date,priority,dataset_version,reporting_week,source_alert=None,evidence=None):
  fingerprint=hashlib.sha1(json.dumps([dataset_version,reporting_week,description.strip().lower()],sort_keys=True).encode()).hexdigest(); now=datetime.now(timezone.utc).isoformat(); aid="ACT-"+fingerprint[:10].upper()
  with self.connect() as c:
   try: c.execute("INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(aid,fingerprint,source_alert,dataset_version,reporting_week,description,rationale,owner,due_date,priority,"proposed","proposed",None,json.dumps(evidence or []),now,now)); c.execute("INSERT INTO action_history(action_id,event,note,occurred_at) VALUES(?,?,?,?)",(aid,"proposed",None,now))
   except sqlite3.IntegrityError: raise ValueError("An equivalent action already exists for this dataset version and reporting week.")
  return self.get(aid)
 def get(self,aid):
  with self.connect() as c:
   c.row_factory=sqlite3.Row; row=c.execute("SELECT * FROM actions WHERE action_id=?",(aid,)).fetchone(); return dict(row) if row else None
 def list(self, dataset_version=None):
  q="SELECT * FROM actions"; p=[]
  if dataset_version: q+=" WHERE dataset_version=?"; p=[dataset_version]
  with self.connect() as c: c.row_factory=sqlite3.Row; return [dict(x) for x in c.execute(q+" ORDER BY updated_at DESC",p).fetchall()]
 def transition(self,aid,to_state,note=None,reference_date=None):
  action=self.get(aid)
  if not action: raise ValueError("Action not found.")
  current=action["execution_status"]
  if to_state not in VALID.get(current,set()): raise ValueError(f"Invalid transition from {current} to {to_state}.")
  now=datetime.now(timezone.utc).isoformat()
  with self.connect() as c:
   c.execute("UPDATE actions SET approval_state=?, execution_status=?, completion_notes=COALESCE(?,completion_notes), updated_at=? WHERE action_id=?",("approved" if to_state in ["approved","in_progress","blocked","complete"] else to_state,to_state,note,now,aid)); c.execute("INSERT INTO action_history(action_id,event,note,occurred_at) VALUES(?,?,?,?)",(aid,to_state,note,now))
  if to_state=="approved": self.create_dispatch_event(aid)
  return self.get(aid)
 def overdue(self,reference_date=None):
  ref=str(reference_date or date.today())
  return [x for x in self.list() if x["due_date"] and x["due_date"]<ref and x["execution_status"] in ["approved","in_progress","blocked"]]
 def history(self,aid):
  with self.connect() as c: c.row_factory=sqlite3.Row; return [dict(x) for x in c.execute("SELECT * FROM action_history WHERE action_id=? ORDER BY id",(aid,)).fetchall()]
 def save_ai_run(self,response):
  run_id="AIR-"+uuid.uuid4().hex[:10].upper(); now=datetime.now(timezone.utc).isoformat()
  with self.connect() as c: c.execute("INSERT INTO ai_runs VALUES (?,?,?,?,?,?)",(run_id,response.dataset_version,response.reporting_week,response.mode,json.dumps(asdict(response)),now))
  return run_id
 def create_dispatch_event(self,aid):
  action=self.get(aid)
  if not action or action["execution_status"] not in ["approved","in_progress","blocked","deferred"]: raise ValueError("Only an approved action can be dispatched.")
  key=hashlib.sha1(f"assignment:{aid}:{action['dataset_version']}".encode()).hexdigest(); now=datetime.now(timezone.utc).isoformat(); event_id="EVT-"+key[:12].upper(); payload={k:action[k] for k in ["action_id","description","owner","due_date","priority","dataset_version","reporting_week","rationale"]}
  with self.connect() as c:
   c.execute("INSERT OR IGNORE INTO workflow_events(event_id,action_id,event_type,idempotency_key,payload_json,status,created_at) VALUES(?,?,?,?,?,?,?)",(event_id,aid,"approved_action_dispatch",key,json.dumps(payload),"pending",now))
  return self.get_event_by_key(key)
 def get_event_by_key(self,key):
  with self.connect() as c: c.row_factory=sqlite3.Row; r=c.execute("SELECT * FROM workflow_events WHERE idempotency_key=?",(key,)).fetchone(); return dict(r) if r else None
 def event_for_action(self,aid):
  with self.connect() as c: c.row_factory=sqlite3.Row; return [dict(x) for x in c.execute("SELECT * FROM workflow_events WHERE action_id=? ORDER BY created_at DESC",(aid,)).fetchall()]
 def pending_events(self):
  with self.connect() as c: c.row_factory=sqlite3.Row; return [dict(x) for x in c.execute("SELECT * FROM workflow_events WHERE status IN ('pending','retry_scheduled') ORDER BY created_at").fetchall()]
 def record_execution(self,event_id,destination,status,detail=None):
  now=datetime.now(timezone.utc).isoformat(); execution_id="WFX-"+uuid.uuid4().hex[:12].upper()
  with self.connect() as c:
   event=c.execute("SELECT attempt_count FROM workflow_events WHERE event_id=?",(event_id,)).fetchone()
   if not event: raise ValueError("Workflow event not found.")
   attempt=event[0]+1; final="dispatched" if status=="dispatched" else "retry_scheduled"
   c.execute("UPDATE workflow_events SET status=?,attempt_count=?,last_attempt_at=?,result_detail=?,completed_at=? WHERE event_id=?",(final,attempt,now,detail,now if status=="dispatched" else None,event_id)); c.execute("INSERT INTO workflow_executions VALUES(?,?,?,?,?,?,?)",(execution_id,event_id,destination,status,attempt,detail,now))
  return execution_id
 def workflow_summary(self,reference_date=None):
  events=self.pending_events(); all_actions=self.list(); return {"awaiting_dispatch":len(events),"dispatched":sum(1 for x in self._all_events() if x['status']=="dispatched"),"failed":sum(1 for x in self._all_events() if x['status']=="retry_scheduled"),"overdue":len(self.overdue(reference_date)),"completed":sum(1 for x in all_actions if x['execution_status']=="complete")}
 def _all_events(self):
  with self.connect() as c: c.row_factory=sqlite3.Row; return [dict(x) for x in c.execute("SELECT * FROM workflow_events").fetchall()]
 def executions(self,event_id):
  with self.connect() as c: c.row_factory=sqlite3.Row; return [dict(x) for x in c.execute("SELECT * FROM workflow_executions WHERE event_id=? ORDER BY occurred_at",(event_id,)).fetchall()]
 def create_overdue_digest_event(self,reference_date):
  actions=self.overdue(reference_date); grouped={}
  for a in actions: grouped.setdefault(a['owner'] or 'Unassigned',[]).append(a['action_id'])
  key=hashlib.sha1(f"overdue_review:{reference_date}:{json.dumps(grouped,sort_keys=True)}".encode()).hexdigest(); now=datetime.now(timezone.utc).isoformat(); eid="EVT-"+key[:12].upper(); payload={"reference_date":str(reference_date),"overdue_by_owner":grouped}
  with self.connect() as c: c.execute("INSERT OR IGNORE INTO workflow_events(event_id,action_id,event_type,idempotency_key,payload_json,status,created_at) VALUES(?,?,?,?,?,?,?)",(eid,None,"overdue_action_review",key,json.dumps(payload),"pending",now))
  return self.get_event_by_key(key)
