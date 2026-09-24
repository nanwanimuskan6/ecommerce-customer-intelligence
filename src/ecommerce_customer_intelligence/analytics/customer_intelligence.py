"""Explainable RFM, concentration, cohort and lifecycle analysis."""
import numpy as np
import pandas as pd

SEGMENTS = ["Champions","Loyal Customers","Potential Loyalists","New Customers",
            "Promising","Need Attention","Cannot Lose Them","At Risk","Hibernating","Lost / Low Value"]

def score_values(values, reverse=False):
    edges=values.quantile([.2,.4,.6,.8]).to_numpy()
    score=pd.Series(np.searchsorted(edges,values.to_numpy(),side="left")+1,index=values.index,dtype=int)
    return (6-score if reverse else score), edges.tolist()

def assign_segments(rfm):
    r,f,m=rfm.R_score,rfm.F_score,rfm.M_score
    conditions=[(r>=4)&(f>=4)&(m>=4),(r>=3)&(f>=4),
        (r>=4)&f.between(2,3),(r>=4)&(f==1),(r==3)&(f<=2),
        (r>=3),(r<=2)&(f>=4)&(m>=4),(r<=2)&(f>=3),(r==2)]
    return pd.Series(np.select(conditions,SEGMENTS[:-1],default=SEGMENTS[-1]),index=rfm.index)

def build_rfm(features, snapshot, expected_revenue):
    c=features.loc[features.frequency_orders.ge(1)].copy()
    if c.customer_id.isna().any() or not c.customer_id.is_unique:
        raise ValueError("Expected one identified record per purchasing customer")
    if c.recency_days.isna().any() or c.recency_days.lt(0).any() or c.monetary_value.le(0).any():
        raise ValueError("Invalid RFM values")
    calculated=(pd.Timestamp(snapshot)-pd.to_datetime(c.last_purchase_date).dt.normalize()).dt.days
    if not calculated.equals(c.recency_days.astype(int)):
        raise ValueError("Snapshot conflicts with Phase 3 recency")
    if not np.isclose(c.monetary_value.sum(),expected_revenue,rtol=0,atol=1e-6):
        raise ValueError("Customer monetary total does not reconcile with Phase 3")
    c["recency"]=c.recency_days.astype(int); c["frequency"]=c.frequency_orders
    c["monetary"]=c.monetary_value
    edges={}
    for source,label,reverse in [("recency","R",True),("frequency","F",False),("monetary","M",False)]:
        c[label+"_score"],edges[label]=score_values(c[source],reverse)
    c["RFM_score"]=c[["R_score","F_score","M_score"]].astype(str).agg("".join,axis=1)
    c["RFM_total_score"]=c[["R_score","F_score","M_score"]].sum(axis=1)
    c["segment"]=assign_segments(c)
    s=c.groupby("segment").agg(customer_count=("customer_id","size"),
        total_revenue=("monetary","sum"),average_revenue_per_customer=("monetary","mean"),
        median_revenue_per_customer=("monetary","median"),average_order_frequency=("frequency","mean"),
        average_recency=("recency","mean"),average_aov=("average_order_value","mean"),
        average_items_per_order=("average_items_per_order","mean"),
        return_value=("return_value","sum"),net_merchandise_revenue=("net_revenue","sum"))
    s=s.reindex(SEGMENTS)
    s[["customer_count","total_revenue","return_value","net_merchandise_revenue"]]=s[
        ["customer_count","total_revenue","return_value","net_merchandise_revenue"]].fillna(0)
    s["customer_count"]=s.customer_count.astype(int)
    s["customer_pct"]=100*s.customer_count/len(c)
    s["revenue_pct"]=100*s.total_revenue/c.monetary.sum()
    return c,s.reset_index(),edges

def concentration(c):
    ranked=c[["customer_id","monetary"]].sort_values(["monetary","customer_id"],ascending=[False,True]).reset_index(drop=True)
    ranked["customer_rank"]=np.arange(1,len(ranked)+1)
    ranked["cumulative_customer_pct"]=ranked.customer_rank/len(ranked)*100
    ranked["cumulative_revenue_pct"]=ranked.monetary.cumsum()/ranked.monetary.sum()*100
    shares=[]
    for pct in [1,5,10,20]:
        n=int(np.ceil(len(ranked)*pct/100))
        shares.append({"top_pct":pct,"customer_count":n,
            "actual_customer_pct":100*n/len(ranked),
            "revenue_share_pct":float(ranked.iloc[n-1].cumulative_revenue_pct)})
    crossing=ranked.loc[ranked.cumulative_revenue_pct.ge(80)].iloc[0]
    return ranked,pd.DataFrame(shares),{"customers_for_80pct":int(crossing.customer_rank),
        "customer_pct_for_80pct":float(crossing.cumulative_customer_pct)}

def cohorts_and_lifecycle(ledger,rfm):
    p=ledger.loc[ledger.is_customer_purchase].copy()
    orders=p.groupby(["CustomerID","InvoiceNo"]).InvoiceDate.min().reset_index().sort_values(["CustomerID","InvoiceDate","InvoiceNo"])
    orders["purchase_month"]=orders.InvoiceDate.dt.to_period("M")
    first=orders.groupby("CustomerID").purchase_month.min()
    orders["cohort"]=orders.CustomerID.map(first)
    active=orders[["CustomerID","cohort","purchase_month"]].drop_duplicates()
    counts=active.groupby(["cohort","purchase_month"]).size()
    sizes=first.value_counts()
    start=ledger.InvoiceDate.min().normalize(); end=ledger.InvoiceDate.max().normalize()
    last=end.to_period("M"); first_month=start.to_period("M")
    max_age=last.ordinal-first_month.ordinal
    records=[]
    for cohort in sorted(sizes.index):
        for age in range(max_age+1):
            period=cohort+age
            status="future" if period>last else ("partial" if period.end_time.normalize()>end or period.start_time.normalize()<start else "complete")
            n=None if status=="future" else int(counts.get((cohort,period),0))
            records.append({"cohort":str(cohort),"cohort_size":int(sizes[cohort]),"month_index":age,
                "activity_month":str(period),"period_status":status,"active_customers":n,
                "retention":None if n is None else n/int(sizes[cohort]),
                "complete_retention":n/int(sizes[cohort]) if status=="complete" else None})
    cohort_table=pd.DataFrame(records)
    orders["gap_days"]=orders.groupby("CustomerID").InvoiceDate.diff().dt.total_seconds()/86400
    gaps=orders.loc[orders.gap_days.notna(),["CustomerID","InvoiceNo","InvoiceDate","gap_days"]]
    trend=active.groupby("purchase_month").CustomerID.nunique().rename("active_customers").to_frame()
    trend["new_customers"]=first.value_counts()
    trend["returning_customers"]=trend.active_customers-trend.new_customers
    trend["is_partial"]=[x.end_time.normalize()>end or x.start_time.normalize()<start for x in trend.index]
    trend=trend.reset_index(); trend["purchase_month"]=trend.purchase_month.astype(str)
    freq=rfm.groupby("frequency").size().reset_index(name="customer_count")
    m1=cohort_table.loc[cohort_table.month_index.eq(1)&cohort_table.period_status.eq("complete")]
    metrics={"one_time_customers":int(rfm.frequency.eq(1).sum()),"repeat_customers":int(rfm.frequency.ge(2).sum()),
        "median_frequency":float(rfm.frequency.median()),"median_tenure_days":float(rfm.customer_tenure_days.median()),
        "mean_tenure_days":float(rfm.customer_tenure_days.mean()),"observed_order_gaps":len(gaps),
        "median_interpurchase_days":float(gaps.gap_days.median()),"mean_interpurchase_days":float(gaps.gap_days.mean()),
        "month1_complete_cohorts":len(m1),"month1_weighted_retention":float(m1.active_customers.sum()/m1.cohort_size.sum()),
        "month1_unweighted_retention":float(m1.retention.mean()),
        "month1_min_retention":float(m1.retention.min()),"month1_max_retention":float(m1.retention.max())}
    return cohort_table,gaps,trend,freq,metrics
