# Business and accounting assumptions

RelayOps and every supplied source record are synthetic. The financial journal covers July–September 2026. Existing operational CSVs were preserved; finance was added rather than renaming MRR.

Recognized service revenue accrues the dated recurring contract balance over elapsed calendar time in a month. Opening events carry the recorded opening balance back only to the beginning of that opening month. Monthly contract prices divide by the actual calendar-month duration. Changes prorate at event timestamps, with per-customer monthly amounts rounded to cents. This is a demonstration policy, not a comprehensive accounting standard implementation.

Opening bank cash is EUR 150,000 on June 30. Monthly receipts are 85% of current recognized revenue plus 15% of the preceding month, rounded per account. Direct service costs are hosting at 12% of revenue plus EUR 26,000 delivery payroll; both are paid in the month. Other payroll and operating payments are EUR 48,000 monthly. Closing bank statements equal opening cash plus receipts minus payments.

August revenue is EUR 78,878.47, direct costs EUR 35,465.42, gross service profit EUR 43,413.05, closing cash EUR 122,558.70 and gross margin 55.04%. Earned revenue, contract MRR, collections, profit and bank balances answer distinct questions. Gross margin excludes other operating payments. VAT, annual prepayments, refunds, depreciation, taxes, nonrecurring revenue and net-profit accounting are outside scope. Signed bank balances allow overdrafts; ordinary revenue/cost/receipt/payment entries must be nonnegative.

Financial month selection requires a closing statement and a calendar end before the reporting cutoff. Reconciliation errors invalidate affected values to N/A. Finance imports validate the whole candidate journal against subscription accrual and bank statements. Operational corrections can invalidate previously closed financial periods until corresponding journal corrections arrive.

Paying customers have positive latest dated subscription balances. New customers are first-ever paid activations, excluding returning accounts. Churn counts opening paying customers cancelled this week and unpaid at cutoff, divided by the opening paying base for the rate.

The sales funnel uses one created-week lead cohort and linked opportunities with dated stage history. Deal counts count opportunities; nested funnel stages deduplicate leads. Undated qualification status is excluded. Won deals cannot be equated to paid customers without a supplied deal-to-contract link.

Support ages and targets both use elapsed calendar time. Cases are overdue after opening timestamp plus SLA hours. Tickets are not automatically complaints; customer satisfaction is unavailable.

Onboarding completes when all required recorded tasks are completed before cutoff. Started incomplete projects are active. Past-due targets or unfinished overdue tasks indicate delay. Task creation history is unavailable, so later-added milestones cannot be reconstructed historically. Allocated hours do not prove productivity or causes of delay.

Earlier follow-ups use current recorded action statuses, explicitly not historical task-state reconstruction. AI narrative is provisional. Human edits are identified separately from computed facts.
