"""Run the full audit and cleaning pipeline against the real workbook."""
from pathlib import Path
import hashlib
import json
import sys
import pandas as pd
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ecommerce_customer_intelligence.data.loading import load_raw_transactions
from ecommerce_customer_intelligence.data.audit import audit_transactions, cancellation_mask
from ecommerce_customer_intelligence.data.cleaning import clean_transactions, cleaning_summary, save_processed

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def json_ready(value):
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(v) for v in value]
    if value is pd.NA or value is pd.NaT:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat(sep=" ")
    return value

def markdown_table(frame):
    def cell(x):
        return str(x).replace("|", "\\|").replace("\n", " ")
    return "\n".join([
        "| " + " | ".join(map(cell, frame.columns)) + " |",
        "| " + " | ".join("---" for _ in frame.columns) + " |",
        *["| " + " | ".join(map(cell, row)) + " |" for row in frame.itertuples(index=False, name=None)]
    ])

def main():
    raw_path = ROOT / "data/raw/Online Retail.xlsx"
    before = digest(raw_path)
    raw = load_raw_transactions(raw_path)
    audit = audit_transactions(raw)  # Audit precedes every exclusion.
    c = cancellation_mask(raw)
    exception = raw.loc[raw.Quantity.lt(0) & ~c]
    audit["cancellation_quantity_relationship"]["negative_without_c_price_counts"] = exception.UnitPrice.value_counts().to_dict()
    audit["negative_price_records"] = raw.loc[raw.UnitPrice.lt(0)].to_dict("records")
    ledger = clean_transactions(raw)
    audit["cleaning"] = cleaning_summary(ledger)
    output = ROOT / "data/processed/transactions.csv.gz"
    save_processed(ledger, output, ROOT)
    after = digest(raw_path)
    if before != after:
        raise RuntimeError("Raw workbook checksum changed.")
    audit["source"] = {"path": "data/raw/Online Retail.xlsx", "bytes": raw_path.stat().st_size,
        "sha256_before": before, "sha256_after": after, "unchanged": before == after,
        "url": "https://archive.ics.uci.edu/dataset/352/online+retail"}
    audit["environment"] = {"python": sys.version.split()[0], "pandas": pd.__version__, "openpyxl": openpyxl.__version__}
    audit["processed_file"] = str(output.relative_to(ROOT)).replace("\\", "/")
    audit = json_ready(audit)
    (ROOT / "reports/metrics/data_quality_report.json").write_text(
        json.dumps(audit, indent=2, allow_nan=False), encoding="utf-8")

    rel = audit["cancellation_quantity_relationship"]
    summary = audit["cleaning"]
    missing = pd.DataFrame(audit["missing_values"]).T.reset_index(names="Column")
    numeric = pd.DataFrame(audit["numeric"]).T.reset_index(names="Column")
    candidates = pd.Series(audit["description_review"]["candidate_counts"]).head(30).rename_axis("Description").reset_index(name="Rows")
    sections = [
        "# Data quality audit — UCI Online Retail",
        "Generated from the real workbook by scripts/run_phase2.py. All raw statistics precede cleaning.",
        "## Source and integrity",
        f"File: {audit['source']['path']}; size: {audit['source']['bytes']:,} bytes. SHA-256 before and after: {before}. Raw file unchanged.",
        "Source: https://archive.ics.uci.edu/dataset/352/online+retail. Source rows are invoice lines, not whole orders.",
        "## Dataset",
        f"Shape: {raw.shape}. Date range: {audit['date_min']} to {audit['date_max']}. "
        f"Unique invoices: {audit['unique_invoices']:,}; stock codes: {audit['unique_stock_codes']:,}; "
        f"identified customers: {audit['unique_identified_customers']:,}; countries: {audit['countries']:,}. "
        f"Invalid or missing dates: {audit['invalid_or_missing_dates']:,}.",
        markdown_table(pd.DataFrame({"Column": raw.columns, "Loaded dtype": raw.dtypes.astype(str).values})),
        "Identifiers are loaded as strings to preserve cancellation prefixes. Original values are not imputed.",
        "### First five rows", markdown_table(raw.head()),
        "### Last five rows", markdown_table(raw.tail()),
        "## Missing values", markdown_table(missing),
        f"Identified-customer rows: {audit['customers']['identified_rows']:,}. No customer IDs are invented.",
        "## Exact duplicates",
        f"{audit['exact_duplicates']['count']:,} repeated rows ({audit['exact_duplicates']['percentage']:.6f}%). "
        "Exact means equality across all eight loaded source columns. The first occurrence is retained for analysis; "
        "later copies remain in the ledger with is_duplicate=True. Identical lines could represent genuine repetitions, "
        "so this is an explicit analytical assumption, not proof of a source-system error.",
        "## Quantity and price", markdown_table(numeric),
        "### Negative-price records", markdown_table(raw.loc[raw.UnitPrice.lt(0)]),
        "## Cancellations and negative quantities",
        f"C-prefixed rows: {audit['cancellations']['rows']:,}, across {audit['cancellations']['unique_invoices']:,} invoices. "
        f"C and negative: {rel['c_and_negative']:,}; C without negative: {rel['c_and_not_negative']:,}; "
        f"negative without C: {rel['negative_without_c']:,}; neither: {rel['neither']:,}. "
        "All cancellation rows are negative in this workbook, but the reverse is not true.",
        f"Prices on negative-quantity rows without C: {rel['negative_without_c_price_counts']}. "
        "These require separate inventory/adjustment interpretation. is_return denotes a negative quantity; "
        "it does not assert that a physical return has been verified or matched to its original purchase.",
        "## Description review", markdown_table(candidates),
        "Keyword matches are review candidates only: legitimate names such as BROWN CHECK CAT DOORSTOP also match. "
        "Only blank descriptions and exact audited service/adjustment descriptions are excluded from purchase behavior. "
        "The exact non-product list is POSTAGE, DOTCOM POSTAGE, MANUAL, DISCOUNT, BANK CHARGES, AMAZONFEE, ADJUST BAD DEBT. "
        "This conservative list is not an exhaustive product taxonomy. Full candidate counts are in the JSON report.",
        "## Cleaning rules",
        "The ledger preserves every original row and field, adds source_excel_row, and marks exclusions instead of discarding evidence. "
        "is_cancellation means InvoiceNo begins with C (case-insensitive); is_return means Quantity < 0; "
        "has_customer_id means a nonblank identifier. is_valid_purchase requires a nonduplicate, noncancellation, "
        "positive finite quantity and price, nonblank description, no listed service/adjustment description, "
        "valid date and invoice/product keys. is_customer_purchase additionally requires a customer ID. "
        "No clipping of extreme values, imputation, return matching, or fabricated values is performed.",
        "### Sequential customer-purchase exclusions",
        markdown_table(pd.DataFrame(summary["sequential_exclusions"])),
        f"Original rows: {summary['original_rows']:,}. Final customer-analysis rows: {summary['final_customer_analysis_rows']:,}. "
        "The exclusions above are mutually exclusive in the displayed order. Raw audit counts overlap and therefore differ "
        "from later waterfall counts. Duplicate rows are excluded from analytical views, not physically erased.",
        "## Revenue preservation",
        "line_revenue = Quantity * UnitPrice on every row. After duplicate exclusion, positive-price positive-quantity "
        "noncancellation lines contribute to gross_purchase_revenue; positive-price reversal lines contribute their "
        "negated signed value to return_cancellation_value. Other signed values remain in other_adjustment_revenue. "
        "net_revenue = gross_purchase_revenue - return_cancellation_value + other_adjustment_revenue. "
        "Anonymous and service lines remain in this accounting bridge. Negative-price adjustments are disclosed, "
        "not silently counted as ordinary sales or dropped. These are transaction-value checks, not a claim of "
        "audited financial-statement revenue. Stored line values are not rounded; display totals use two decimals.",
        markdown_table(pd.DataFrame([{"Measure": k, "GBP": f"{v:,.2f}"} for k,v in summary["money_gbp"].items()])),
        f"Duplicate signed value excluded from net: GBP {summary['duplicate_signed_value']:,.2f}.",
        "## Output and reproduction",
        f"One compressed CSV: {audit['processed_file']} ({len(ledger):,} ledger rows). "
        "Select is_customer_purchase == True for customer purchase analysis; do not treat the whole ledger as clean purchases. "
        "Use the documented loading recipe in docs/PHASE2.md. The raw workbook and processed CSV remain gitignored.",
        "Run .\\.venv\\Scripts\\python.exe scripts/run_phase2.py, then "
        ".\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v. "
        "Tests use the actual processed source records; no synthetic fixtures are generated.",
        "Phase 2 ends here. RFM, cohorts, CLV, ML and Streamlit are not implemented."
    ]
    (ROOT / "reports/DATA_QUALITY.md").write_text("\n\n".join(sections)+"\n", encoding="utf-8")
    print(json.dumps({"dataset": {k:audit[k] for k in ("shape","date_min","date_max","unique_invoices","unique_identified_customers","countries")},
                      "cleaning": summary, "raw_unchanged": before == after}, indent=2))
if __name__ == "__main__":
    main()
