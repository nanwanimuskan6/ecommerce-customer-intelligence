"""Regression checks using real UCI records from the generated ledger."""
from pathlib import Path
import hashlib
import json
import sys
import unittest
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ecommerce_customer_intelligence.data.loading import REQUIRED_COLUMNS, validate_columns
from ecommerce_customer_intelligence.data.cleaning import clean_transactions, customer_purchases, save_processed

class Phase2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((ROOT / "reports/metrics/data_quality_report.json").read_text(encoding="utf-8"))
        cls.ledger = pd.read_csv(ROOT / cls.report["processed_file"],
            dtype={"InvoiceNo": "string", "StockCode": "string", "CustomerID": "string"},
            parse_dates=["InvoiceDate"], keep_default_na=False, na_values=[""])
        cls.raw = cls.ledger[list(REQUIRED_COLUMNS)].copy()

    def test_required_columns(self):
        validate_columns(self.raw)
        for column in REQUIRED_COLUMNS:
            with self.subTest(column=column), self.assertRaisesRegex(ValueError, column):
                validate_columns(self.raw.drop(columns=[column]))

    def test_cancellation_identification(self):
        expected = self.raw.InvoiceNo.str.upper().str.startswith("C").fillna(False)
        np.testing.assert_array_equal(self.ledger.is_cancellation, expected)
        self.assertGreater(int(expected.sum()), 0)

    def test_negative_quantity_preserved(self):
        expected = self.raw.Quantity.lt(0)
        np.testing.assert_array_equal(self.ledger.is_return, expected)
        self.assertEqual(int(expected.sum()), self.report["numeric"]["Quantity"]["negative"])
        self.assertTrue((self.ledger.loc[expected, "is_customer_purchase"] == False).all())
        self.assertGreater(int((expected & ~self.ledger.is_cancellation).sum()), 0)

    def test_revenue_calculation_and_bridge(self):
        d = self.ledger
        np.testing.assert_allclose(d.line_revenue, d.Quantity * d.UnitPrice, rtol=1e-12, atol=1e-9)
        np.testing.assert_allclose(d.net_revenue,
            d.gross_purchase_revenue - d.return_cancellation_value + d.other_adjustment_revenue,
            rtol=1e-12, atol=1e-9)
        self.assertAlmostEqual(d.line_revenue.sum(),
            d.net_revenue.sum() + d.loc[d.is_duplicate, "line_revenue"].sum(), places=6)

    def test_raw_output_is_rejected_and_unchanged(self):
        raw_path = ROOT / "data/raw/Online Retail.xlsx"
        before = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "data/processed"):
            save_processed(self.ledger.head(), raw_path, ROOT)
        self.assertEqual(before, hashlib.sha256(raw_path.read_bytes()).hexdigest())
        self.assertEqual(before, self.report["source"]["sha256_before"])
        self.assertEqual(before, self.report["source"]["sha256_after"])

    def test_purchase_validity(self):
        p = customer_purchases(self.ledger)
        self.assertGreater(len(p), 0)
        self.assertEqual(len(p), self.report["cleaning"]["final_customer_analysis_rows"])
        self.assertTrue(p.CustomerID.notna().all())
        self.assertTrue(p.Quantity.gt(0).all() and p.UnitPrice.gt(0).all())
        self.assertTrue(np.isfinite(p.Quantity).all() and np.isfinite(p.UnitPrice).all())
        self.assertTrue(p.Description.astype("string").str.strip().fillna("").ne("").all())
        self.assertTrue(p.InvoiceDate.notna().all())
        self.assertFalse(p.InvoiceNo.str.upper().str.startswith("C").any())
        self.assertFalse(p.is_non_product.any())
        self.assertFalse(p.duplicated(subset=list(REQUIRED_COLUMNS)).any())

    def test_exact_duplicates_and_row_traceability(self):
        np.testing.assert_array_equal(self.ledger.is_duplicate, self.raw.duplicated())
        np.testing.assert_array_equal(self.ledger.source_excel_row, np.arange(2, len(self.raw)+2))
        self.assertEqual(len(self.raw), self.report["rows"])

    def test_cleaning_does_not_mutate_input(self):
        # These are actual source rows, never generated fixtures.
        sample = self.raw.iloc[:1000].copy(deep=True)
        snapshot = sample.copy(deep=True)
        clean_transactions(sample)
        pd.testing.assert_frame_equal(sample, snapshot)

    def test_exclusion_waterfall_reconciles(self):
        report = self.report["cleaning"]
        self.assertEqual(sum(s["excluded_rows"] for s in report["sequential_exclusions"]) +
                         report["final_customer_analysis_rows"], report["original_rows"])

    def test_missing_customers_and_adjustments_preserved(self):
        d = self.ledger
        self.assertEqual(int(d.CustomerID.isna().sum()), self.report["customers"]["missing_rows"])
        self.assertFalse(d.loc[d.CustomerID.isna(), "is_customer_purchase"].any())
        negative = d.UnitPrice.lt(0)
        self.assertGreater(int(negative.sum()), 0)
        np.testing.assert_allclose(d.loc[negative, "other_adjustment_revenue"],
                                   d.loc[negative, "line_revenue"])

if __name__ == "__main__":
    unittest.main()
