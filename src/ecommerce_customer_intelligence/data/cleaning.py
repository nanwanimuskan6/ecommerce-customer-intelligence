"""Flag every source row and expose a strict customer purchase view."""
from pathlib import Path
import numpy as np
import pandas as pd
from .loading import validate_columns
from .audit import cancellation_mask

# Exact audited service/adjustment descriptions, not fuzzy product-name matches.
NON_PRODUCT_DESCRIPTIONS = frozenset({
    "POSTAGE", "DOTCOM POSTAGE", "MANUAL", "DISCOUNT", "BANK CHARGES",
    "AMAZONFEE", "ADJUST BAD DEBT",
})

def clean_transactions(raw):
    validate_columns(raw)
    frame = raw.copy(deep=True)
    frame.insert(0, "source_excel_row", np.arange(2, len(frame) + 2))
    frame["is_duplicate"] = raw.duplicated(keep="first").to_numpy()
    frame["is_cancellation"] = cancellation_mask(raw)
    frame["is_return"] = raw.Quantity.lt(0)
    frame["has_customer_id"] = raw.CustomerID.astype("string").str.strip().fillna("").ne("")
    frame["has_valid_description"] = raw.Description.astype("string").str.strip().fillna("").ne("")
    frame["is_non_product"] = raw.Description.astype("string").str.strip().str.upper().isin(NON_PRODUCT_DESCRIPTIONS)
    frame["has_valid_date"] = pd.to_datetime(raw.InvoiceDate, errors="coerce").notna()
    frame["has_transaction_keys"] = (
        raw.InvoiceNo.astype("string").str.strip().fillna("").ne("") &
        raw.StockCode.astype("string").str.strip().fillna("").ne(""))
    frame["has_valid_price"] = raw.UnitPrice.gt(0) & np.isfinite(raw.UnitPrice)
    frame["has_finite_quantity"] = np.isfinite(raw.Quantity)
    frame["line_revenue"] = raw.Quantity * raw.UnitPrice
    frame["is_valid_purchase"] = (
        ~frame.is_duplicate & ~frame.is_cancellation & ~frame.is_return &
        raw.Quantity.gt(0) & frame.has_finite_quantity & frame.has_valid_price &
        frame.has_valid_description & ~frame.is_non_product &
        frame.has_valid_date & frame.has_transaction_keys)
    frame["is_customer_purchase"] = frame.is_valid_purchase & frame.has_customer_id

    # Accounting components keep anonymous and service lines; behavioral filters
    # must not silently redefine total retail revenue.
    base = ~frame.is_duplicate & frame.has_valid_price & frame.has_finite_quantity
    sale = base & raw.Quantity.gt(0) & ~frame.is_cancellation
    reversal = base & (frame.is_return | frame.is_cancellation)
    frame["gross_purchase_revenue"] = frame.line_revenue.where(sale, 0.0)
    frame["return_cancellation_value"] = (-frame.line_revenue).where(reversal, 0.0)
    frame["other_adjustment_revenue"] = frame.line_revenue.where(~frame.is_duplicate & ~sale & ~reversal, 0.0)
    frame["net_revenue"] = frame.line_revenue.where(~frame.is_duplicate, 0.0)
    return frame

def customer_purchases(ledger):
    return ledger.loc[ledger.is_customer_purchase].copy()

def cleaning_summary(ledger):
    # Sequential, mutually exclusive exclusions: totals add to original rows.
    remaining = pd.Series(True, index=ledger.index)
    steps = []
    for reason, mask in (
        ("exact_duplicates", ledger.is_duplicate),
        ("missing_customer_id", ~ledger.has_customer_id),
        ("cancellation_or_return", ledger.is_cancellation | ledger.is_return),
        ("invalid_price", ~ledger.has_valid_price),
        ("invalid_description", ~ledger.has_valid_description),
        ("non_product_service_or_adjustment", ledger.is_non_product),
        ("invalid_quantity", ~ledger.has_finite_quantity | ledger.Quantity.le(0)),
        ("invalid_date_or_keys", ~ledger.has_valid_date | ~ledger.has_transaction_keys),
    ):
        removed = remaining & mask
        steps.append({"reason": reason, "excluded_rows": int(removed.sum())})
        remaining &= ~mask
    assert remaining.equals(ledger.is_customer_purchase)
    monetary = ["line_revenue", "gross_purchase_revenue",
                "return_cancellation_value", "other_adjustment_revenue", "net_revenue"]
    return {"original_rows": len(ledger), "ledger_rows": len(ledger),
            "sequential_exclusions": steps,
            "final_customer_analysis_rows": int(ledger.is_customer_purchase.sum()),
            "all_customer_or_anonymous_valid_purchase_rows": int(ledger.is_valid_purchase.sum()),
            "money_gbp": {col: float(ledger[col].sum()) for col in monetary},
            "duplicate_signed_value": float(ledger.loc[ledger.is_duplicate, "line_revenue"].sum()),
            "note": "Ledger preserves all raw rows. Exclusions apply to the customer purchase view only."}

def save_processed(ledger, output, project_root):
    root = Path(project_root).resolve()
    target = Path(output).resolve()
    processed = (root / "data/processed").resolve()
    if not target.is_relative_to(processed) or target.suffix not in {".csv", ".gz"}:
        raise ValueError("Output must be a CSV inside this project's data/processed directory.")
    target.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(target, index=False, compression="infer")
