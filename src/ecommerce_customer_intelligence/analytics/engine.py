"""Explicit accounting and merchandise-purchase KPI scopes."""
from pathlib import Path
import pandas as pd
import numpy as np

MONEY = ["gross_purchase_revenue", "return_cancellation_value",
         "other_adjustment_revenue", "net_revenue"]

def load_ledger(path):
    d = pd.read_csv(path, dtype={x: "string" for x in ["InvoiceNo", "StockCode", "CustomerID"]},
                    parse_dates=["InvoiceDate"], keep_default_na=False, na_values=[""])
    flags = ["is_duplicate", "is_cancellation", "is_return", "has_customer_id",
             "is_non_product", "has_valid_description", "has_valid_price",
             "is_valid_purchase", "is_customer_purchase"]
    required = flags + MONEY + ["source_excel_row", "Quantity", "UnitPrice", "line_revenue",
                               "InvoiceDate", "Country", "Description", "StockCode", "InvoiceNo", "CustomerID"]
    missing = set(required) - set(d)
    if missing:
        raise ValueError(f"Missing processed columns: {sorted(missing)}")
    if any(d[c].dtype != bool for c in flags):
        raise ValueError("Cleaning flags must be non-null booleans")
    if d.InvoiceDate.isna().any() or not d.source_excel_row.is_unique:
        raise ValueError("Invalid dates or repeated source row identifiers")
    return d

def divide(n, d):
    return n / d if d else None

def build_tables(d):
    p = d.loc[d.is_valid_purchase].copy()
    cp = d.loc[d.is_customer_purchase].copy()
    r = d.loc[~d.is_duplicate & (d.is_return | d.is_cancellation)].copy()
    mr = r.loc[r.has_valid_price & r.has_valid_description & ~r.is_non_product].copy()
    orders = p.groupby("InvoiceNo").agg(order_date=("InvoiceDate","min"),
        purchase_revenue=("line_revenue","sum"), quantity=("Quantity","sum"),
        customer_count=("CustomerID","nunique"), country_count=("Country","nunique"))
    identified = cp.groupby("CustomerID").agg(first_purchase_date=("InvoiceDate","min"),
        last_purchase_date=("InvoiceDate","max"), frequency_orders=("InvoiceNo","nunique"),
        total_quantity=("Quantity","sum"), gross_revenue=("line_revenue","sum"))
    ids = pd.Index(d.loc[d.has_customer_id,"CustomerID"].unique(), name="CustomerID").sort_values()
    customers = identified.reindex(ids)
    for col in ["frequency_orders", "total_quantity", "gross_revenue"]:
        customers[col] = customers[col].fillna(0)
    ret = mr.loc[mr.has_customer_id].groupby("CustomerID").agg(
        return_count=("InvoiceNo","nunique"), return_value=("return_cancellation_value","sum"))
    customers = customers.join(ret).fillna({"return_count":0, "return_value":0})
    customers["net_revenue"] = customers.gross_revenue - customers.return_value
    customers["monetary_value"] = customers.gross_revenue
    customers["average_order_value"] = customers.gross_revenue / customers.frequency_orders.replace(0,np.nan)
    customers["average_items_per_order"] = customers.total_quantity / customers.frequency_orders.replace(0,np.nan)
    reference = d.InvoiceDate.max().normalize() + pd.Timedelta(days=1)
    customers["recency_days"] = (reference - customers.last_purchase_date.dt.normalize()).dt.days
    customers["customer_tenure_days"] = (reference - customers.first_purchase_date.dt.normalize()).dt.days
    customers = customers.reset_index().rename(columns={"CustomerID":"customer_id"})
    for col in ["frequency_orders","return_count"]:
        customers[col] = customers[col].astype(int)

    monthly = d.groupby(d.InvoiceDate.dt.to_period("M")).agg(
        **{c:(c,"sum") for c in MONEY})
    monthly.index.name = "month"
    pm = p.groupby(p.InvoiceDate.dt.to_period("M"))
    monthly["orders"] = pm.InvoiceNo.nunique()
    monthly["unique_customers"] = pm.CustomerID.nunique()
    monthly["valid_purchase_revenue"] = pm.line_revenue.sum()
    monthly["aov"] = monthly.valid_purchase_revenue / monthly.orders
    first = cp.groupby("CustomerID").InvoiceDate.min().dt.to_period("M")
    monthly["new_customers"] = first.value_counts()
    monthly["new_customers"] = monthly.new_customers.fillna(0).astype(int)
    monthly["repeat_customers"] = monthly.unique_customers - monthly.new_customers
    start, end = d.InvoiceDate.min().normalize(), d.InvoiceDate.max().normalize()
    monthly["is_partial"] = [(x.start_time.normalize() < start or x.end_time.normalize() > end) for x in monthly.index]
    monthly["net_revenue_growth_pct_observed"] = monthly.net_revenue.pct_change()*100
    comparable = ~monthly.is_partial & ~monthly.is_partial.shift(1, fill_value=True)
    monthly["net_revenue_growth_pct_complete"] = monthly.net_revenue_growth_pct_observed.where(comparable)
    monthly = monthly.reset_index()
    monthly["month"] = monthly.month.astype(str)

    country = d.groupby("Country")[MONEY].sum()
    pg = p.groupby("Country")
    country["orders"] = pg.InvoiceNo.nunique()
    country["customers"] = pg.CustomerID.nunique()
    country["valid_purchase_revenue"] = pg.line_revenue.sum()
    country[["orders","customers","valid_purchase_revenue"]] = country[["orders","customers","valid_purchase_revenue"]].fillna(0)
    country["aov"] = country.valid_purchase_revenue / country.orders.replace(0,np.nan)
    country["revenue_contribution_pct"] = 100*country.net_revenue/d.net_revenue.sum()
    country["return_value_rate_pct"] = 100*country.return_cancellation_value/country.gross_purchase_revenue.replace(0,np.nan)
    country["return_invoices"] = r.groupby("Country").InvoiceNo.nunique()
    country["return_invoices"] = country.return_invoices.fillna(0)
    country = country.sort_values("net_revenue",ascending=False).reset_index()

    products = p.groupby("StockCode").agg(gross_revenue=("line_revenue","sum"),
        quantity=("Quantity","sum"), purchase_orders=("InvoiceNo","nunique"),
        purchase_rows=("InvoiceNo","size"), description_variants=("Description","nunique"))
    # Most frequent observed purchase description; lexical tie-break is deterministic.
    labels = p.groupby(["StockCode","Description"]).size().reset_index(name="n").sort_values(
        ["StockCode","n","Description"],ascending=[True,False,True]).drop_duplicates("StockCode").set_index("StockCode").Description
    rev = mr.groupby("StockCode").agg(return_value=("return_cancellation_value","sum"),
        return_quantity=("Quantity",lambda x: -x.sum()), return_invoices=("InvoiceNo","nunique"))
    products = products.join(rev,how="outer").join(labels.rename("description"))
    fallback = mr.groupby("StockCode").Description.first()
    products["description"] = products.description.fillna(fallback)
    numeric = [x for x in products if x != "description"]
    products[numeric] = products[numeric].fillna(0)
    products["net_revenue"] = products.gross_revenue-products.return_value
    products["gross_revenue_contribution_pct"] = products.gross_revenue/products.gross_revenue.sum()*100
    products["return_value_rate_pct"] = products.return_value/products.gross_revenue.replace(0,np.nan)*100
    products = products.sort_values("gross_revenue",ascending=False).reset_index()

    active = customers.loc[customers.frequency_orders.gt(0)]
    repeat = int(active.frequency_orders.ge(2).sum())
    single = int(active.frequency_orders.eq(1).sum())
    sales = float(d.gross_purchase_revenue.sum())
    returns = float(d.return_cancellation_value.sum())
    adjustment = float(d.other_adjustment_revenue.sum())
    k = {"raw_rows_used":len(d), "valid_purchase_rows":len(p), "valid_customer_purchase_rows":len(cp),
        "gross_sales":sales, "return_cancellation_value":returns,
        "signed_adjustments":adjustment, "adjustment_deduction":-adjustment,
        "net_revenue":float(d.net_revenue.sum()),
        "valid_purchase_revenue":float(p.line_revenue.sum()),
        "valid_customer_purchase_revenue":float(cp.line_revenue.sum()),
        "total_valid_orders":len(orders), "valid_customer_purchase_orders":int(cp.InvoiceNo.nunique()),
        "unique_purchasing_customers":len(active), "unique_identified_ledger_customers":len(customers),
        "aov":divide(float(p.line_revenue.sum()),len(orders)),
        "customer_purchase_aov":divide(float(cp.line_revenue.sum()),int(cp.InvoiceNo.nunique())),
        "average_items_per_order":divide(float(p.Quantity.sum()),len(orders)),
        "revenue_per_customer":divide(float(cp.line_revenue.sum()),len(active)),
        "return_value_rate_pct":100*returns/sales,
        "return_invoice_to_purchase_order_pct":100*r.InvoiceNo.nunique()/len(orders),
        "return_row_rate_pct":100*len(r)/int((~d.is_duplicate).sum()),
        "repeat_customer_rate_pct":100*repeat/len(active),
        "repeat_customers":repeat, "single_purchase_customers":single,
        "average_purchase_frequency":float(active.frequency_orders.mean()),
        "recency_reference_date":str(reference.date()),
        "all_observed_unique_invoices":int(d.InvoiceNo.nunique()),
        "return_only_or_no_valid_purchase_customers":int(customers.frequency_orders.eq(0).sum()),
        "negative_without_c_rows":int((d.is_return & ~d.is_cancellation).sum()),
        "negative_without_c_signed_value":float(d.loc[d.is_return & ~d.is_cancellation,"line_revenue"].sum()),
        "duplicate_signed_value":float(d.loc[d.is_duplicate,"line_revenue"].sum()),
        "multi_country_valid_invoices":int(orders.country_count.gt(1).sum()),
        "multi_customer_valid_invoices":int(orders.customer_count.gt(1).sum()),
        "products_with_multiple_purchase_descriptions":int(products.description_variants.gt(1).sum())}
    complete = monthly.loc[~monthly.is_partial]
    k["best_complete_month"] = complete.loc[complete.net_revenue.idxmax(),"month"]
    k["weakest_complete_month"] = complete.loc[complete.net_revenue.idxmin(),"month"]
    k["strongest_observed_month"] = monthly.loc[monthly.net_revenue.idxmax(),"month"]
    k["top_country"] = country.iloc[0].Country
    k["top_product_code"] = products.iloc[0].StockCode
    k["top_product_description"] = products.iloc[0].description
    k["top_3_country_net_share_pct"] = float(country.head(3).revenue_contribution_pct.sum())
    count = max(1,int(np.ceil(len(active)*.01)))
    k["top_1pct_customer_count"] = count
    k["top_1pct_customer_purchase_revenue_share_pct"] = float(active.nlargest(count,"gross_revenue").gross_revenue.sum()/active.gross_revenue.sum()*100)
    return k, {"monthly":monthly, "countries":country, "products":products,
               "customer_features":customers, "valid_orders":orders.reset_index()}
