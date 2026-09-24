"""Descriptive raw-data audit; no records are removed."""
import pandas as pd

def cancellation_mask(frame):
    return frame.InvoiceNo.astype("string").str.upper().str.startswith("C").fillna(False)

def audit_transactions(frame):
    n = len(frame)
    c = cancellation_mask(frame)
    negative = frame.Quantity.lt(0)
    dates = pd.to_datetime(frame.InvoiceDate, errors="coerce")
    descriptions = frame.Description.astype("string")
    # Review candidates only: these matches are not automatic deletion rules.
    unusual = descriptions.str.contains(
        r"(?i)postage|manual|discount|bank charges|amazonfee|adjust|damaged|"
        r"missing|check|found|lost|smashed|thrown|wet|crushed|debt", na=False)
    stats = {}
    for name in ("Quantity", "UnitPrice"):
        s = frame[name]
        stats[name] = {"min": s.min(), "max": s.max(), "median": s.median(),
                       "positive": int(s.gt(0).sum()), "negative": int(s.lt(0).sum()),
                       "zero": int(s.eq(0).sum())}
    return {
        "shape": list(frame.shape), "rows": n, "columns_count": len(frame.columns),
        "columns": list(frame.columns), "dtypes": frame.dtypes.astype(str).to_dict(),
        "first_5_rows": frame.head().to_dict("records"),
        "last_5_rows": frame.tail().to_dict("records"),
        "date_min": str(dates.min()), "date_max": str(dates.max()),
        "invalid_or_missing_dates": int(dates.isna().sum()),
        "unique_invoices": int(frame.InvoiceNo.nunique()),
        "unique_stock_codes": int(frame.StockCode.nunique()),
        "unique_identified_customers": int(frame.CustomerID.nunique()),
        "countries": int(frame.Country.nunique()),
        "missing_values": {col: {"count": int(frame[col].isna().sum()),
            "percentage": float(frame[col].isna().mean()*100)} for col in frame},
        "exact_duplicates": {"count": int(frame.duplicated().sum()),
                             "percentage": float(frame.duplicated().mean()*100)},
        "numeric": stats,
        "cancellations": {"rows": int(c.sum()), "unique_invoices": int(frame.loc[c, "InvoiceNo"].nunique())},
        "cancellation_quantity_relationship": {
            "c_and_negative": int((c & negative).sum()),
            "c_and_not_negative": int((c & ~negative).sum()),
            "negative_without_c": int((~c & negative).sum()),
            "neither": int((~c & ~negative).sum())},
        "customers": {"missing_rows": int(frame.CustomerID.isna().sum()),
                      "identified_rows": int(frame.CustomerID.notna().sum()),
                      "unique_identified": int(frame.CustomerID.nunique())},
        "description_review": {"matching_rows": int(unusual.sum()),
            "candidate_counts": descriptions[unusual].value_counts().to_dict(),
            "note": "Keyword candidates can include legitimate products; manual review required."}
    }
