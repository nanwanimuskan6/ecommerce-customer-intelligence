"""Read the original workbook without changing source records."""
from pathlib import Path
import pandas as pd

REQUIRED_COLUMNS = ("InvoiceNo", "StockCode", "Description", "Quantity",
                    "InvoiceDate", "UnitPrice", "CustomerID", "Country")

def validate_columns(frame):
    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

def load_raw_transactions(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Workbook missing or empty: {path}")
    with pd.ExcelFile(path, engine="openpyxl") as workbook:
        if len(workbook.sheet_names) != 1:
            raise ValueError(f"Expected one data sheet; inspect: {workbook.sheet_names}")
        frame = pd.read_excel(workbook, sheet_name=workbook.sheet_names[0],
                              dtype={"InvoiceNo": "string", "StockCode": "string",
                                     "CustomerID": "string"})
    validate_columns(frame)
    return frame
