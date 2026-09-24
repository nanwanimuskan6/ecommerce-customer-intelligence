"""Phase 5A target selection and plots; no model fitting."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from ecommerce_customer_intelligence.analytics.target_selection import assess,load_ledger
from ecommerce_customer_intelligence.analytics.theme import canvas,C,grid,save,number,percent,callout

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def table(d):
    d=d.copy()
    for col in d.select_dtypes("number"):
        d[col]=d[col].map(lambda v:f"{v:,.2f}" if pd.notna(v) else "N/A")
    return "| "+" | ".join(d.columns)+" |\n| "+" | ".join(["---"]*len(d.columns))+" |\n"+"\n".join("| "+" | ".join(map(str,r))+" |" for r in d.itertuples(index=False,name=None))

def main():
    protected=[p for folder in ["data","src","reports/metrics","reports/figures","docs","tests"] for p in (ROOT/folder).rglob("*")
        if p.is_file() and p.suffix in {".csv",".gz",".xlsx",".json",".png",".svg",".md",".py"}
        and "phase5a" not in p.name.lower() and "target_selection" not in p.name and "__pycache__" not in str(p)]
    before={str(p.relative_to(ROOT)):digest(p) for p in protected}
    ledger=load_ledger(ROOT/"data/processed/transactions.csv.gz")
    summary,comparison,orders,snapshots,by_date=assess(ledger)
    h=summary["recommended_horizon_days"]
    selected=comparison.loc[comparison.horizon_days.eq(h)].iloc[0]
    orders.to_csv(ROOT/"data/processed/phase5a_purchase_occasions.csv",index=False)
    snapshots.to_csv(ROOT/"data/processed/phase5a_candidate_snapshots.csv.gz",index=False)
    comparison.to_csv(ROOT/"reports/metrics/phase5a_horizon_comparison.csv",index=False)
    by_date.to_csv(ROOT/"reports/metrics/phase5a_snapshot_dates.csv",index=False)
    gaps=orders.gap_days.dropna()
    fig,ax=canvas("Observed repeat purchases span a wide time range",
        f"Median {summary['median_days']:.1f} days • middle 50%: {summary['p25_days']:.1f}–{summary['p75_days']:.1f} days",
        "Completed invoice-to-invoice intervals only; unobserved future returns are not included in this distribution.")
    ax.hist(gaps,bins="fd",color=C["primary"],edgecolor="white",lw=.4)
    ax.axvline(summary["median_days"],color=C["highlight"],ls="--",lw=1.5)
    ax.axvline(summary["p75_days"],color=C["secondary"],ls=":",lw=1.5)
    ax.set(xlabel="Days between consecutive valid purchase invoices",ylabel="Completed purchase intervals",xlim=(0,gaps.max()))
    ax.yaxis.set_major_formatter(FuncFormatter(number));grid(ax)
    save(fig,ROOT/"reports/figures","phase5a_interpurchase_distribution")
    x=np.sort(gaps.to_numpy());y=np.arange(1,len(x)+1)/len(x)*100
    fig,ax=canvas("How quickly observed repeat purchases occur",
        f"{summary['coverage_pct'][str(h)]:.1f}% of completed intervals fall within the recommended {h}-day window",
        "Empirical distribution of completed gaps, not the probability that any customer will return.")
    ax.plot(x,y,color=C["primary"]);ax.axvline(h,color=C["highlight"],ls=":",lw=1)
    callout(ax,h,summary["coverage_pct"][str(h)],f"{h} days • {summary['coverage_pct'][str(h)]:.1f}%",(24,-45))
    ax.set(xlabel="Days between valid purchase invoices",ylabel="Cumulative completed intervals",ylim=(0,103),xlim=(0,x.max()))
    ax.yaxis.set_major_formatter(FuncFormatter(percent));grid(ax)
    save(fig,ROOT/"reports/figures","phase5a_interpurchase_cumulative")
    fig,ax=canvas("Longer horizons capture more observed repeat intervals",
        "Completed-gap coverage versus positive-label rate on identical, fully observed snapshot dates",
        f"Recommended: {h} days. Selection uses purchase cadence and usable follow-up, not class balance.")
    idx=np.arange(len(comparison))
    ax.plot(idx,comparison.completed_gap_coverage_pct,color=C["primary"],marker="o",label="Completed-gap coverage")
    ax.plot(idx,comparison.common_positive_pct,color=C["secondary"],marker="s",label="Common-snapshot positive rate")
    ax.set_xticks(idx,[f"{v} days" for v in comparison.horizon_days])
    ax.set(ylabel="Share (%)",ylim=(0,105));ax.yaxis.set_major_formatter(FuncFormatter(percent));grid(ax)
    ax.legend(loc="upper left",bbox_to_anchor=(0,1.12),ncol=2,fontsize=9)
    for i,row in enumerate(comparison.itertuples()):
        ax.text(i,row.completed_gap_coverage_pct+4,f"{row.completed_gap_coverage_pct:.1f}%",ha="center",color=C["primary"])
    save(fig,ROOT/"reports/figures","phase5a_candidate_windows")
    after={str(p.relative_to(ROOT)):digest(p) for p in protected}
    if before!=after:raise RuntimeError("Previous phase artifact changed")
    summary["comparison"]=comparison.to_dict("records")
    summary["integrity"]={"prior_artifacts_unchanged":True,"sha256":before}
    (ROOT/"reports/metrics/phase5a_target_selection.json").write_text(json.dumps(summary,indent=2,allow_nan=False),encoding="utf-8")
    sections=[
        "# Phase 5A — Repeat-purchase target and horizon selection",
        "## Decision",
        f"Recommend **{h} days**, conditional on the monthly existing-customer snapshot design below. "
        f"The observed median invoice-to-invoice gap is {summary['median_days']:.2f} days; the 75th percentile is "
        f"{summary['p75_days']:.2f} days. The selected horizon is the shortest supplied candidate at or above that upper quartile, "
        f"capturing {summary['coverage_pct'][str(h)]:.2f}% of completed repeat intervals. "
        "The upper-quartile criterion is an explicit operational trade-off, not a statistically unique optimum: allow most observed repeat cycles "
        "while retaining timely intervention and more evaluable historical snapshots than a longer window. "
        "Class balance is reported as a consequence, never optimized. A campaign budget or deployment cadence could justify revisiting this choice.",
        "## Purchase occasions and empirical evidence",
        "Use the existing is_customer_purchase flag unchanged. Aggregate each (CustomerID, InvoiceNo) to its earliest valid timestamp, "
        "so invoice line items are not separate occasions. Sort by customer, timestamp, then invoice. Distinct invoices on the same day "
        "remain separate occasions, including simultaneous invoices; report zero and sub-day gaps and a calendar-day sensitivity check. "
        "Fractional-day gaps preserve source timestamps.",
        table(pd.DataFrame([{"measure":k,"value":str(v)} for k,v in summary.items() if k not in ["comparison","integrity","coverage_pct"]])),
        table(pd.DataFrame([{"within_days":int(k),"completed_interval_pct":v} for k,v in summary["coverage_pct"].items()])),
        "The distribution counts completed intervals, so frequent buyers contribute multiple gaps. One-time buyers and the unfinished "
        "last waiting interval of every customer do not contribute completed gaps. This selection and right-censoring bias tends to favor "
        "shorter observed intervals. It is not a customer return-probability estimate. Snapshot labels below explicitly include customers "
        "with no subsequent purchase only when follow-up is complete. Calendar-day sensitivity checks whether multiple invoices drive the recommendation.",
        "## Target and snapshot design",
        "At each calendar-month start t, include every identified customer with at least one valid purchase strictly before t. "
        "The target is **1 if a valid customer purchase occurs in [t, t + H days), otherwise 0**, but only when t + H is no later than "
        "the last observed ledger timestamp. Feature history is [dataset start, t), strictly excluding target purchases. "
        "Customers may contribute multiple monthly snapshots. January 2011 is the first cutoff: it follows the first observed calendar month; "
        "December 2011 is the last candidate cutoff. Monthly cadence represents a recurring retention decision rather than an immediate post-order trigger.",
        "Snapshot design affects class balance and observation count; these results do not apply automatically to order-triggered scoring. "
        "The eligible customer population expands with observed purchases and includes inactive customers, without an arbitrary recent-activity filter.",
        "## Candidate comparison",
        table(comparison[["horizon_days","completed_gap_coverage_pct","eligible_snapshots","censored_snapshots",
            "eligible_customers","positive","negative","positive_pct","fully_observed_snapshot_dates","last_eligible_snapshot"]]),
        "30 days supports a short monthly conversion decision; 45 days extends it into roughly six weeks; 60 days covers roughly two months; "
        "90 days is a slower quarterly follow-up decision. Longer windows can include more purchase cycles but postpone outcome availability, "
        "discard more late snapshots, and create more overlap between adjacent labels. All candidates require the same strict censoring rule.",
        "### Matched-date and history sensitivity",
        table(comparison[["horizon_days","common_snapshot_count","common_positive","common_negative","common_positive_pct",
            "min_dataset_history_days","max_dataset_history_days","median_customer_history_days","single_prior_order_pct",
            "after_first_three_snapshots_count","after_first_three_snapshots_positive_pct"]]),
        f"Common-date comparisons end at {summary['common_last_snapshot']}; the customer/date population is identical across horizons. "
        "The additional warm-up sensitivity excludes the first three monthly cutoffs (January–March) solely to assess limited initial history; "
        "it does not silently change the primary population. It is a history-design sensitivity, not a prediction-window assumption.",
        "## Selected target population",
        f"{int(selected.eligible_snapshots):,} fully observed customer snapshots across "
        f"{int(selected.fully_observed_snapshot_dates)} dates and {int(selected.eligible_customers):,} distinct customers. "
        f"Positive: {int(selected.positive):,} ({selected.positive_pct:.2f}%); negative: {int(selected.negative):,} "
        f"({100-selected.positive_pct:.2f}%). Censored/excluded for this horizon: {int(selected.censored_snapshots):,}.",
        "## Censoring policy",
        "Every insufficient-follow-up snapshot retains a null target, even if an early repeat purchase is visible. This conservative complete-window "
        "policy keeps eligibility independent of whether a positive event happens early. No incomplete snapshot is labeled negative. "
        "The complete-window boundary uses the actual maximum ledger timestamp, not a fabricated month end. "
        "Customer disappearance before that date cannot be distinguished from nonpurchase. A negative means no observed valid purchase in the window, not churn.",
        "## Leakage-free feasibility and suitability",
        "This dataset is suitable for a limited historical repeat-purchase propensity exercise, with observed-purchase rather than true churn labels. "
        "Recency, cumulative order frequency, gross purchase value, prior returns and tenure can later be calculated from events strictly before each cutoff. "
        "Only snapshot metadata is saved now; no feature matrix or model is trained. Earliest cutoffs have only about one observed month of history, "
        "so long-lookback seasonal features are not supported everywhere. Newer customers also have short histories and require exposure-aware features.",
        "Do not merge full-window Phase 3 customer features or Phase 4 RFM segments into training snapshots: those contain future information. "
        "Do not expose next_observed_purchase, target_end-derived future facts, gap outcomes, or target columns as predictors. "
        "Use forward calendar splits; training label windows must finish before the validation scoring period. Fit transformations only on training data. "
        "Adjacent monthly labels overlap, and customers recur: row count overstates independent sample size; uncertainty must account for customer/time dependence. "
        "The one-year history offers few independent forward evaluation periods and limited seasonality evidence.",
        "A censored time-to-next-purchase analysis is a defensible complementary target because it retains terminal censored spells and avoids a fixed horizon. "
        "It does not eliminate short history or missing identities, and is not so clearly superior that the requested binary repeat-purchase objective should "
        "be replaced. No objective change is made. Reassess feasibility during temporal feature/split design before any claim of predictive performance.",
        "## Files and reproduction",
        "Run python scripts/run_phase5a.py in the project environment. Outputs: phase5a_purchase_occasions.csv and "
        "phase5a_candidate_snapshots.csv.gz under data/processed; phase5a_target_selection.json, phase5a_horizon_comparison.csv and "
        "phase5a_snapshot_dates.csv under reports/metrics. The snapshot table is an assessment/label ledger, not a model-ready feature matrix. "
        "All prior artifact hashes are verified and stored in the new JSON. Tests are written to a separate phase5a_test_results.json to preserve previous reports.",
        "## Figures",
        *[f"![{name}](../reports/figures/phase5a_{name}.png)" for name in ["interpurchase_distribution","interpurchase_cumulative","candidate_windows"]],
        "Stopped after target selection. No classifiers, SHAP, dashboard, or deployment."
    ]
    (ROOT/"docs/PHASE5A.md").write_text("\n\n".join(sections)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k not in ["integrity","comparison"]},indent=2))
    print(comparison[["horizon_days","eligible_snapshots","positive","negative","positive_pct","censored_snapshots"]].to_string(index=False))
if __name__=="__main__":main()
