# Data quality audit — UCI Online Retail

Generated from the real workbook by scripts/run_phase2.py. All raw statistics precede cleaning.

## Source and integrity

File: data/raw/Online Retail.xlsx; size: 23,715,628 bytes. SHA-256 before and after: 675b746d9a50be7fbe09d60930ef50d1f6af4d49b2eef9f289f91823aa0e738e. Raw file unchanged.

Source: https://archive.ics.uci.edu/dataset/352/online+retail. Source rows are invoice lines, not whole orders.

## Dataset

Shape: (541909, 8). Date range: 2010-12-01 08:26:00 to 2011-12-09 12:50:00. Unique invoices: 25,900; stock codes: 4,070; identified customers: 4,372; countries: 38. Invalid or missing dates: 0.

| Column | Loaded dtype |
| --- | --- |
| InvoiceNo | string |
| StockCode | string |
| Description | object |
| Quantity | int64 |
| InvoiceDate | datetime64[us] |
| UnitPrice | float64 |
| CustomerID | string |
| Country | str |

Identifiers are loaded as strings to preserve cancellation prefixes. Original values are not imputed.

### First five rows

| InvoiceNo | StockCode | Description | Quantity | InvoiceDate | UnitPrice | CustomerID | Country |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 536365 | 85123A | WHITE HANGING HEART T-LIGHT HOLDER | 6 | 2010-12-01 08:26:00 | 2.55 | 17850 | United Kingdom |
| 536365 | 71053 | WHITE METAL LANTERN | 6 | 2010-12-01 08:26:00 | 3.39 | 17850 | United Kingdom |
| 536365 | 84406B | CREAM CUPID HEARTS COAT HANGER | 8 | 2010-12-01 08:26:00 | 2.75 | 17850 | United Kingdom |
| 536365 | 84029G | KNITTED UNION FLAG HOT WATER BOTTLE | 6 | 2010-12-01 08:26:00 | 3.39 | 17850 | United Kingdom |
| 536365 | 84029E | RED WOOLLY HOTTIE WHITE HEART. | 6 | 2010-12-01 08:26:00 | 3.39 | 17850 | United Kingdom |

### Last five rows

| InvoiceNo | StockCode | Description | Quantity | InvoiceDate | UnitPrice | CustomerID | Country |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 581587 | 22613 | PACK OF 20 SPACEBOY NAPKINS | 12 | 2011-12-09 12:50:00 | 0.85 | 12680 | France |
| 581587 | 22899 | CHILDREN'S APRON DOLLY GIRL  | 6 | 2011-12-09 12:50:00 | 2.1 | 12680 | France |
| 581587 | 23254 | CHILDRENS CUTLERY DOLLY GIRL  | 4 | 2011-12-09 12:50:00 | 4.15 | 12680 | France |
| 581587 | 23255 | CHILDRENS CUTLERY CIRCUS PARADE | 4 | 2011-12-09 12:50:00 | 4.15 | 12680 | France |
| 581587 | 22138 | BAKING SET 9 PIECE RETROSPOT  | 3 | 2011-12-09 12:50:00 | 4.95 | 12680 | France |

## Missing values

| Column | count | percentage |
| --- | --- | --- |
| InvoiceNo | 0.0 | 0.0 |
| StockCode | 0.0 | 0.0 |
| Description | 1454.0 | 0.2683107311375157 |
| Quantity | 0.0 | 0.0 |
| InvoiceDate | 0.0 | 0.0 |
| UnitPrice | 0.0 | 0.0 |
| CustomerID | 135080.0 | 24.926694334288598 |
| Country | 0.0 | 0.0 |

Identified-customer rows: 406,829. No customer IDs are invented.

## Exact duplicates

5,268 repeated rows (0.972119%). Exact means equality across all eight loaded source columns. The first occurrence is retained for analysis; later copies remain in the ledger with is_duplicate=True. Identical lines could represent genuine repetitions, so this is an explicit analytical assumption, not proof of a source-system error.

## Quantity and price

| Column | min | max | median | positive | negative | zero |
| --- | --- | --- | --- | --- | --- | --- |
| Quantity | -80995.0 | 80995.0 | 3.0 | 531285.0 | 10624.0 | 0.0 |
| UnitPrice | -11062.06 | 38970.0 | 2.08 | 539392.0 | 2.0 | 2515.0 |

### Negative-price records

| InvoiceNo | StockCode | Description | Quantity | InvoiceDate | UnitPrice | CustomerID | Country |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A563186 | B | Adjust bad debt | 1 | 2011-08-12 14:51:00 | -11062.06 | <NA> | United Kingdom |
| A563187 | B | Adjust bad debt | 1 | 2011-08-12 14:52:00 | -11062.06 | <NA> | United Kingdom |

## Cancellations and negative quantities

C-prefixed rows: 9,288, across 3,836 invoices. C and negative: 9,288; C without negative: 0; negative without C: 1,336; neither: 531,285. All cancellation rows are negative in this workbook, but the reverse is not true.

Prices on negative-quantity rows without C: {'0.0': 1336}. These require separate inventory/adjustment interpretation. is_return denotes a negative quantity; it does not assert that a physical return has been verified or matched to its original purchase.

## Description review

| Description | Rows |
| --- | --- |
| POSTAGE | 1252 |
| DOTCOM POSTAGE | 709 |
| Manual | 572 |
| check | 159 |
| BROWN CHECK CAT DOORSTOP  | 139 |
| Discount | 77 |
| SUNSET CHECK HAMMOCK | 62 |
| PAIR PADDED HANGERS PINK CHECK | 43 |
| damaged | 43 |
| Bank Charges | 37 |
| found | 25 |
| adjustment | 16 |
| Damaged | 14 |
| thrown away | 9 |
| Found | 8 |
| BLUE CHECK BAG W HANDLE 34X20CM | 6 |
| wet damaged | 5 |
| smashed | 4 |
| BLUE CRUSOE CHECK LAMPSHADE | 3 |
| missing | 3 |
| Adjust bad debt | 3 |
| CHECK | 3 |
| wet pallet | 3 |
| reverse 21/5/10 adjustment | 2 |
| Adjustment | 2 |
| crushed | 2 |
| wet/rusty | 2 |
| printing smudges/thrown away | 2 |
| ?missing | 2 |
| taig adjust | 2 |

Keyword matches are review candidates only: legitimate names such as BROWN CHECK CAT DOORSTOP also match. Only blank descriptions and exact audited service/adjustment descriptions are excluded from purchase behavior. The exact non-product list is POSTAGE, DOTCOM POSTAGE, MANUAL, DISCOUNT, BANK CHARGES, AMAZONFEE, ADJUST BAD DEBT. This conservative list is not an exhaustive product taxonomy. Full candidate counts are in the JSON report.

## Cleaning rules

The ledger preserves every original row and field, adds source_excel_row, and marks exclusions instead of discarding evidence. is_cancellation means InvoiceNo begins with C (case-insensitive); is_return means Quantity < 0; has_customer_id means a nonblank identifier. is_valid_purchase requires a nonduplicate, noncancellation, positive finite quantity and price, nonblank description, no listed service/adjustment description, valid date and invoice/product keys. is_customer_purchase additionally requires a customer ID. No clipping of extreme values, imputation, return matching, or fabricated values is performed.

### Sequential customer-purchase exclusions

| reason | excluded_rows |
| --- | --- |
| exact_duplicates | 5268 |
| missing_customer_id | 135037 |
| cancellation_or_return | 8872 |
| invalid_price | 40 |
| invalid_description | 0 |
| non_product_service_or_adjustment | 1406 |
| invalid_quantity | 0 |
| invalid_date_or_keys | 0 |

Original rows: 541,909. Final customer-analysis rows: 391,286. The exclusions above are mutually exclusive in the displayed order. Raw audit counts overlap and therefore differ from later waterfall counts. Duplicate rows are excluded from analytical views, not physically erased.

## Revenue preservation

line_revenue = Quantity * UnitPrice on every row. After duplicate exclusion, positive-price positive-quantity noncancellation lines contribute to gross_purchase_revenue; positive-price reversal lines contribute their negated signed value to return_cancellation_value. Other signed values remain in other_adjustment_revenue. net_revenue = gross_purchase_revenue - return_cancellation_value + other_adjustment_revenue. Anonymous and service lines remain in this accounting bridge. Negative-price adjustments are disclosed, not silently counted as ordinary sales or dropped. These are transaction-value checks, not a claim of audited financial-statement revenue. Stored line values are not rounded; display totals use two decimals.

| Measure | GBP |
| --- | --- |
| line_revenue | 9,747,747.93 |
| gross_purchase_revenue | 10,642,110.80 |
| return_cancellation_value | 893,979.73 |
| other_adjustment_revenue | -22,124.12 |
| net_revenue | 9,726,006.95 |

Duplicate signed value excluded from net: GBP 21,740.98.

## Output and reproduction

One compressed CSV: data/processed/transactions.csv.gz (541,909 ledger rows). Select is_customer_purchase == True for customer purchase analysis; do not treat the whole ledger as clean purchases. Use the documented loading recipe in docs/PHASE2.md. The raw workbook and processed CSV remain gitignored.

Run .\.venv\Scripts\python.exe scripts/run_phase2.py, then .\.venv\Scripts\python.exe -m unittest discover -s tests -v. Tests use the actual processed source records; no synthetic fixtures are generated.

Phase 2 ends here. RFM, cohorts, CLV, ML and Streamlit are not implemented.

## Verification

Executed unittest discovery after generating the outputs: 10 tests passed, 0 failed. Checks cover required columns, cancellation and return flags, revenue calculations, exclusion reconciliation, purchase validity, source-row preservation, missing identities, input immutability, and rejection of writes to the raw workbook. All tests use real UCI records.

