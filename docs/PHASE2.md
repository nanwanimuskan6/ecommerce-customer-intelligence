# Phase 2: loading, auditing and cleaning

## Reproduce

From the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/run_phase2.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The pipeline reads data/raw/Online Retail.xlsx once, audits all rows, adds flags and monetary fields, writes the ledger and reports, and checks the raw SHA-256 again. It never writes the Excel source. Required columns and the single-sheet assumption fail clearly. The output writer accepts only paths within data/processed.

## Load the processed data

```python
import pandas as pd

ledger = pd.read_csv(
    "data/processed/transactions.csv.gz",
    dtype={"InvoiceNo": "string", "StockCode": "string", "CustomerID": "string"},
    parse_dates=["InvoiceDate"],
    keep_default_na=False,
    na_values=[""],
)
purchases = ledger.loc[ledger["is_customer_purchase"]].copy()
```

One compressed CSV avoids storing a redundant purchase copy. It contains the original eight fields, source Excel row numbers, flags, and accounting components. The filtered purchases DataFrame is the analysis-ready identified-customer dataset. Loading the entire ledger without this filter is not a customer purchase dataset.

CSV readers must preserve identifier strings and parse dates, as shown. Missing source fields remain missing. Monetary fields retain numeric precision from the source; aggregate display rounding does not alter stored line values.

## Interpretation

- is_duplicate: repeated row across the eight original columns; first occurrence wins.
- is_cancellation: invoice starts with C, case-insensitive.
- is_return: negative quantity, including zero-price inventory adjustments.
- has_customer_id: nonblank identity; missing identities are never filled.
- is_valid_purchase: positive finite quantity and price, nonduplicate, not cancellation/return, nonblank description, valid date and keys, and not an exact listed service/adjustment description.
- is_customer_purchase: is_valid_purchase plus has_customer_id.
- line_revenue: source Quantity multiplied by UnitPrice on every row.
- gross_purchase_revenue: eligible positive sales after duplicate exclusion; includes anonymous and service lines for accounting.
- return_cancellation_value: negated signed value of eligible reversal rows after duplicate exclusion.
- other_adjustment_revenue: remaining signed amounts after duplicate exclusion.
- net_revenue: signed line value after duplicate exclusion.

The accounting scope differs deliberately from the narrower customer merchandise purchase view. The components reconcile without discarding anonymous customers, service charges, or negative-price adjustments. No returns are matched to original orders in this phase.

Exact duplicate exclusion is a declared assumption because source line identifiers are unavailable. Description keyword candidates are diagnostic, not fuzzy deletion rules. The precise service list and exclusion waterfall are documented in reports/DATA_QUALITY.md. Raw overlapping issue counts must not be added together.

Tests use actual processed UCI source records and standard-library unittest. No synthetic dataset or test transactions are generated.

No RFM, cohorts, churn model, CLV, product/country analytics, or dashboard has been implemented.
