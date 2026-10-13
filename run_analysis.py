from founderos.config import DATA_DIR
from founderos.analytics import load_data, weekly_snapshot
from founderos.alerts import detect_alerts
import pandas as pd

data=load_data(DATA_DIR); weeks=sorted(data["team_capacity"].week_start.unique()); current=pd.Timestamp(weeks[-1]); previous=pd.Timestamp(weeks[-2])
print("Current week:",current.date()); print(weekly_snapshot(data,current)); print("\nPrioritized alerts:")
for alert in detect_alerts(data,current,previous): print(f"{alert['priority_score']} | {alert['title']} | {alert['evidence']}")
