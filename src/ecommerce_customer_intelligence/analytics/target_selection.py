"""Empirical target assessment. No models and no alteration of prior phases."""
import numpy as np
import pandas as pd
from .engine import load_ledger

HORIZONS=(30,45,60,90)
def purchase_occasions(ledger):
    p=ledger.loc[ledger.is_customer_purchase]
    return p.groupby(["CustomerID","InvoiceNo"]).InvoiceDate.min().reset_index().sort_values(
        ["CustomerID","InvoiceDate","InvoiceNo"]).reset_index(drop=True)

def assess(ledger):
    orders=purchase_occasions(ledger)
    orders["gap_days"]=orders.groupby("CustomerID").InvoiceDate.diff().dt.total_seconds()/86400
    gaps=orders.gap_days.dropna()
    start,end=ledger.InvoiceDate.min(),ledger.InvoiceDate.max()
    cutoffs=pd.date_range(start.normalize()+pd.offsets.MonthBegin(1),end.normalize(),freq="MS")
    by_customer={cid:g.InvoiceDate.sort_values().to_numpy(dtype="datetime64[ns]") for cid,g in orders.groupby("CustomerID")}
    records=[]
    for cutoff in cutoffs:
        for cid,times in by_customer.items():
            n=int(np.searchsorted(times,np.datetime64(cutoff),"left"))
            if n==0:continue
            next_time=pd.Timestamp(times[n]) if n<len(times) else pd.NaT
            for h in HORIZONS:
                target_end=cutoff+pd.Timedelta(days=h)
                complete=target_end<=end
                positive=pd.notna(next_time) and next_time<target_end
                records.append({"customer_id":cid,"snapshot_date":cutoff,"horizon_days":h,
                    "target_end":target_end,"full_followup":complete,
                    "target":int(positive) if complete else None,
                    "historical_orders":n,"first_observed_purchase":pd.Timestamp(times[0]),
                    "last_historical_purchase":pd.Timestamp(times[n-1]),
                    "next_observed_purchase":next_time,
                    "customer_history_days":(cutoff-pd.Timestamp(times[0])).total_seconds()/86400,
                    "available_dataset_history_days":(cutoff-start).total_seconds()/86400})
    snapshots=pd.DataFrame(records)
    common_last=max(cutoffs[cutoffs+pd.Timedelta(days=max(HORIZONS))<=end])
    rows=[]
    for h,g in snapshots.groupby("horizon_days"):
        a=g.loc[g.full_followup];common=a.loc[a.snapshot_date.le(common_last)]
        warm=a.loc[a.snapshot_date.ge(cutoffs[0]+pd.DateOffset(months=3))]
        rows.append({"horizon_days":int(h),"candidate_snapshots":len(g),"eligible_snapshots":len(a),
            "censored_snapshots":int((~g.full_followup).sum()),"eligible_customers":int(a.customer_id.nunique()),
            "positive":int(a.target.sum()),"negative":int(a.target.eq(0).sum()),
            "positive_pct":float(a.target.mean()*100),"fully_observed_snapshot_dates":a.snapshot_date.nunique(),
            "first_eligible_snapshot":str(a.snapshot_date.min()),"last_eligible_snapshot":str(a.snapshot_date.max()),
            "latest_possible_cutoff":str(end-pd.Timedelta(days=int(h))),
            "min_dataset_history_days":float(a.available_dataset_history_days.min()),
            "max_dataset_history_days":float(a.available_dataset_history_days.max()),
            "median_customer_history_days":float(a.customer_history_days.median()),
            "single_prior_order_pct":float(a.historical_orders.eq(1).mean()*100),
            "completed_gap_coverage_pct":float(gaps.le(h).mean()*100),
            "common_snapshot_count":len(common),"common_positive":int(common.target.sum()),
            "common_negative":int(common.target.eq(0).sum()),"common_positive_pct":float(common.target.mean()*100),
            "after_first_three_snapshots_count":len(warm),
            "after_first_three_snapshots_positive_pct":float(warm.target.mean()*100)})
    comparison=pd.DataFrame(rows)
    # Declared operational criterion, not optimization against target balance.
    # Select the shortest candidate covering the upper quartile of completed gaps.
    q75=float(gaps.quantile(.75))
    chosen=next((h for h in HORIZONS if h>=q75),max(HORIZONS))
    summary={"eligible_customers":int(orders.CustomerID.nunique()),
        "repeat_customers":int(orders.groupby("CustomerID").size().ge(2).sum()),
        "purchase_occasions":len(orders),"completed_interpurchase_intervals":len(gaps),
        "median_days":float(gaps.median()),"mean_days":float(gaps.mean()),
        "p25_days":float(gaps.quantile(.25)),"p75_days":q75,"p90_days":float(gaps.quantile(.9)),
        "min_days":float(gaps.min()),"max_days":float(gaps.max()),
        "zero_day_gaps":int(gaps.eq(0).sum()),"under_one_day_gaps":int(gaps.lt(1).sum()),
        "coverage_pct":{str(h):float(gaps.le(h).mean()*100) for h in [7,14,30,45,60,90]},
        "observation_start":str(start),"observation_end":str(end),"snapshot_dates":len(cutoffs),
        "common_last_snapshot":str(common_last),"recommended_horizon_days":chosen,
        "criterion":"Shortest candidate at or above the observed completed-gap 75th percentile; balance is diagnostic only."}
    # Same-day sensitivity: distinct customer calendar dates, without changing the main invoice definition.
    days=orders.assign(day=orders.InvoiceDate.dt.normalize()).drop_duplicates(["CustomerID","day"])
    day_gaps=days.groupby("CustomerID").day.diff().dt.days.dropna()
    summary["calendar_day_sensitivity"]={"intervals":len(day_gaps),
        "median_days":float(day_gaps.median()),"p75_days":float(day_gaps.quantile(.75)),
        "recommended_by_same_criterion":next((h for h in HORIZONS if h>=day_gaps.quantile(.75)),max(HORIZONS))}
    per_date=snapshots.groupby(["horizon_days","snapshot_date"]).agg(
        candidate_customers=("customer_id","size"),full_followup=("full_followup","all"),
        positives=("target","sum"),eligible=("target","count")).reset_index()
    per_date["negatives"]=per_date.eligible-per_date.positives
    per_date.loc[~per_date.full_followup,["positives","negatives"]]=np.nan
    return summary,comparison,orders,snapshots,per_date
