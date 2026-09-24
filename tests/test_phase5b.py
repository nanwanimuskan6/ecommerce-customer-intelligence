"""Tests of real-data cutoff construction, temporal evaluation and inference."""
from pathlib import Path
import sys,json,hashlib,unittest
import numpy as np
import pandas as pd
import joblib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from ecommerce_customer_intelligence.models.features import FEATURES,asof_features
from ecommerce_customer_intelligence.models.evaluation import metrics
from ecommerce_customer_intelligence.analytics.engine import load_ledger

class Phase5BTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=load_ledger(ROOT/"data/processed/transactions.csv.gz")
        cls.f=pd.read_csv(ROOT/"data/processed/phase5b_features.csv.gz",dtype={"customer_id":"string"},
            parse_dates=["snapshot_date","target_end"])
        cls.r=json.loads((ROOT/"reports/metrics/phase5b_model_results.json").read_text())
        cls.a=pd.read_csv(ROOT/"data/processed/phase5b_customer_actions.csv",dtype={"customer_id":"string"},parse_dates=["snapshot_date"])
        cls.model=joblib.load(ROOT/("data/processed/phase5b_models/"+cls.r["decision"]["winner"].replace(" ","_")+".joblib"))

    def test_no_future_records_needed_for_features(self):
        for date in ["2011-01-01","2011-06-01","2011-09-01"]:
            t=pd.Timestamp(date);ids=self.f.loc[self.f.snapshot_date.eq(t),"customer_id"].head(30).tolist()
            full=asof_features(self.d,t,ids)
            truncated=asof_features(self.d.loc[self.d.InvoiceDate.lt(t)],t,ids)
            pd.testing.assert_frame_equal(full,truncated)

    def test_feature_values_from_actual_historical_invoices(self):
        t=pd.Timestamp("2011-09-01")
        expected=self.f.loc[self.f.snapshot_date.eq(t)].set_index("customer_id")
        p=self.d.loc[self.d.is_customer_purchase&self.d.InvoiceDate.lt(t)]
        order=p.groupby(["CustomerID","InvoiceNo"]).line_revenue.sum()
        total=order.groupby("CustomerID").sum()
        np.testing.assert_allclose(expected.loc[total.index,"monetary_value"],total,atol=1e-8)
        np.testing.assert_array_equal(expected.loc[total.index,"purchase_frequency"],p.groupby("CustomerID").InvoiceNo.nunique())
        np.testing.assert_allclose(expected.loc[total.index,"average_order_value"],order.groupby("CustomerID").mean(),atol=1e-8)

    def test_historical_window_coverage(self):
        jan=self.f.loc[self.f.snapshot_date.eq("2011-01-01")]
        self.assertTrue(jan.orders_previous_60_days.isna().all())
        self.assertTrue(jan.orders_previous_90_days.isna().all())
        self.assertTrue(jan.history_60_days_complete.eq(0).all())
        self.assertTrue(jan.history_30_days_complete.eq(1).all())
        self.assertTrue(self.f.recency_days.gt(0).all())
        self.assertTrue(self.f.customer_tenure_days.ge(self.f.recency_days).all())

    def test_target_window_and_censoring(self):
        p=self.d.loc[self.d.is_customer_purchase].groupby(["CustomerID","InvoiceNo"]).InvoiceDate.min().reset_index()
        arrays={cid:np.sort(g.InvoiceDate.to_numpy(dtype="datetime64[ns]")) for cid,g in p.groupby("CustomerID")}
        for cid,g in self.f.groupby("customer_id"):
            a=arrays[cid]
            lo=np.searchsorted(a,g.snapshot_date.to_numpy(dtype="datetime64[ns]"),"right")
            hi=np.searchsorted(a,g.target_end.to_numpy(dtype="datetime64[ns]"),"right")
            np.testing.assert_array_equal(g.target,(hi>lo).astype(int))
        self.assertTrue(self.f.target_end.le(self.d.InvoiceDate.max()).all())
        self.assertTrue((self.f.target_end-self.f.snapshot_date).dt.days.eq(60).all())
        prior=pd.read_csv(ROOT/"data/processed/phase5a_candidate_snapshots.csv.gz",dtype={"customer_id":"string"})
        self.assertEqual(len(self.f),len(prior.loc[prior.horizon_days.eq(60)&prior.full_followup]))

    def test_temporal_split_integrity(self):
        tr=self.f.loc[self.f.split.eq("train")];va=self.f.loc[self.f.split.eq("validation")];te=self.f.loc[self.f.split.eq("test")]
        self.assertLess(tr.target_end.max(),va.snapshot_date.min())
        self.assertLess(va.target_end.max(),te.snapshot_date.min())
        self.assertEqual(set(self.f.loc[self.f.split.eq("embargo")].snapshot_date.dt.month),{5,8})
        self.assertFalse(self.f.duplicated(["customer_id","snapshot_date"]).any())

    def test_feature_allowlist_excludes_future_and_identifiers(self):
        banned={"customer_id","snapshot_date","target","target_end","split","segment","RFM_score","next_observed_purchase"}
        self.assertFalse(set(FEATURES)&banned)
        self.assertEqual(list(self.model.feature_names_in_),FEATURES)
        self.assertEqual(len(FEATURES),self.r["feature_count"])

    def test_imputer_fitted_only_on_train(self):
        train=self.f.loc[self.f.split.eq("train"),FEATURES]
        np.testing.assert_allclose(self.model.named_steps["imputer"].statistics_,train.median().to_numpy(),atol=1e-8)
        transformed=self.model[:-1].transform(self.f[FEATURES])
        self.assertTrue(np.isfinite(transformed).all())
        lr=joblib.load(ROOT/"data/processed/phase5b_models/Logistic_Regression.joblib")
        imputed=lr.named_steps["imputer"].transform(train)
        np.testing.assert_allclose(lr.named_steps["scaler"].mean_,imputed.mean(axis=0),atol=1e-8)

    def test_saved_model_inference_and_calibration(self):
        te=self.f.loc[self.f.split.eq("test")]
        raw=self.model.predict_proba(te[FEATURES])[:,1]
        np.testing.assert_allclose(raw,self.a.raw_model_probability,atol=1e-8)
        cal=joblib.load(ROOT/"data/processed/phase5b_models/calibrator.joblib")
        final=raw if cal is None else cal.predict_proba(np.log(np.clip(raw,1e-6,1-1e-6)/(1-np.clip(raw,1e-6,1-1e-6))).reshape(-1,1))[:,1]
        np.testing.assert_allclose(final,self.a.predicted_probability,atol=1e-8)
        self.assertTrue(self.a.predicted_probability.between(0,1).all())
        np.testing.assert_array_equal(self.a.predicted_class,final>=self.r["decision"]["threshold"])

    def test_output_schema_and_real_entities(self):
        required={"customer_id","snapshot_date","actual_label","predicted_probability","raw_model_probability",
                  "predicted_class","opportunity_band","action_candidate","top_model_driving_factors"}
        self.assertTrue(required.issubset(self.a.columns))
        self.assertFalse(self.a[list(required)].isna().any().any())
        self.assertEqual(set(self.a.customer_id),set(self.f.loc[self.f.split.eq("test"),"customer_id"]))
        self.assertEqual(len(self.a),len(self.f.loc[self.f.split.eq("test")]))

    def test_selection_and_operating_metrics(self):
        decision=json.loads((ROOT/"data/processed/phase5b_models/decision.json").read_text())
        self.assertEqual(decision,self.r["decision"])
        vals=self.r["validation_comparison_raw"]
        winner=max([k for k in vals if k!="Naive"],key=lambda k:vals[k]["average_precision"])
        self.assertEqual(winner,decision["winner"])
        actual=metrics(self.a.actual_label,self.a.predicted_probability,decision["threshold"])
        for key,value in actual.items():
            if key=="confusion_matrix":self.assertEqual(value,self.r["winner_operating_test"][key])
            else:self.assertAlmostEqual(value,self.r["winner_operating_test"][key],places=8)

    def test_shap_additivity(self):
        data=np.load(ROOT/"data/processed/phase5b_shap_values.npz")
        np.testing.assert_allclose(data["base"]+data["values"].sum(axis=1),self.a.raw_model_probability,atol=1e-5)

    def test_previous_artifacts_unchanged(self):
        for path,checksum in self.r["input_integrity"]["sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),checksum,path)
if __name__=="__main__":unittest.main()
