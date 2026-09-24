"""Explain the frozen tree and render diagnostics without model reselection."""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
import joblib,shap
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from ecommerce_customer_intelligence.models.features import FEATURES
from ecommerce_customer_intelligence.models.plots import diagnostics,explanation_charts

def main():
    result=json.loads((ROOT/"reports/metrics/phase5b_model_results.json").read_text())
    actions=pd.read_csv(ROOT/"data/processed/phase5b_customer_actions.csv",dtype={"customer_id":"string"})
    data=pd.read_csv(ROOT/"data/processed/phase5b_features.csv.gz",dtype={"customer_id":"string"})
    test=data.loc[data.split.eq("test")]
    pred=pd.read_csv(ROOT/"data/processed/phase5b_test_probabilities.csv")
    tradeoff=pd.read_csv(ROOT/"reports/metrics/phase5b_threshold_tradeoff.csv")
    name=result["decision"]["best_tree"]
    pipe=joblib.load(ROOT/("data/processed/phase5b_models/"+name.replace(" ","_")+".joblib"))
    x=pipe[:-1].transform(test[FEATURES]);names=pipe[:-1].get_feature_names_out().tolist()
    explainer=shap.TreeExplainer(pipe.named_steps["model"],feature_perturbation="tree_path_dependent",model_output="raw")
    values=[];base=[]
    for start in range(0,len(x),500):
        explanation=explainer(x[start:start+500],check_additivity=True)
        v=explanation.values;b=explanation.base_values
        if v.ndim==3:v=v[:,:,1];b=b[:,1]
        values.append(v);base.extend(np.asarray(b).reshape(-1))
        print(f"Explained {min(start+500,len(x))}/{len(x)} real test snapshots",flush=True)
    values=np.concatenate(values);base=np.asarray(base)
    probs=pipe.predict_proba(test[FEATURES])[:,1]
    scale="probability" if name=="Random Forest" else "log odds"
    reconstructed=base+values.sum(axis=1)
    if scale=="log odds":reconstructed=1/(1+np.exp(-reconstructed))
    error=float(np.max(np.abs(reconstructed-probs)))
    if error>1e-5:raise RuntimeError("SHAP additivity check failed")
    final=actions.predicted_probability.to_numpy()
    representatives={"high_repeat_probability":int(np.argmax(final)),"low_repeat_probability":int(np.argmin(final)),
        "borderline_customer":int(np.argmin(np.abs(final-result["decision"]["threshold"])))}
    importance=explanation_charts(values,x,names,base,probs,representatives,name,scale,ROOT/"reports/figures")
    diagnostics(result,pred,actions,tradeoff,ROOT/"reports/figures")
    imp=pd.DataFrame({"feature":names,"mean_absolute_shap":importance}).sort_values("mean_absolute_shap",ascending=False)
    imp.to_csv(ROOT/"reports/metrics/phase5b_shap_importance.csv",index=False)
    np.savez_compressed(ROOT/"data/processed/phase5b_shap_values.npz",values=values,base=base,feature_names=np.asarray(names))
    if name==result["decision"]["winner"]:
        factors=[]
        for row in values:
            idx=np.argsort(np.abs(row))[-3:][::-1]
            factors.append("; ".join(f"{names[j]}: {row[j]:+.4f} raw-model {scale}" for j in idx))
        actions["top_model_driving_factors"]=factors
    else:
        winner=joblib.load(ROOT/("data/processed/phase5b_models/"+result["decision"]["winner"].replace(" ","_")+".joblib"))
        z=winner[:-1].transform(test[FEATURES]);n=winner[:-1].get_feature_names_out()
        contributions=z*winner.named_steps["model"].coef_[0]
        actions["top_model_driving_factors"]=["; ".join(f"{n[j]}: {row[j]:+.4f} linear log-odds contribution"
            for j in np.argsort(np.abs(row))[-3:][::-1]) for row in contributions]
    actions.to_csv(ROOT/"data/processed/phase5b_customer_actions.csv",index=False)
    explained={"tree_model":name,"output_scale":scale,"rows_explained":len(x),"max_additivity_error":error,
        "feature_count_after_preprocessing":len(names),"representatives":[{"role":role,
            "customer_id":str(actions.iloc[i].customer_id),"snapshot_date":str(actions.iloc[i].snapshot_date),
            "raw_tree_probability":float(probs[i]),"final_probability":float(final[i]),
            "actual_label":int(actions.iloc[i].actual_label)} for role,i in representatives.items()],
        "top_features":imp.head(10).to_dict("records")}
    (ROOT/"reports/metrics/phase5b_explanations.json").write_text(json.dumps(explained,indent=2),encoding="utf-8")
    print(json.dumps(explained,indent=2),flush=True)
if __name__=="__main__":main()
