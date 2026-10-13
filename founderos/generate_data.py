"""Deterministically generate the coherent RelayOps operating dataset."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .config import DATA_DIR, SEED, START_DATE, WEEKS


def week_dates() -> pd.DatetimeIndex:
    return pd.date_range(START_DATE, periods=WEEKS, freq="W-MON")


def generate(output_dir: Path = DATA_DIR, seed: int = SEED) -> dict[str, pd.DataFrame]:
    """Create all data files. Same seed always produces the same records."""
    rng = np.random.default_rng(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    weeks = week_dates()
    customer_ids = [f"CUS-{i:03d}" for i in range(1, 97)]
    segments = rng.choice(["SMB", "Mid-market"], 96, p=[.68, .32])
    plan = rng.choice(["Starter", "Growth", "Scale"], 96, p=[.35, .47, .18])
    base_mrr = {"Starter": 450, "Growth": 900, "Scale": 1800}
    customers = pd.DataFrame({
        "customer_id": customer_ids,
        "company_name": [f"Relay customer {i:03d}" for i in range(1, 97)],
        "segment": segments, "plan": plan,
        "owner": rng.choice(["CS-01", "CS-02", "CS-03"], 96),
        "created_at": [weeks[0] - pd.Timedelta(days=int(x)) for x in rng.integers(15, 730, 96)],
    })
    # First 80 entered before the reporting window; the last 16 are new wins.
    customers.loc[80:, "created_at"] = [weeks[int(i // 2)] + pd.Timedelta(days=int(i % 5)) for i in range(16)]
    customers.to_csv(output_dir / "customers.csv", index=False)

    events = []
    for i, row in customers.iterrows():
        cid, amount = row.customer_id, base_mrr[row.plan]
        if i < 80:
            events.append([f"SUB-{len(events)+1:04d}", cid, weeks[0] - pd.Timedelta(days=1), "opening", amount, amount, "Opening subscription"])
        else:
            start = row.created_at.normalize()
            events.append([f"SUB-{len(events)+1:04d}", cid, start, "new", 0, amount, "New customer contract"])
    # Intentional, realistic signal: elevated contraction/churn in weeks 9-12.
    for idx, kind, factor, wk in [(4,"expansion",1.35,3),(15,"expansion",1.25,5),(23,"contraction",.70,8),(31,"churn",0,9),(44,"contraction",.60,10),(52,"churn",0,11),(67,"contraction",.70,11)]:
        row = customers.iloc[idx]; before = base_mrr[row.plan]
        # Account for prior expansion on customer 5 only.
        if idx == 4: before = base_mrr[row.plan]
        after = round(before * factor, 2)
        events.append([f"SUB-{len(events)+1:04d}", row.customer_id, weeks[wk] + pd.Timedelta(days=2), kind, before, after, f"{kind.title()} event"])
    subscriptions = pd.DataFrame(events, columns=["event_id","customer_id","event_date","event_type","mrr_before","mrr_after","reason"])
    subscriptions.to_csv(output_dir / "subscription_events.csv", index=False)

    lead_rows, opp_rows, stage_events = [], [], []
    for wi, week in enumerate(weeks):
        n = 18 + (3 if wi >= 9 else 0)
        for j in range(n):
            lid = f"LED-{wi+1:02d}-{j+1:03d}"; created = week + pd.Timedelta(days=int(rng.integers(0, 7)))
            qualified = rng.random() < (.48 if wi < 8 else .38)
            lead_rows.append([lid, created, rng.choice(["Inbound","Partner","Outbound"], p=[.50,.20,.30]), "qualified" if qualified else "disqualified"])
            if qualified:
                oid = f"OPP-{wi+1:02d}-{j+1:03d}"; stage = rng.choice(["discovery","proposal","won","lost"], p=[.33,.27,.22,.18])
                # Recent slowdown: more early-stage opportunities and longer cycles.
                if wi >= 9: stage = rng.choice(["discovery","proposal","won","lost"], p=[.52,.27,.10,.11])
                value = int(rng.choice([450,900,1800]) * rng.choice([6,12]))
                close = created + pd.Timedelta(days=int(rng.integers(8, 35))) if stage in ["won","lost"] else pd.NaT
                opp_rows.append([oid,lid,created,stage,value,close])
                # Lifecycle events make historical pipeline reconstruction possible.
                stage_events.append([f"OST-{len(stage_events)+1:04d}",oid,created,"discovery",value])
                if stage in ["proposal","won","lost"]:
                    proposal_date = created + pd.Timedelta(days=int(rng.integers(3, 10)))
                    stage_events.append([f"OST-{len(stage_events)+1:04d}",oid,proposal_date,"proposal",value])
                if stage in ["won","lost"]:
                    stage_events.append([f"OST-{len(stage_events)+1:04d}",oid,close,stage,value])
    leads = pd.DataFrame(lead_rows, columns=["lead_id","created_at","source","status"])
    opportunities = pd.DataFrame(opp_rows, columns=["opportunity_id","lead_id","created_at","stage","pipeline_value","closed_at"])
    leads.to_csv(output_dir / "leads.csv", index=False); opportunities.to_csv(output_dir / "opportunities.csv", index=False)
    pd.DataFrame(stage_events, columns=["stage_event_id","opportunity_id","event_date","stage","pipeline_value"]).to_csv(output_dir / "opportunity_stage_events.csv", index=False)

    ticket_rows=[]; ticket_id=1
    for wi, week in enumerate(weeks):
        n = 28 + (10 if wi >= 9 else 0)
        for _ in range(n):
            created = week + pd.Timedelta(days=int(rng.integers(0,7)), hours=int(rng.integers(0,10)))
            priority = rng.choice(["low","medium","high"], p=[.25,.55,.20])
            # Recent pressure means some remain open and a slower response.
            open_prob = .12 if wi < 9 else .35
            is_open = rng.random() < open_prob
            hrs = int(rng.integers(5, 35) if wi < 9 else rng.integers(18, 80))
            resolved = pd.NaT if is_open else created + pd.Timedelta(hours=hrs)
            sla = 24 if priority == "high" else 48
            ticket_rows.append([f"TIC-{ticket_id:04d}",rng.choice(customer_ids[:90]),created,priority,"open" if is_open else "resolved",resolved,sla,"Product issue" if rng.random()<.45 else "How-to"]); ticket_id += 1
    tickets = pd.DataFrame(ticket_rows, columns=["ticket_id","customer_id","created_at","priority","status","resolved_at","sla_hours","category"])
    tickets.to_csv(output_dir / "support_tickets.csv", index=False)

    projects=[]; milestones=[]; mid=1
    new_customer_ids = customers.iloc[80:].customer_id.tolist()
    for pi, cid in enumerate(new_customer_ids):
        start = customers.loc[customers.customer_id.eq(cid),"created_at"].iloc[0].normalize(); pid=f"IMP-{pi+1:03d}"
        projects.append([pid,cid,start, start+pd.Timedelta(days=30),"active" if pi>2 else "complete", rng.choice(["CS-01","CS-02","CS-03"])])
        for name, offset in [("Kickoff",3),("Configuration",12),("Training",22),("Go-live",30)]:
            due=start+pd.Timedelta(days=offset); completed = due-pd.Timedelta(days=int(rng.integers(0,3)))
            if pi >= 10 and name in ["Training","Go-live"]: completed = pd.NaT
            milestones.append([f"MS-{mid:03d}",pid,name,due,completed,"complete" if pd.notna(completed) else "open"]); mid += 1
    pd.DataFrame(projects,columns=["project_id","customer_id","start_date","target_go_live","status","owner"]).to_csv(output_dir / "implementation_projects.csv",index=False)
    pd.DataFrame(milestones,columns=["milestone_id","project_id","milestone","due_date","completed_at","status"]).to_csv(output_dir / "implementation_milestones.csv",index=False)

    team = pd.DataFrame([
        ("CEO-01","Management","CEO",40),("OPS-01","Management","Founder Associate",40),("FIN-01","Management","Finance",40),
        ("SAL-01","Sales","AE",40),("SAL-02","Sales","AE",40),("SAL-03","Sales","SDR",40),
        ("CS-01","Customer Success","Implementation Manager",40),("CS-02","Customer Success","Implementation Manager",40),("CS-03","Customer Success","CSM",40),("SUP-01","Customer Success","Support",40),("SUP-02","Customer Success","Support",40),
        ("PM-01","Product","Product Manager",40),("PD-01","Product","Designer",40),("ENG-01","Engineering","Engineer",40),("ENG-02","Engineering","Engineer",40),("ENG-03","Engineering","Engineer",40),("ENG-04","Engineering","Engineer",40),("ENG-05","Engineering","Engineer",40),("ENG-06","Engineering","Engineer",40),("ENG-07","Engineering","Engineer",40),
    ], columns=["employee_id","function","role","weekly_capacity_hours"])
    team.to_csv(output_dir / "team.csv",index=False)
    workloads=[]
    for wi, week in enumerate(weeks):
        for _, member in team.iterrows():
            base={"Sales":.76,"Customer Success":.78,"Product":.72,"Engineering":.77,"Management":.70}[member.function]
            overload = .16 if wi>=9 and member.function=="Customer Success" else 0
            hours=round(member.weekly_capacity_hours*(base+overload+rng.normal(0,.05)),1)
            workloads.append([week,member.employee_id,member.function,max(0,hours),member.weekly_capacity_hours])
    pd.DataFrame(workloads,columns=["week_start","employee_id","function","allocated_hours","capacity_hours"]).to_csv(output_dir / "team_capacity.csv",index=False)
    from .analytics import load_data
    from .business import demo_finance
    finance=demo_finance(load_data(output_dir)); finance.to_csv(output_dir/'financial_entries.csv',index=False)
    return {"customers":customers,"subscriptions":subscriptions,"leads":leads,"opportunities":opportunities,"tickets":tickets,"projects":pd.DataFrame(projects),"milestones":pd.DataFrame(milestones),"team":team,"capacity":pd.DataFrame(workloads),"financial_entries":finance}


if __name__ == "__main__":
    generated = generate()
    print("Generated:", ", ".join(f"{key}={len(value)}" for key, value in generated.items()))
