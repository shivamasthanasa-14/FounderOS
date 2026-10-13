# Primary metric definitions

Headline cards include tooltips explaining meaning, relevance and calculation. Weekly comparisons default to the previous week; financial comparisons to the previous completed month. Future events are excluded. Unavailable values and zero-denominator rates show N/A.

| Metric | Calculation |
|---|---|
| Monthly Revenue | Recognized service journal entries, checked against calendar-time subscription accrual. |
| Cash in Bank | Closing statement reconciled to opening + receipts − payments. |
| Gross Margin | (Revenue − direct service costs) / revenue; excludes other operating payments. |
| Active Customers | Positive latest dated subscription balance at cutoff. |
| New Customers | First-ever paid activation during the week. |
| Customers Lost / Customer Churn | Opening paying customers cancelled this week and unpaid at cutoff; rate divides by opening base. |
| New Sales Leads | Leads created during the selected week. |
| Opportunities | Deals linked to that lead cohort and created by cutoff. |
| Deals Won / Lost | Linked opportunities with the respective latest dated stage by cutoff. |
| Leads Reaching an Opportunity | Unique cohort leads with an opportunity / all cohort leads. |
| Closed-deal Win Rate | Won / (won + lost), N/A without closures. |
| New Support Tickets | Created within the week. |
| Tickets Resolved | Resolution timestamps within the week. |
| Open Tickets | Created before cutoff and unresolved then. |
| Overdue Tickets | Open and beyond opening timestamp + SLA hours. |
| Active Onboardings | Started projects with required tasks still incomplete. |
| Completed Onboardings | Final required task completed within the week. |
| Delayed Projects | Active with an overdue target or required task. |
| Overdue Tasks | Required tasks past due and incomplete at cutoff. |

Advanced MRR is the recurring contract balance at cutoff. Net New MRR = new + expansion − contraction − cancellation movements. It is not earned revenue or cash. The cohort funnel counts unique leads while deal cards count actual opportunities. Capacity remains optional, not executive headline information. Existing calculations remain in analytics.py and periods.py. See business_assumptions.md for limitations.
