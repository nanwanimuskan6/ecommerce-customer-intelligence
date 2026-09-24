"""Run Phase 4 using existing verified inputs only."""
from pathlib import Path
import hashlib,json,sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from ecommerce_customer_intelligence.analytics.engine import load_ledger
from ecommerce_customer_intelligence.analytics.customer_intelligence import build_rfm,concentration,cohorts_and_lifecycle
from ecommerce_customer_intelligence.analytics.customer_charts import charts

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def table(d):
    d=d.copy()
    for col in d.select_dtypes("number"):
        d[col]=d[col].map(lambda v:f"{v:,.2f}" if pd.notna(v) else "N/A")
    return "| "+" | ".join(d.columns)+" |\n| "+" | ".join(["---"]*len(d.columns))+" |\n"+"\n".join(
        "| "+" | ".join(map(str,row))+" |" for row in d.itertuples(index=False,name=None))

def main():
    paths=["data/raw/Online Retail.xlsx","data/processed/transactions.csv.gz",
        "data/processed/customer_features.csv","reports/metrics/business_kpis.json"]
    before={p:digest(ROOT/p) for p in paths}
    k3=json.loads((ROOT/paths[-1]).read_text())["kpis"]
    features=pd.read_csv(ROOT/paths[2],dtype={"customer_id":"string"},parse_dates=["first_purchase_date","last_purchase_date"])
    ledger=load_ledger(ROOT/paths[1])
    snapshot=k3["recency_reference_date"]
    rfm,s,edges=build_rfm(features,snapshot,k3["valid_customer_purchase_revenue"])
    pareto,shares,con=concentration(rfm)
    cohort,gaps,trend,freq,life=cohorts_and_lifecycle(ledger,rfm)
    tables={"rfm_customers":rfm,"segment_summary":s,"cohort_retention":cohort,
        "customer_concentration":pareto,"customer_concentration_shares":shares,
        "customer_order_gaps":gaps,"customer_lifecycle_trend":trend,"customer_frequency_distribution":freq}
    for name,frame in tables.items():frame.to_csv(ROOT/f"data/processed/{name}.csv",index=False)
    cohort.pivot(index="cohort",columns="month_index",values="complete_retention").to_csv(ROOT/"data/processed/cohort_retention_matrix.csv")
    highest=s.loc[s.average_revenue_per_customer.idxmax()]
    largest=s.loc[s.customer_count.idxmax()]
    most=s.loc[s.total_revenue.idxmax()]
    actions={"Champions":"Test VIP and early-access benefits; review net value before expensive incentives.",
        "Loyal Customers":"Test repeat-order benefits with a holdout group.",
        "Potential Loyalists":"Test relevant follow-up offers to encourage the next purchase.",
        "New Customers":"Test onboarding and relevant cross-sell after the first observed purchase.",
        "Promising":"Test a follow-up timed around observed purchase intervals.",
        "Need Attention":"Review category and purchase cadence before a reminder campaign.",
        "Cannot Lose Them":"Prioritize a high-value win-back review, checking refunds before offering incentives.",
        "At Risk":"Test reactivation against a holdout; inactivity is a heuristic, not confirmed churn.",
        "Hibernating":"Consider a low-cost re-engagement test after checking contact eligibility.",
        "Lost / Low Value":"Limit incentive cost and test selective reactivation rather than assuming permanent loss."}
    recommendations=[]
    for row in s.itertuples():
        if row.customer_count:
            recommendations.append(f"{row.segment}: {row.customer_count:,} customers, £{row.total_revenue:,.2f} gross revenue "
                f"({row.revenue_pct:.2f}%), mean recency {row.average_recency:.1f} days and frequency {row.average_order_frequency:.2f}. "
                f"Observed merchandise returns are £{row.return_value:,.2f}. {actions[row.segment]}")
    risk=rfm.loc[rfm.segment.isin(["At Risk","Cannot Lose Them"])]
    metrics={"customers_analyzed":len(rfm),"excluded_no_valid_purchase_customers":len(features)-len(rfm),
        "snapshot_date":snapshot,"customer_purchase_revenue":float(rfm.monetary.sum()),
        "quantile_boundaries":edges,"highest_value_segment_by_mean_revenue":highest.segment,
        "largest_segment":largest.segment,"most_revenue_segment":most.segment,
        "concentration":con,"revenue_shares":shares.to_dict("records"),"lifecycle":life,
        "risk_segment_customers":len(risk),"risk_segment_gross_revenue":float(risk.monetary.sum()),
        "risk_segment_return_value":float(risk.return_value.sum()),"recommendations":recommendations}
    charts(rfm,s,pareto,cohort,trend,freq,ROOT/"reports/figures")
    after={p:digest(ROOT/p) for p in paths}
    if before!=after:raise RuntimeError("Existing input changed")
    metrics["integrity"]={"before":before,"after":after,"unchanged":True}
    (ROOT/"reports/metrics/customer_intelligence.json").write_text(json.dumps(metrics,indent=2,allow_nan=False),encoding="utf-8")
    s.to_csv(ROOT/"reports/metrics/rfm_segment_summary.csv",index=False)
    m1=cohort.loc[cohort.month_index.eq(1)]
    sections=[
        "# Phase 4 — Advanced customer intelligence",
        "## Reproduce and scope",
        "Run python scripts/run_phase4.py using the existing project virtual environment, then python scripts/run_tests.py. "
        "Only existing Phase 2/3 inputs are read. No earlier phase is rerun, no synthetic transactions are created, and no ML or dashboard is implemented.",
        "## Snapshot and eligibility",
        f"Snapshot: {snapshot}, inherited from Phase 3 (one calendar day after the maximum ledger date). "
        f"{len(rfm):,} identified customers with frequency >= 1 are eligible; {len(features)-len(rfm)} identified ledger customers "
        "with no valid merchandise purchase are excluded from RFM but remain in Phase 3. One record per eligible customer is enforced.",
        "R = existing recency_days, calendar days since last valid purchase. F = existing frequency_orders, distinct valid invoices. "
        "M = existing monetary_value / gross_revenue from identified valid merchandise purchases, not total accounting net revenue. "
        f"M sums to £{rfm.monetary.sum():,.2f} and reconciles with Phase 3. Returns and net merchandise revenue remain visible in the RFM table "
        "and segment summaries. High gross purchase value does not necessarily mean high retained net value.",
        "## Quantile scoring",
        "For each feature, compute its empirical 20th, 40th, 60th and 80th percentiles with pandas' linear interpolation. "
        "The base score is 1 + the number of boundaries strictly less than the feature value "
        "(numpy.searchsorted with side='left'). F and M use the base score; R uses 6 minus the base score. "
        "Scores are integers from 1 to 5, where higher is better. Equal inputs always receive equal scores; "
        "duplicate boundaries are retained, so some score levels can be empty and groups need not have equal sizes. "
        "No customer-ID ranking or arbitrary tie-breaking is used for scores. Thresholds are snapshot-specific.",
        table(pd.DataFrame([{"feature":label,**{f"q{q}":v for q,v in zip([20,40,60,80],values)}} for label,values in edges.items()])),
        "RFM_score concatenates the three score digits as a string. RFM_total_score is their sum (3–15); neither is a probability.",
        "## Deterministic segment rules",
        "Apply these rules in the listed order; the first match wins. The final fallback makes assignment exhaustive.",
        "1. Champions: R >= 4, F >= 4, M >= 4.\n"
        "2. Loyal Customers: R >= 3, F >= 4, excluding Champions.\n"
        "3. Potential Loyalists: R >= 4, F in 2–3.\n"
        "4. New Customers: R >= 4, F = 1.\n"
        "5. Promising: R = 3, F <= 2.\n"
        "6. Need Attention: remaining R >= 3.\n"
        "7. Cannot Lose Them: R <= 2, F >= 4, M >= 4.\n"
        "8. At Risk: remaining R <= 2, F >= 3.\n"
        "9. Hibernating: remaining R = 2.\n"
        "10. Lost / Low Value: all remaining customers (R = 1 and lower frequency).",
        "Segment names are heuristic business labels. New Customers means recent and low-frequency, not a proven acquisition date. "
        "Lost / Low Value does not guarantee low monetary value; inactive one-order customers can have large gross purchases or refunds. "
        "Use the accompanying monetary and return fields before taking action.",
        "## Actual segment profiles",
        table(s),
        "Average AOV and average items/order are unweighted means of per-customer ratios, not pooled order-weighted ratios. "
        "Revenue shares use identified gross merchandise purchase revenue. Empty segments keep zero count/revenue and undefined averages.",
        f"Highest value by mean gross revenue/customer: {highest.segment} (£{highest.average_revenue_per_customer:,.2f}). "
        f"Largest segment: {largest.segment} ({largest.customer_count:,}). Most gross revenue: {most.segment} (£{most.total_revenue:,.2f}). "
        f"At Risk plus Cannot Lose Them contain {len(risk):,} customers and £{risk.monetary.sum():,.2f} gross purchase revenue; "
        f"their observed returns total £{risk.return_value.sum():,.2f}. These labels are not predictive churn estimates.",
        "## Customer concentration",
        table(shares),
        f"{con['customers_for_80pct']:,} customers ({con['customer_pct_for_80pct']:.2f}%) reach at least 80% of customer purchase revenue. "
        "Shares select ceil(N × percentage) customers sorted by descending M, with lexical customer ID tie-breaking only at the cutoff. "
        "The table includes the actual selected percentage. The curve contains only real customers; no artificial origin record is saved. "
        "No universal 80/20 rule is assumed.",
        "## Cohort methodology and retention",
        "Cohort = first observed valid purchase month, not confirmed acquisition. Each customer's activity is counted once per calendar month. "
        "Retention = distinct active cohort customers / original cohort size. Month 0 observed retention is 100% by construction. "
        "Months without activity are zero only if observable; future periods have null active counts and retention. "
        "Partial periods retain observed retention separately but complete_retention is null. The heatmap masks partial cells with P and leaves "
        "future cells blank. The analytical grid enumerates cohort-age cells, not fabricated transactions or customers. "
        "December 2011 is partial; December 2010 is calendar-covered, without any claim that pre-window history is known.",
        table(m1[["cohort","cohort_size","period_status","active_customers","retention","complete_retention"]]),
        f"Month-1 retention across {life['month1_complete_cohorts']} complete follow-up cohorts is "
        f"{life['month1_weighted_retention']:.2%} weighted by cohort size; unweighted mean {life['month1_unweighted_retention']:.2%}, "
        f"range {life['month1_min_retention']:.2%}–{life['month1_max_retention']:.2%}. "
        "November 2011's month-1 follow-up is partial and December 2011's is future, so neither enters this summary.",
        "## Lifecycle findings",
        table(pd.DataFrame([{"metric":k,"value":str(v)} for k,v in life.items()])),
        "Order gaps use distinct (CustomerID, InvoiceNo) pairs and the earliest valid line timestamp, sorted chronologically. "
        "Same-day distinct orders are retained; gaps are fractional days. Gap statistics are interval-weighted among observed repeat orders, "
        "not estimates of a typical future wait. Tenure is snapshot minus first observed purchase date, inherited from Phase 3. "
        "First-time customers can have multiple orders in their first month but remain monthly new; returning means first purchase was in an earlier month.",
        table(trend),
        "## Segment-specific action hypotheses",
        "\n".join(f"- {item}" for item in recommendations),
        "These are proposed experiments tied to measured historical profiles, not claims that a campaign will produce an uplift. No messages are sent.",
        "## Limitations",
        "Anonymous rows are excluded from identity-based analysis; the original cleaning assumptions and conservative service exclusions remain. "
        "Quantile ties lead to unequal score groups. Gross RFM can overstate retained value for fully refunded customers; net and returns should inform "
        "targeting. Segments reflect the single snapshot and are relative to this population. Left-censored history and short follow-up for newer cohorts "
        "limit acquisition and churn interpretations. Observed cohort retention is nonconsecutive monthly activity and can rise in later months. "
        "Complete calendar coverage does not guarantee business-source completeness. No causal inference or predictive validation is claimed.",
        "## Outputs",
        "Reusable CSVs in data/processed: rfm_customers, segment_summary, cohort_retention (long form), cohort_retention_matrix "
        "(complete months only), customer_concentration (ranked curve), customer_concentration_shares, customer_order_gaps, "
        "customer_lifecycle_trend, customer_frequency_distribution. Read customer_id as string and RFM_score as string. "
        "Machine metrics: reports/metrics/customer_intelligence.json and rfm_segment_summary.csv. "
        "Full test results: reports/metrics/test_results.json. Existing .gitignore rules exclude generated datasets and metrics.",
        "## Figures",
        *[f"![{name.replace('_',' ').title()}](../reports/figures/{name}.png)" for name in [
            "rfm_segment_distribution","segment_revenue","segment_count_vs_revenue","customer_pareto",
            "cohort_retention_heatmap","purchase_frequency_distribution","customer_activity_trend","recency_vs_monetary"]],
        "Stopped after Phase 4. Prior modules/tests, raw data, and Phase 3 feature inputs remain unchanged."
    ]
    (ROOT/"docs/PHASE4.md").write_text("\n\n".join(sections)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in metrics.items() if k not in ["integrity","recommendations"]},indent=2))
    print(s[["segment","customer_count","total_revenue","revenue_pct"]].to_string(index=False))
if __name__=="__main__":main()
