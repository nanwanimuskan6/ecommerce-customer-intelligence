# E-Commerce Customer Intelligence & Retention Analytics

A portfolio project using real UCI Online Retail transactions to build reproducible customer intelligence and retention analysis.

## Current status

**Phase 2 complete:** real workbook loading, schema validation, a raw-data quality audit, a flagged cleaning pipeline, a compressed transaction ledger, and tests. The original workbook is preserved and verified by SHA-256. No synthetic data is used.

Read [the measured audit report](reports/DATA_QUALITY.md), [dataset documentation](DATA.md), and [the Phase 2 reproduction guide](docs/PHASE2.md).

## Why this dataset?

[UCI Online Retail](https://archive.ics.uci.edu/dataset/352/online+retail) contains transaction-level retail data with customer IDs, timestamps, products, quantities, prices, and countries. These fields support future customer purchase, retention, product, and geographic analysis. Cancellation invoice prefixes and quantity signs allow reversal and adjustment investigation; Phase 2 checks their relationship before applying rules.

## Structure

```text
data/raw/                          Original workbook (gitignored)
data/processed/                    Flagged transactions.csv.gz (gitignored)
src/ecommerce_customer_intelligence/data/
    loading.py                     Excel loading and required schema
    audit.py                       Raw quality statistics
    cleaning.py                    Flags, purchase view, accounting fields
scripts/run_phase2.py               Reproduce ledger and audit reports
reports/DATA_QUALITY.md             Readable findings and cleaning rules
reports/metrics/data_quality_report.json
tests/test_phase2.py                Tests using real UCI records
docs/PHASE2.md                      Usage and output interpretation
notebooks/                         Reserved
reports/figures/                    Reserved
app/                               Reserved
```

## Run Phase 2

From this project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/run_phase2.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The real workbook must exist at data/raw/Online Retail.xlsx. Dependencies are pandas and openpyxl; tests use unittest. The JSON report records runtime versions.

The processed file preserves all raw rows with flags. **Filter is_customer_purchase == True for customer purchase analysis.** See the documented CSV loading recipe before using it. Returns, anonymous transactions, duplicates, and adjustments remain traceable.

## Roadmap

1. Phase 1 — complete: scaffold and dataset acquisition plan.
2. Phase 2 — complete: load, audit, clean, preserve accounting components, and test.
3. Future customer analysis: customer KPIs, repeat purchase rate, cohort retention, RFM segmentation, customer concentration.
4. Future commercial analysis: product and country performance and fuller revenue interpretation.
5. Future presentation: professional charts, findings, and Streamlit dashboard.
6. Optional extension: churn-risk / CLV, subject to suitable assumptions and validation.

Work stops after Phase 2. All later roadmap items remain unimplemented.
