"""Phase 3 checks against real Phase 2 transactions; no fabricated fixtures."""
from pathlib import Path
import sys, unittest, json, hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from ecommerce_customer_intelligence.analytics.engine import load_ledger, build_tables

class Phase3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=load_ledger(ROOT/"data/processed/transactions.csv.gz")
        cls.k,cls.t=build_tables(cls.d)
        cls.p=cls.d.loc[cls.d.is_valid_purchase]
        cls.cp=cls.d.loc[cls.d.is_customer_purchase]

    def test_reconciliation_against_signed_source(self):
        d=self.d; k=self.k
        expected=(d.loc[~d.is_duplicate,"Quantity"]*d.loc[~d.is_duplicate,"UnitPrice"]).sum()
        self.assertAlmostEqual(k["net_revenue"],expected,places=6)
        self.assertAlmostEqual(k["gross_sales"]-k["return_cancellation_value"]+
                               k["signed_adjustments"],expected,places=6)
        self.assertAlmostEqual(k["valid_customer_purchase_revenue"],
                               (self.cp.Quantity*self.cp.UnitPrice).sum(),places=6)

    def test_order_count_and_aov(self):
        invoices=set(self.p.InvoiceNo)
        self.assertEqual(self.k["total_valid_orders"],len(invoices))
        self.assertEqual(self.k["valid_customer_purchase_orders"],len(set(self.cp.InvoiceNo)))
        order_values=self.p.assign(value=self.p.Quantity*self.p.UnitPrice).groupby("InvoiceNo").value.sum()
        self.assertAlmostEqual(self.k["aov"],order_values.mean(),places=8)
        self.assertEqual(set(self.t["valid_orders"].InvoiceNo),invoices)

    def test_customer_aggregation(self):
        c=self.t["customer_features"].set_index("customer_id")
        grouped=self.cp.groupby("CustomerID")
        np.testing.assert_allclose(c.loc[grouped.size().index,"gross_revenue"],
                                   grouped.line_revenue.sum(),atol=1e-8)
        np.testing.assert_array_equal(c.loc[grouped.size().index,"frequency_orders"],
                                      grouped.InvoiceNo.nunique())
        self.assertAlmostEqual(c.gross_revenue.sum(),self.cp.line_revenue.sum(),places=6)
        np.testing.assert_allclose(c.net_revenue,c.gross_revenue-c.return_value,atol=1e-8)
        first=grouped.InvoiceDate.min()
        pd.testing.assert_series_equal(c.loc[first.index,"first_purchase_date"],first,check_names=False)
        self.assertEqual(self.k["unique_purchasing_customers"],self.cp.CustomerID.nunique())
        self.assertAlmostEqual(self.k["repeat_customer_rate_pct"],
                               100*grouped.InvoiceNo.nunique().ge(2).mean(),places=8)

    def test_monthly_aggregation_and_partial_period(self):
        m=self.t["monthly"]
        self.assertAlmostEqual(m.net_revenue.sum(),self.k["net_revenue"],places=6)
        self.assertEqual(m.orders.sum(),self.k["total_valid_orders"])
        expected=self.p.groupby(self.p.InvoiceDate.dt.strftime("%Y-%m")).InvoiceNo.nunique()
        np.testing.assert_array_equal(m.set_index("month").loc[expected.index,"orders"],expected)
        np.testing.assert_allclose(m.aov*m.orders,m.valid_purchase_revenue,atol=1e-8)
        self.assertTrue(m.iloc[-1].is_partial)
        self.assertFalse(m.iloc[0].is_partial)
        self.assertTrue(pd.isna(m.iloc[-1].net_revenue_growth_pct_complete))
        self.assertTrue(pd.isna(m.iloc[0].net_revenue_growth_pct_complete))
        self.assertEqual(m.new_customers.sum(),self.k["unique_purchasing_customers"])
        np.testing.assert_array_equal(m.new_customers+m.repeat_customers,m.unique_customers)

    def test_country_totals(self):
        c=self.t["countries"]
        self.assertAlmostEqual(c.net_revenue.sum(),self.k["net_revenue"],places=6)
        self.assertAlmostEqual(c.revenue_contribution_pct.sum(),100,places=8)
        self.assertEqual(c.orders.sum(),self.k["total_valid_orders"])
        defined=c.orders.gt(0)
        np.testing.assert_allclose(c.loc[defined,"aov"]*c.loc[defined,"orders"],
                                   c.loc[defined,"valid_purchase_revenue"],atol=1e-8)

    def test_product_aggregation(self):
        p=self.t["products"]
        self.assertAlmostEqual(p.gross_revenue.sum(),self.p.line_revenue.sum(),places=6)
        self.assertEqual(p.quantity.sum(),self.p.Quantity.sum())
        expected=self.p.groupby("StockCode").InvoiceNo.nunique()
        np.testing.assert_array_equal(p.set_index("StockCode").loc[expected.index,"purchase_orders"],expected)
        self.assertTrue(p.StockCode.is_unique)
        self.assertTrue(p.description.notna().all())

    def test_no_impossible_counts(self):
        for name,cols in {"monthly":["orders","unique_customers","new_customers","repeat_customers"],
            "countries":["orders","customers","return_invoices"],
            "products":["quantity","purchase_orders","return_invoices","return_quantity"],
            "customer_features":["frequency_orders","total_quantity","return_count","recency_days","customer_tenure_days"]}.items():
            for col in cols:
                values=self.t[name][col].dropna()
                self.assertTrue(values.ge(0).all(),f"{name}.{col}")
                np.testing.assert_allclose(values,values.round())

    def test_no_fabricated_entities_or_rows(self):
        self.assertEqual(len(self.d),json.loads((ROOT/"reports/metrics/data_quality_report.json").read_text())["rows"])
        self.assertEqual(set(self.t["customer_features"].customer_id),set(self.d.CustomerID.dropna()))
        self.assertTrue(set(self.t["products"].StockCode).issubset(set(self.d.StockCode)))
        self.assertEqual(set(self.t["countries"].Country),set(self.d.Country))
        self.assertTrue(set(self.t["monthly"].month).issubset(set(self.d.InvoiceDate.dt.strftime("%Y-%m"))))

    def test_saved_outputs_and_input_integrity(self):
        report=json.loads((ROOT/"reports/metrics/business_kpis.json").read_text())
        self.assertEqual(report["kpis"],self.k)
        for name,path in {"raw":"data/raw/Online Retail.xlsx","ledger":"data/processed/transactions.csv.gz"}.items():
            checksum=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
            self.assertEqual(checksum,report["integrity"]["before"][name])
            self.assertEqual(checksum,report["integrity"]["after"][name])
        for name,frame in self.t.items():
            saved=pd.read_csv(ROOT/f"data/processed/{name}.csv")
            self.assertEqual(len(saved),len(frame))
            self.assertEqual(list(saved.columns),list(frame.columns))

if __name__=="__main__": unittest.main()
