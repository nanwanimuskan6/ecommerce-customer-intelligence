"""As-of features: every source transaction must precede the snapshot."""
import numpy as np
import pandas as pd
FEATURES=["recency_days","purchase_frequency","monetary_value","total_items",
    "average_order_value","average_items_per_order","median_order_value","max_order_value",
    "customer_tenure_days","average_days_between_purchases","median_days_between_purchases",
    "std_days_between_purchases","historical_return_count","historical_return_rate",
    "historical_returned_value","historical_dataset_days",
    "orders_previous_30_days","orders_previous_60_days","orders_previous_90_days",
    "history_30_days_complete","history_60_days_complete","history_90_days_complete"]
def asof_features(ledger,cutoff,customer_ids):
    cutoff=pd.Timestamp(cutoff)
    hist=ledger.loc[ledger.InvoiceDate.lt(cutoff)]
    p=hist.loc[hist.is_customer_purchase]
    orders=p.groupby(["CustomerID","InvoiceNo"]).agg(date=("InvoiceDate","min"),
        value=("line_revenue","sum"),items=("Quantity","sum")).reset_index().sort_values(["CustomerID","date","InvoiceNo"])
    orders["gap"]=orders.groupby("CustomerID").date.diff().dt.total_seconds()/86400
    c=orders.groupby("CustomerID").agg(first=("date","min"),last=("date","max"),
        purchase_frequency=("InvoiceNo","nunique"),monetary_value=("value","sum"),total_items=("items","sum"),
        average_order_value=("value","mean"),average_items_per_order=("items","mean"),
        median_order_value=("value","median"),max_order_value=("value","max"),
        average_days_between_purchases=("gap","mean"),median_days_between_purchases=("gap","median"),
        std_days_between_purchases=("gap","std"))
    c=c.reindex(pd.Index(customer_ids,name="CustomerID"))
    if c.purchase_frequency.isna().any():raise ValueError("Snapshot customer lacks a historical valid purchase")
    c["recency_days"]=(cutoff-c["last"]).dt.total_seconds()/86400
    c["customer_tenure_days"]=(cutoff-c["first"]).dt.total_seconds()/86400
    returns=hist.loc[~hist.is_duplicate & hist.has_customer_id & (hist.is_return|hist.is_cancellation)]
    rg=returns.groupby("CustomerID")
    c["historical_return_count"]=rg.InvoiceNo.nunique().reindex(c.index).fillna(0)
    c["historical_returned_value"]=rg.return_cancellation_value.sum().reindex(c.index).fillna(0)
    c["historical_return_rate"]=c.historical_return_count/c.purchase_frequency
    start=ledger.InvoiceDate.min()
    c["historical_dataset_days"]=(cutoff-start).total_seconds()/86400
    for days in [30,60,90]:
        complete=cutoff-pd.Timedelta(days=days)>=start
        counts=orders.loc[orders.date.ge(cutoff-pd.Timedelta(days=days))].groupby("CustomerID").InvoiceNo.nunique()
        c[f"orders_previous_{days}_days"]=counts.reindex(c.index).fillna(0) if complete else np.nan
        c[f"history_{days}_days_complete"]=int(complete)
    return c[FEATURES]
def split_name(date):
    date=pd.Timestamp(date)
    if date<=pd.Timestamp("2011-04-01"):return "train"
    if pd.Timestamp("2011-06-01")<=date<=pd.Timestamp("2011-07-01"):return "validation"
    if date>=pd.Timestamp("2011-09-01"):return "test"
    return "embargo"
def build_dataset(ledger,snapshots):
    base=snapshots.loc[snapshots.horizon_days.eq(60)&snapshots.full_followup].copy()
    orders=ledger.loc[ledger.is_customer_purchase].groupby(["CustomerID","InvoiceNo"]).InvoiceDate.min().reset_index()
    arrays={cid:np.sort(g.InvoiceDate.to_numpy(dtype="datetime64[ns]")) for cid,g in orders.groupby("CustomerID")}
    records=[]
    for date,g in base.groupby("snapshot_date"):
        f=asof_features(ledger,date,g.customer_id.tolist()).reset_index().rename(columns={"CustomerID":"customer_id"})
        f["snapshot_date"]=date; f["target_end"]=date+pd.Timedelta(days=60)
        labels=[]
        for cid in f.customer_id:
            a=arrays[cid]
            lo=np.searchsorted(a,np.datetime64(date),side="right")
            hi=np.searchsorted(a,np.datetime64(date+pd.Timedelta(days=60)),side="right")
            labels.append(int(hi>lo))
        f["target"]=labels; f["split"]=split_name(date);records.append(f)
    result=pd.concat(records,ignore_index=True)
    old=base.set_index(["customer_id","snapshot_date"]).target
    keys=pd.MultiIndex.from_frame(result[["customer_id","snapshot_date"]])
    return result,int((result.target.to_numpy()!=old.reindex(keys).to_numpy()).sum())
