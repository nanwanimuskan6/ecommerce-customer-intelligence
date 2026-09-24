"""Target assessment tests use only observed project records."""
from pathlib import Path
import sys,json,hashlib,unittest
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from ecommerce_customer_intelligence.analytics.target_selection import purchase_occasions
from ecommerce_customer_intelligence.analytics.engine import load_ledger

class Phase5ATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=load_ledger(ROOT/"data/processed/transactions.csv.gz")
        cls.o=purchase_occasions(cls.d)
        cls.s=pd.read_csv(ROOT/"data/processed/phase5a_candidate_snapshots.csv.gz",
            dtype={"customer_id":"string"},parse_dates=["snapshot_date","target_end","first_observed_purchase",
                "last_historical_purchase","next_observed_purchase"])
        cls.k=json.loads((ROOT/"reports/metrics/phase5a_target_selection.json").read_text())
        cls.c=pd.read_csv(ROOT/"reports/metrics/phase5a_horizon_comparison.csv")

    def test_invoice_lines_are_not_occasions(self):
        p=self.d.loc[self.d.is_customer_purchase]
        self.assertEqual(len(self.o),p.groupby(["CustomerID","InvoiceNo"]).ngroups)
        self.assertFalse(self.o.duplicated(["CustomerID","InvoiceNo"]).any())
        self.assertEqual(self.k["eligible_customers"],p.CustomerID.nunique())
        self.assertEqual(self.k["purchase_occasions"],len(self.o))

    def test_gap_statistics_match_prior_real_gaps(self):
        g=self.o.groupby("CustomerID").InvoiceDate.diff().dt.total_seconds().div(86400).dropna()
        self.assertTrue(g.ge(0).all())
        self.assertEqual(len(g),self.k["completed_interpurchase_intervals"])
        self.assertAlmostEqual(g.median(),self.k["median_days"])
        self.assertAlmostEqual(g.quantile(.75),self.k["p75_days"])
        previous=json.loads((ROOT/"reports/metrics/customer_intelligence.json").read_text())
        self.assertAlmostEqual(g.median(),previous["lifecycle"]["median_interpurchase_days"])
        for h,pct in self.k["coverage_pct"].items():
            self.assertAlmostEqual(g.le(int(h)).mean()*100,pct)

    def test_censoring_and_target_bounds(self):
        end=self.d.InvoiceDate.max()
        expected=self.s.target_end.le(end)
        np.testing.assert_array_equal(self.s.full_followup,expected)
        self.assertTrue(self.s.loc[~expected,"target"].isna().all())
        self.assertTrue(self.s.loc[expected,"target"].isin([0,1]).all())
        self.assertTrue((self.s.target_end-self.s.snapshot_date).dt.days.eq(self.s.horizon_days).all())

    def test_targets_against_future_transactions(self):
        # Independently count actual orders in each half-open target window.
        arrays={cid:g.InvoiceDate.to_numpy(dtype="datetime64[ns]") for cid,g in self.o.groupby("CustomerID")}
        for cid,g in self.s.loc[self.s.full_followup].groupby("customer_id"):
            times=arrays[cid]
            left=np.searchsorted(times,g.snapshot_date.to_numpy(dtype="datetime64[ns]"),side="left")
            right=np.searchsorted(times,g.target_end.to_numpy(dtype="datetime64[ns]"),side="left")
            np.testing.assert_array_equal(g.target.to_numpy(),(right>left).astype(int))

    def test_history_is_strictly_before_snapshot(self):
        self.assertTrue(self.s.last_historical_purchase.lt(self.s.snapshot_date).all())
        self.assertTrue(self.s.first_observed_purchase.le(self.s.last_historical_purchase).all())
        self.assertTrue(self.s.historical_orders.ge(1).all())
        self.assertTrue(self.s.customer_history_days.ge(0).all())
        arrays={cid:g.InvoiceDate.to_numpy(dtype="datetime64[ns]") for cid,g in self.o.groupby("CustomerID")}
        for cid,g in self.s.groupby("customer_id"):
            expected=np.searchsorted(arrays[cid],g.snapshot_date.to_numpy(dtype="datetime64[ns]"),side="left")
            np.testing.assert_array_equal(g.historical_orders,expected)

    def test_candidate_counts_reconcile(self):
        for row in self.c.itertuples():
            g=self.s.loc[self.s.horizon_days.eq(row.horizon_days)]
            self.assertEqual(row.eligible_snapshots,int(g.full_followup.sum()))
            self.assertEqual(row.positive,int(g.target.eq(1).sum()))
            self.assertEqual(row.negative,int(g.target.eq(0).sum()))
            self.assertEqual(row.positive+row.negative,row.eligible_snapshots)
            self.assertEqual(row.eligible_snapshots+row.censored_snapshots,len(g))
            self.assertTrue(row.positive>=0 and row.negative>=0)

    def test_common_snapshot_population_and_monotone_labels(self):
        cutoff=pd.Timestamp(self.k["common_last_snapshot"])
        common=self.s.loc[self.s.snapshot_date.le(cutoff)]
        pivot=common.pivot(index=["customer_id","snapshot_date"],columns="horizon_days",values="target")
        self.assertFalse(pivot.isna().any().any())
        self.assertTrue((np.diff(pivot.to_numpy(),axis=1)>=0).all())
        self.assertTrue(self.c.common_snapshot_count.eq(len(pivot)).all())

    def test_no_fabricated_customers_and_unique_snapshots(self):
        self.assertTrue(set(self.s.customer_id).issubset(set(self.o.CustomerID)))
        self.assertFalse(self.s.duplicated(["customer_id","snapshot_date","horizon_days"]).any())
        self.assertTrue(self.s.snapshot_date.dt.day.eq(1).all())
        self.assertEqual(self.s.horizon_days.nunique(),4)

    def test_recommendation_matches_declared_cadence_rule(self):
        expected=min(h for h in [30,45,60,90] if h>=self.k["p75_days"])
        self.assertEqual(self.k["recommended_horizon_days"],expected)
        self.assertEqual(self.k["calendar_day_sensitivity"]["recommended_by_same_criterion"],expected)

    def test_prior_artifacts_unchanged(self):
        for path,checksum in self.k["integrity"]["sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),checksum,path)

if __name__=="__main__":unittest.main()
