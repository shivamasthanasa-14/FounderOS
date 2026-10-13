"""Traceable issue detection with dynamic, interpretable priority scores."""
from __future__ import annotations
import hashlib, json
from .analytics import weekly_snapshot

def _score(impact, urgency, deterioration, confidence):
    """Weighted 0–100 priority. Inputs are each 0–1 and visible in every alert."""
    factors={"business_impact":round(impact,2),"urgency":round(urgency,2),"trend_deterioration":round(deterioration,2),"evidence_confidence":round(confidence,2)}
    return round(100*(.35*impact+.30*urgency+.20*deterioration+.15*confidence)), factors

def _alert(kind,title,area,severity,week,evidence,recommendation,factors):
    score, scoring=_score(**factors)
    fingerprint=hashlib.sha1(json.dumps({"kind":kind,"week":str(week),"evidence":evidence},sort_keys=True,default=str).encode()).hexdigest()[:10]
    return {"alert_id":kind,"occurrence_id":f"{kind}:{week:%Y%m%d}:{fingerprint}","title":title,"area":area,"severity":severity,"priority_score":score,"scoring_factors":scoring,"evidence":evidence,"recommendation":recommendation}

def detect_alerts(data, current_week, previous_week):
    now=weekly_snapshot(data,current_week); prev=weekly_snapshot(data,previous_week); a=[]
    s,ps=now["support"],prev["support"]
    if s["backlog"] >= 10 and s["backlog"] > ps["backlog"]:
        growth=(s["backlog"]-ps["backlog"])/max(ps["backlog"],1)
        a.append(_alert("support_backlog","Support backlog is increasing","Support","high",current_week,{"current_backlog":s["backlog"],"previous_backlog":ps["backlog"],"sla_adherence":s["sla_adherence"]},"Review aged tickets and reallocate Customer Success capacity this week.",{"impact":min(1,s["backlog"]/75),"urgency":min(1,(1-s["sla_adherence"])+.2),"deterioration":min(1,growth*3),"confidence":.95}))
    o,po=now["operations"],prev["operations"]
    if o["overdue_milestones"] >= 3 and o["cs_capacity_utilization"] >= .85:
        a.append(_alert("implementation_capacity","Implementation delivery is constrained","Operations","high",current_week,{"overdue_milestones":o["overdue_milestones"],"cs_utilization":o["cs_capacity_utilization"],"milestone_completion_rate":o["milestone_completion_rate"]},"Prioritize go-live milestones, then rebalance implementation work before accepting additional complex onboardings.",{"impact":min(1,o["overdue_milestones"]/10),"urgency":min(1,(1-o["milestone_completion_rate"])+.15),"deterioration":min(1,max(0,o["overdue_milestones"]-po["overdue_milestones"])/5),"confidence":.90}))
    r,pr=now["revenue"],prev["revenue"]
    if r["gross_revenue_churn"] > .025 or (r["net_revenue_retention"] < .98 and pr["net_revenue_retention"] < 1):
        a.append(_alert("retention_risk","Retention pressure is reducing recurring revenue","Revenue","high",current_week,{"gross_revenue_churn":r["gross_revenue_churn"],"nrr":r["net_revenue_retention"],"net_new_mrr":r["net_new_mrr"]},"Create recovery plans for accounts with recent contractions or churn and review the customer-risk drivers.",{"impact":min(1,r["gross_revenue_churn"]/.08),"urgency":min(1,(1-r["net_revenue_retention"])*10),"deterioration":min(1,max(0,pr["net_revenue_retention"]-r["net_revenue_retention"])*10),"confidence":.98}))
    sales, p_sales=now["sales"],prev["sales"]
    if sales["lead_to_qualified_conversion"] < .45 and sales["leads"] > p_sales["leads"]:
        a.append(_alert("lead_quality","Lead volume and lead quality are moving in opposite directions","Sales","medium",current_week,{"leads":sales["leads"],"previous_leads":p_sales["leads"],"qualified_conversion":sales["lead_to_qualified_conversion"]},"Review channel mix and tighten qualification criteria before increasing top-of-funnel spend.",{"impact":min(1,(.45-sales["lead_to_qualified_conversion"])/.45),"urgency":.50,"deterioration":min(1,(sales["leads"]-p_sales["leads"])/max(p_sales["leads"],1)*3),"confidence":.80}))
    # Contradiction: capacity is high while delivery still slips.
    if o["cs_capacity_utilization"] >= .85 and o["milestone_completion_rate"] < .70:
        a.append(_alert("capacity_delivery_contradiction","High implementation effort is not translating into completed milestones","Operations","high",current_week,{"cs_utilization":o["cs_capacity_utilization"],"milestone_completion_rate":o["milestone_completion_rate"]},"Investigate work mix and blockers; high utilization coincides with delays but does not prove it caused them.",{"impact":min(1,(.70-o["milestone_completion_rate"])/.70),"urgency":min(1,o["cs_capacity_utilization"]),"deterioration":min(1,max(0,po["milestone_completion_rate"]-o["milestone_completion_rate"])*2),"confidence":.75}))
    return sorted(a,key=lambda x:x["priority_score"],reverse=True)
