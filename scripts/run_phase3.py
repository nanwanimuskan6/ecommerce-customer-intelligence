"""Generate Phase 3 metrics, tables, findings and charts without rerunning cleaning."""
from pathlib import Path
import hashlib, json, sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from ecommerce_customer_intelligence.analytics.engine import load_ledger, build_tables
from ecommerce_customer_intelligence.analytics.charts import make_charts

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def table(d):
    d=d.copy()
    for col in d.select_dtypes("number"):
        d[col]=d[col].map(lambda x:f"{x:,.2f}" if pd.notna(x) else "N/A")
    return "| "+" | ".join(d.columns)+" |\n| "+" | ".join(["---"]*len(d.columns))+" |\n"+"\n".join(
        "| "+" | ".join(str(x).replace("|","/") for x in row)+" |" for row in d.itertuples(index=False,name=None))
def main():
    raw=ROOT/"data/raw/Online Retail.xlsx"; source=ROOT/"data/processed/transactions.csv.gz"
    before={"raw":digest(raw),"ledger":digest(source)}
    d=load_ledger(source); k,t=build_tables(d)
    for name,frame in t.items():
        frame.to_csv(ROOT/f"data/processed/{name}.csv",index=False)
    m=t["monthly"]; countries=t["countries"]; products=t["products"]
    uk=countries.loc[countries.Country.eq("United Kingdom")].iloc[0]
    best=m.loc[m.month.eq(k["best_complete_month"])].iloc[0]
    weak=m.loc[m.month.eq(k["weakest_complete_month"])].iloc[0]
    growth=m.dropna(subset=["net_revenue_growth_pct_complete"])
    up=growth.loc[growth.net_revenue_growth_pct_complete.idxmax()]
    down=growth.loc[growth.net_revenue_growth_pct_complete.idxmin()]
    nonuk=countries.loc[countries.Country.ne("United Kingdom")].head(3)
    insights=[
        f"UK net revenue is £{uk.net_revenue:,.2f}, {uk.revenue_contribution_pct:.2f}% of the accounting total; the top three countries contribute {k['top_3_country_net_share_pct']:.2f}%.",
        "Top non-UK markets by net revenue: "+", ".join(f"{r.Country} (£{r.net_revenue:,.2f})" for r in nonuk.itertuples())+".",
        f"{k['repeat_customers']:,} customers ({k['repeat_customer_rate_pct']:.2f}%) placed at least two valid orders; {k['single_purchase_customers']:,} placed one. The latter are a measurable follow-up audience, not proven churn.",
        f"Purchasing customers average {k['average_purchase_frequency']:.2f} valid orders and £{k['revenue_per_customer']:,.2f} gross merchandise purchase revenue.",
        f"The top {k['top_1pct_customer_count']} purchasers (rounded-up top 1%) account for {k['top_1pct_customer_purchase_revenue_share_pct']:.2f}% of identified purchase revenue, indicating customer concentration.",
        f"Returns/cancellations total £{k['return_cancellation_value']:,.2f}, {k['return_value_rate_pct']:.2f}% of accounting gross sales; this is a value ratio, not a matched-order return probability.",
        f"{k['negative_without_c_rows']:,} negative-quantity rows lack C prefixes and have combined signed value £{k['negative_without_c_signed_value']:,.2f}; they remain visible in the ledger.",
        f"The best complete observed month is {best.month} (£{best.net_revenue:,.2f}); the weakest is {weak.month} (£{weak.net_revenue:,.2f}). The short history cannot establish recurring seasonality.",
        f"The largest comparable monthly increase is {up.month} ({up.net_revenue_growth_pct_complete:.2f}%); the largest decline is {down.month} ({down.net_revenue_growth_pct_complete:.2f}%). Partial-month changes are excluded.",
        f"Top merchandise product {products.iloc[0].StockCode}, {products.iloc[0].description}, has £{products.iloc[0].gross_revenue:,.2f} gross purchase revenue ({products.iloc[0].gross_revenue_contribution_pct:.2f}% of merchandise sales).",
        f"{k['products_with_multiple_purchase_descriptions']:,} product codes have multiple purchase descriptions; aggregation by code prevents splitting their revenue across labels.",
        f"{k['return_only_or_no_valid_purchase_customers']:,} identified ledger customers have no valid merchandise purchase in the observed window; they remain in the feature table with zero frequency and missing purchase dates."
    ]
    make_charts(k,t,ROOT/"reports/figures")
    after={"raw":digest(raw),"ledger":digest(source)}
    if before != after: raise RuntimeError("Input checksum changed")
    payload={"kpis":k,"insights":insights,"integrity":{"before":before,"after":after,"unchanged":before==after},
             "input_columns":list(d.columns),"environment":{"python":sys.version.split()[0],"pandas":pd.__version__}}
    (ROOT/"reports/metrics/business_kpis.json").write_text(json.dumps(payload,indent=2,allow_nan=False),encoding="utf-8")
    reconciliation=pd.DataFrame([
        {"component":"Gross sales","signed_gbp":k["gross_sales"]},
        {"component":"Returns / cancellations","signed_gbp":-k["return_cancellation_value"]},
        {"component":"Other adjustments","signed_gbp":k["signed_adjustments"]},
        {"component":"Net revenue","signed_gbp":k["net_revenue"]}])
    reconciliation.to_csv(ROOT/"reports/metrics/revenue_reconciliation.csv",index=False)
    for name in ["monthly","countries","products"]:
        t[name].to_csv(ROOT/f"reports/metrics/{name}.csv",index=False)
    sections=[
        "# Phase 3 — Business KPI engine and revenue analysis",
        "## Reproduce",
        "Run from the project root: python -m pip install -r requirements.txt; then python scripts/run_phase3.py; "
        "then python -m unittest discover -s tests -v. Use the project's .venv Python executable. "
        "Phase 3 consumes the existing transactions.csv.gz and never reruns Phase 2 or changes its rules.",
        "## Revenue reconciliation and scope",
        table(reconciliation),
        "Gross sales sums Phase 2 gross_purchase_revenue: nonduplicate, positive-price, positive-quantity, noncancellation lines. "
        "Returns/cancellations sum return_cancellation_value: nonduplicate, positive-price negative-quantity or C-prefixed lines, "
        "with signed line values negated. Signed other_adjustment_revenue includes the negative-price bad-debt entries. "
        "Net revenue = gross sales - returns + signed adjustments (equivalently subtract the adjustment deduction). "
        "The bridge includes anonymous customers and service lines. Duplicate contributions are zero; their original signed value "
        f"is £{k['duplicate_signed_value']:,.2f}. Zero prices contribute zero, including all {k['negative_without_c_rows']:,} "
        "negative-quantity rows without C prefixes. Unusual rows remain in the Phase 2 ledger.",
        "Valid customer purchase revenue sums line_revenue only where is_customer_purchase is True. "
        "Valid merchandise purchases use is_valid_purchase, including anonymous customers. Neither purchase scope is interchangeable "
        "with accounting net revenue. Existing description and validity flags are reused unchanged.",
        "## KPI definitions",
        "Total valid orders = distinct InvoiceNo among is_valid_purchase rows; valid customer orders use is_customer_purchase. "
        "Unique purchasing customers excludes anonymous and return-only identities. AOV = valid merchandise purchase revenue / total valid orders. "
        "Customer AOV uses identified purchase revenue / identified purchase orders. Items per order uses purchase Quantity / valid orders. "
        "Revenue per customer = identified purchase revenue / distinct purchasing customers. Average frequency = identified purchase orders per purchaser.",
        "Return value rate = accounting returns / accounting gross sales. Return invoice ratio = distinct nonduplicate reversal invoices / valid purchase orders; "
        "return row rate = nonduplicate reversal rows / all nonduplicate rows. These ratios do not match reversals to originating orders. "
        "Overall repeat-customer rate = purchasers with at least two orders / all purchasers. Single-order versus repeat counts are mutually exclusive. "
        "Monthly new customers have their first observed valid purchase that month; monthly returning customers purchased in an earlier month. "
        "A new customer who repeats within the same month remains in the monthly new category.",
        "## Calculated executive KPIs",
        table(pd.DataFrame([{"metric":key,"value":str(value)} for key,value in k.items()])),
        "## Monthly results and period handling",
        table(m),
        "Boundary coverage is evaluated by calendar date, not midnight timestamps: December 2010 starts on day 1 and is treated as "
        "calendar-covered; December 2011 ends on day 9 and is partial. Calendar coverage does not prove source completeness. "
        "Observed growth is provided separately; comparable growth is null when either adjacent month is partial. "
        "First-period growth is undefined. Monthly customers are not additive across months.",
        "## Geographic results",
        table(countries.head(12)),
        "Country revenue and contribution use accounting net; country orders, customers and AOV use valid merchandise purchases. "
        "Country return rates use accounting return value / gross sales. Countries with zero denominators retain undefined ratios. "
        "Country customer counts are distinct within each country and need not sum to global customers.",
        "## Product results",
        table(products.head(10)[["StockCode","description","gross_revenue","quantity","purchase_orders","return_value","net_revenue"]]),
        "Product keys are StockCode, with the most frequent observed valid-purchase Description as label and lexical tie-breaking. "
        "Return-only codes use an observed return description. Exact Phase 2 service flags are excluded. "
        "Gross revenue, quantity, and distinct purchase orders support separate rankings in products.csv. "
        "Return invoices, returned units, return value and value ratio measure reversal activity; net subtracts these from merchandise gross. "
        "Descriptions are not treated as unique product IDs. Non-product detection remains the conservative Phase 2 list.",
        "### Most purchased by quantity",
        table(products.nlargest(10,"quantity")[["StockCode","description","quantity"]]),
        "### Most frequently purchased",
        table(products.nlargest(10,"purchase_orders")[["StockCode","description","purchase_orders"]]),
        "### Highest return/cancellation value",
        table(products.nlargest(10,"return_value")[["StockCode","description","return_value","return_invoices","return_quantity"]]),
        "## Customer feature contract",
        "customer_features.csv contains every identified ledger CustomerID once, renamed customer_id. "
        "first_purchase_date and last_purchase_date come from valid customer purchases. frequency_orders counts distinct valid invoices; "
        "total_quantity and gross_revenue sum those purchase lines. monetary_value aliases gross_revenue. "
        "return_count counts distinct identified positive-price merchandise reversal invoices; return_value sums their value. "
        "net_revenue = customer merchandise gross_revenue - merchandise return_value, excluding service/adjustment scope. "
        "Average order value and items per order divide gross and quantity by frequency. Recency and tenure are calendar days from "
        f"last and first purchase to reference date {k['recency_reference_date']} (one day after the maximum ledger date). "
        "Customers with no valid purchases retain zero frequency/gross/quantity, missing dates/recency/tenure/AOV, and any observed returns. "
        "No RFM scoring or segmentation is performed.",
        "## Computed business findings",
        "\n".join(f"{i+1}. {text}" for i,text in enumerate(insights)),
        "## Limitations",
        "Missing customer IDs exclude anonymous transactions from customer behavior but not revenue. First-observed purchases are left-censored, "
        "and customers near the end have less opportunity to repeat. Returns may relate to purchases outside the observation window. "
        "No order-level return matching, VAT/shipping financial normalization, or confirmed acquisition dates are available. "
        "The dataset supports historical patterns, not causal or recurring-seasonality claims. Customer features use the full observation window; "
        "future ML requires as-of-date rebuilding and leakage-safe splits. Values inherit source floating-point precision and are rounded only for display. "
        f"Valid invoices spanning multiple countries: {k['multi_country_valid_invoices']}; multiple identified customers: {k['multi_customer_valid_invoices']}.",
        "## Outputs",
        "Modules: analytics/engine.py and analytics/charts.py. Entry point: scripts/run_phase3.py. "
        "Machine-readable metrics: reports/metrics/business_kpis.json, revenue_reconciliation.csv, monthly.csv, countries.csv, products.csv. "
        "Reusable tables: data/processed/monthly.csv, countries.csv, products.csv, customer_features.csv, valid_orders.csv. "
        "Seven charts: reports/figures/*.png. Generated data/metrics remain gitignored. Raw and ledger SHA-256 hashes before/after are in business_kpis.json.",
        "## Charts",
        *[f"![{name.replace('_',' ').title()}](../reports/figures/{name}.png)" for name in
          ["monthly_net_revenue","monthly_orders","top_countries","top_products","revenue_reconciliation","new_vs_repeat_customers","customer_revenue_distribution"]],
        "Stopped after Phase 3. No segmentation, ML, dashboard, README polishing, deployment or push."
    ]
    (ROOT/"docs/PHASE3.md").write_text("\n\n".join(sections)+"\n",encoding="utf-8")
    print(json.dumps(k,indent=2))
if __name__=="__main__": main()
