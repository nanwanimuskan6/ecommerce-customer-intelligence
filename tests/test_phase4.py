"""Phase 4 regression tests use only real existing customer and ledger records."""
from pathlib import Path
import sys,json,unittest,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from ecommerce_customer_intelligence.analytics.engine import load_ledger
from ecommerce_customer_intelligence.analytics.customer_intelligence import (
    build_rfm,assign_segments,score_values,concentration,cohorts_and_lifecycle,SEGMENTS)

class Phase4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.features=pd.read_csv(ROOT/"data/processed/customer_features.csv",dtype={"customer_id":"string"},
            parse_dates=["first_purchase_date","last_purchase_date"])
        cls.k3=json.loads((ROOT/"reports/metrics/business_kpis.json").read_text())["kpis"]
        cls.r,cls.s,cls.edges=build_rfm(cls.features,cls.k3["recency_reference_date"],cls.k3["valid_customer_purchase_revenue"])
        cls.d=load_ledger(ROOT/"data/processed/transactions.csv.gz")
        cls.cohort,cls.gaps,cls.trend,cls.freq,cls.life=cohorts_and_lifecycle(cls.d,cls.r)
        cls.pareto,cls.shares,cls.con=concentration(cls.r)

    def test_one_record_per_eligible_customer(self):
        expected=set(self.features.loc[self.features.frequency_orders.ge(1),"customer_id"])
        self.assertTrue(self.r.customer_id.is_unique)
        self.assertEqual(set(self.r.customer_id),expected)
        self.assertEqual(len(self.r),self.k3["unique_purchasing_customers"])
        self.assertTrue(self.r.recency.ge(0).all())
        self.assertTrue(self.r.frequency.ge(1).all())
        self.assertTrue(self.r.monetary.gt(0).all())

    def test_score_ranges_and_direction(self):
        for field,score,ascending in [("recency","R_score",False),("frequency","F_score",True),("monetary","M_score",True)]:
            self.assertTrue(self.r[score].between(1,5).all())
            self.assertTrue(self.r.groupby(field)[score].nunique().eq(1).all())
            ordered=self.r.sort_values(field)[score]
            self.assertTrue(ordered.is_monotonic_increasing if ascending else ordered.is_monotonic_decreasing)
        self.assertTrue(self.r.RFM_total_score.between(3,15).all())
        np.testing.assert_array_equal(self.r.RFM_total_score,self.r[["R_score","F_score","M_score"]].sum(axis=1))
        self.assertTrue(self.r.RFM_score.str.fullmatch("[1-5]{3}").all())

    def test_duplicate_boundaries_real_subpopulation(self):
        # Real one-order customers provide constant values without fabricated fixtures.
        observed=self.r.loc[self.r.frequency.eq(1),"frequency"]
        scores,edges=score_values(observed)
        self.assertEqual(len(set(edges)),1)
        self.assertEqual(scores.nunique(),1)
        self.assertTrue(scores.between(1,5).all())

    def test_deterministic_complete_segmentation(self):
        shuffled=self.r.iloc[::-1]
        expected=self.r.segment.sort_index()
        pd.testing.assert_series_equal(assign_segments(shuffled).sort_index(),expected,check_names=False)
        self.assertTrue(self.r.segment.isin(SEGMENTS).all())
        self.assertFalse(self.r.segment.isna().any())
        champions=self.r.loc[self.r.segment.eq("Champions")]
        self.assertTrue((champions[["R_score","F_score","M_score"]]>=4).all().all())
        rerun,_,_=build_rfm(self.features.iloc[::-1],self.k3["recency_reference_date"],self.k3["valid_customer_purchase_revenue"])
        pd.testing.assert_frame_equal(self.r.sort_values("customer_id").reset_index(drop=True),
                                     rerun.sort_values("customer_id").reset_index(drop=True))

    def test_segment_count_and_revenue_reconciliation(self):
        self.assertEqual(self.s.customer_count.sum(),len(self.r))
        self.assertAlmostEqual(self.s.total_revenue.sum(),self.k3["valid_customer_purchase_revenue"],places=6)
        self.assertAlmostEqual(self.s.customer_pct.sum(),100,places=8)
        self.assertAlmostEqual(self.s.revenue_pct.sum(),100,places=8)
        self.assertAlmostEqual(self.r.monetary.sum(),self.features.monetary_value.sum(),places=6)

    def test_cohort_retention_bounds_and_month_zero(self):
        c=self.cohort
        self.assertTrue(c.retention.dropna().between(0,1).all())
        self.assertTrue(c.complete_retention.dropna().between(0,1).all())
        self.assertTrue(c.loc[c.month_index.eq(0),"retention"].eq(1).all())
        self.assertTrue(c.loc[c.period_status.eq("future"),"retention"].isna().all())
        self.assertTrue(c.loc[c.period_status.ne("complete"),"complete_retention"].isna().all())
        self.assertEqual(c.loc[c.month_index.eq(0),"cohort_size"].sum(),len(self.r))

    def test_cohort_counts_against_real_activity(self):
        p=self.d.loc[self.d.is_customer_purchase]
        first=p.groupby("CustomerID").InvoiceDate.min().dt.to_period("M")
        activity=p.assign(month=p.InvoiceDate.dt.to_period("M")).groupby("month").CustomerID.unique()
        for row in self.cohort.loc[self.cohort.period_status.ne("future")].itertuples():
            members=set(first.loc[first.eq(pd.Period(row.cohort))].index)
            observed=set(activity.get(pd.Period(row.activity_month),[]))
            self.assertEqual(row.active_customers,len(members & observed))
        complete_m1=self.cohort.loc[self.cohort.month_index.eq(1)&self.cohort.period_status.eq("complete")]
        self.assertAlmostEqual(self.life["month1_weighted_retention"],
                               complete_m1.active_customers.sum()/complete_m1.cohort_size.sum())

    def test_pareto_monotonicity_and_cutoff(self):
        p=self.pareto
        self.assertTrue(p.cumulative_revenue_pct.is_monotonic_increasing)
        self.assertTrue(p.cumulative_customer_pct.is_monotonic_increasing)
        self.assertAlmostEqual(p.iloc[-1].cumulative_revenue_pct,100,places=8)
        n=self.con["customers_for_80pct"]
        self.assertGreaterEqual(p.iloc[n-1].cumulative_revenue_pct,80)
        self.assertLess(p.iloc[n-2].cumulative_revenue_pct,80)
        for row in self.shares.itertuples():
            expected=self.r.nlargest(row.customer_count,"monetary").monetary.sum()/self.r.monetary.sum()*100
            self.assertAlmostEqual(row.revenue_share_pct,expected,places=8)
        self.assertAlmostEqual(self.shares.iloc[0].revenue_share_pct,
                               self.k3["top_1pct_customer_purchase_revenue_share_pct"],places=8)

    def test_lifecycle_counts_and_gaps(self):
        self.assertEqual(self.life["one_time_customers"]+self.life["repeat_customers"],len(self.r))
        self.assertEqual(self.life["repeat_customers"],self.k3["repeat_customers"])
        self.assertEqual(len(self.gaps),self.k3["valid_customer_purchase_orders"]-len(self.r))
        self.assertTrue(self.gaps.gap_days.ge(0).all())
        self.assertEqual(self.trend.new_customers.sum(),len(self.r))
        np.testing.assert_array_equal(self.trend.new_customers+self.trend.returning_customers,self.trend.active_customers)
        prior=pd.read_csv(ROOT/"data/processed/monthly.csv")
        np.testing.assert_array_equal(self.trend.new_customers,prior.new_customers)
        np.testing.assert_array_equal(self.trend.returning_customers,prior.repeat_customers)

    def test_saved_entities_and_unchanged_inputs(self):
        saved=pd.read_csv(ROOT/"data/processed/rfm_customers.csv",dtype={"customer_id":"string","RFM_score":"string"})
        self.assertEqual(set(saved.customer_id),set(self.r.customer_id))
        self.assertEqual(set(self.pareto.customer_id),set(self.r.customer_id))
        self.assertTrue(set(self.gaps.CustomerID).issubset(set(self.r.customer_id)))
        report=json.loads((ROOT/"reports/metrics/customer_intelligence.json").read_text())
        for path,checksum in report["integrity"]["before"].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),checksum)
            self.assertEqual(report["integrity"]["after"][path],checksum)
        self.assertEqual(report["customers_analyzed"],len(self.r))

if __name__=="__main__":unittest.main()
