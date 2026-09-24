"""Build/train once; freeze decisions before test evaluation."""
from pathlib import Path
import sys,json,hashlib,importlib.metadata
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from ecommerce_customer_intelligence.analytics.engine import load_ledger
from ecommerce_customer_intelligence.models.features import build_dataset,FEATURES
from ecommerce_customer_intelligence.models.training import fit_models

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    protected=[p for folder in ["data","reports","docs","tests","src/ecommerce_customer_intelligence/analytics","src/ecommerce_customer_intelligence/data"]
        for p in (ROOT/folder).rglob("*") if p.is_file() and p.suffix in [".xlsx",".csv",".gz",".json",".md",".png",".svg",".py"]
        and "phase5b" not in str(p).lower() and "__pycache__" not in str(p)]
    before={str(p.relative_to(ROOT)):sha(p) for p in protected}
    ledger=load_ledger(ROOT/"data/processed/transactions.csv.gz")
    snapshots=pd.read_csv(ROOT/"data/processed/phase5a_candidate_snapshots.csv.gz",dtype={"customer_id":"string"},parse_dates=["snapshot_date","target_end"])
    data,differences=build_dataset(ledger,snapshots)
    data.to_csv(ROOT/"data/processed/phase5b_features.csv.gz",index=False)
    splits=[]
    for name,g in data.groupby("split"):
        splits.append({"split":name,"first_snapshot":str(g.snapshot_date.min()),"last_snapshot":str(g.snapshot_date.max()),
            "last_outcome_end":str(g.target_end.max()),"snapshots":len(g),"customers":g.customer_id.nunique(),
            "positive":int(g.target.sum()),"negative":int(g.target.eq(0).sum()),"positive_pct":g.target.mean()*100})
    pd.DataFrame(splits).to_csv(ROOT/"reports/metrics/phase5b_splits.csv",index=False)
    print("Features ready; target boundary changes:",differences,flush=True)
    print(pd.DataFrame(splits).to_string(index=False),flush=True)
    folder=ROOT/"data/processed/phase5b_models"
    models,actions,probs,result,tradeoff=fit_models(data,folder)
    actions.to_csv(ROOT/"data/processed/phase5b_customer_actions.csv",index=False)
    pred=actions[["customer_id","snapshot_date","actual_label"]].copy()
    for name,p in probs.items():pred[name]=p
    pred.to_csv(ROOT/"data/processed/phase5b_test_probabilities.csv",index=False)
    table=pd.DataFrame([{k:v for k,v in row.items() if k!="confusion_matrix"} for row in result["test_comparison_raw_at_05"]])
    table.to_csv(ROOT/"reports/metrics/phase5b_model_comparison.csv",index=False)
    tradeoff.to_csv(ROOT/"reports/metrics/phase5b_threshold_tradeoff.csv",index=False)
    result.update({"splits":splits,"boundary_label_changes_from_phase5a":differences,
        "feature_count":len(FEATURES),"input_integrity":{"prior_artifacts_unchanged":True,"sha256":before},
        "versions":{p:importlib.metadata.version(p) for p in ["pandas","numpy","scikit-learn","xgboost","shap","joblib"]}})
    if before!={str(p.relative_to(ROOT)):sha(p) for p in protected}:raise RuntimeError("Prior phase changed")
    (ROOT/"reports/metrics/phase5b_model_results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(table.to_string(index=False),flush=True)
    print(json.dumps(result["decision"],indent=2),flush=True)
if __name__=="__main__":main()
