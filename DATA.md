# UCI Online Retail dataset

Source: [UCI Online Retail, dataset 352](https://archive.ics.uci.edu/dataset/352/online+retail).
Citation: Chen, D. (2015). Online Retail [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5BW33.
License: CC BY 4.0, as listed by UCI.

The user supplied the real workbook at data/raw/Online Retail.xlsx. The original download date was not supplied; no retrieval date is invented. See reports/metrics/data_quality_report.json for file size and before/after SHA-256 values.

The data describes a UK-based online retailer during December 2010–December 2011. Each row is a product or adjustment line, not necessarily a complete order.

| Field | Meaning |
| --- | --- |
| InvoiceNo | Invoice identifier; C prefix marks cancellations |
| StockCode | Product or adjustment code |
| Description | Product or adjustment description |
| Quantity | Signed line quantity |
| InvoiceDate | Transaction timestamp |
| UnitPrice | Unit price in pounds sterling |
| CustomerID | Customer identifier, where present |
| Country | Customer country |

Phase 2 measures actual schema, missingness, duplicate rows, dates, prices, and quantity/cancellation relationships before cleaning. Identifiers are loaded as strings. The source workbook stays unchanged; processed data is saved separately.

The intended later use includes revenue reconciliation, customer KPIs, repeat purchases, cohort retention, RFM, product and country performance, and customer concentration. Optional churn-risk / CLV work is deferred.

See [DATA_QUALITY.md](reports/DATA_QUALITY.md) for findings and defensible exclusion rules, and [PHASE2.md](docs/PHASE2.md) for reproduction and loading the processed purchase view. Raw and processed datasets are excluded from version control.
