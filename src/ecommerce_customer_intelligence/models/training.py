"""Conservative model selection with a final temporal holdout."""
from pathlib import Path
import json,hashlib,sys
import numpy as np
import pandas as pd
import joblib
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.dummy import DummyClassifier
from sklearn.metrics import brier_score_loss
from xgboost import XGBClassifier
from .features import FEATURES
from .evaluation import metrics,thresholds

SEED=42
def pipeline(model,scale=False):
    steps=[("imputer",SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True))]
    if scale:steps.append(("scaler",StandardScaler()))
    return Pipeline(steps+[("model",model)])
def fit_models(data,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    tr=data.loc[data.split.eq("train")];va=data.loc[data.split.eq("validation")]
    X,y=tr[FEATURES],tr.target
    candidates={
        "Naive":[pipeline(DummyClassifier(strategy="prior"))],
        "Logistic Regression":[pipeline(LogisticRegression(C=c,max_iter=3000,random_state=SEED,class_weight=w),True)
            for c,w in [(.1,None),(1,None),(1,"balanced")]],
        "Random Forest":[pipeline(RandomForestClassifier(n_estimators=200,max_depth=depth,min_samples_leaf=20,
            max_features=.8,n_jobs=2,random_state=SEED)) for depth in [6,10]],
        "XGBoost":[pipeline(XGBClassifier(n_estimators=180,max_depth=depth,learning_rate=.04,
            min_child_weight=20,subsample=.85,colsample_bytree=.85,reg_lambda=5,n_jobs=2,random_state=SEED,
            eval_metric="logloss",tree_method="hist")) for depth in [2,3]]}
    fitted={};trials=[];val_probs={}
    for name,models in candidates.items():
        best=-np.inf
        for i,model in enumerate(models):
            model.fit(X,y)
            p=model.predict_proba(va[FEATURES])[:,1];m=metrics(va.target,p)
            trials.append({"model":name,"candidate":i,"params":str(model.named_steps["model"].get_params()),
                           **{k:v for k,v in m.items() if k!="confusion_matrix"}})
            if m["average_precision"]>best:
                best=m["average_precision"];fitted[name]=model;val_probs[name]=p
        print("Selected configuration:",name,flush=True)
    winner=max([n for n in fitted if n!="Naive"],key=lambda n:metrics(va.target,val_probs[n])["average_precision"])
    besttree=max(["Random Forest","XGBoost"],key=lambda n:metrics(va.target,val_probs[n])["average_precision"])
    raw=val_probs[winner]
    # Calibration fitting and assessment use separate validation months.
    first=va.snapshot_date.eq(va.snapshot_date.min()).to_numpy()
    logit=lambda p:np.log(np.clip(p,1e-6,1-1e-6)/(1-np.clip(p,1e-6,1-1e-6))).reshape(-1,1)
    calibrator=LogisticRegression(C=1e6,random_state=SEED)
    calibrator.fit(logit(raw[first]),va.target.to_numpy()[first])
    trial=calibrator.predict_proba(logit(raw[~first]))[:,1]
    raw_brier=brier_score_loss(va.target.to_numpy()[~first],raw[~first])
    calibrated_brier=brier_score_loss(va.target.to_numpy()[~first],trial)
    use_calibration=bool(calibrated_brier<raw_brier-.001)
    operating=calibrator.predict_proba(logit(raw))[:,1] if use_calibration else raw
    # Threshold is selected on July only, independent of June calibration fitting.
    tradeoff=thresholds(va.target.to_numpy()[~first],operating[~first])
    selected=tradeoff.sort_values(["action_f1","threshold"],ascending=[False,True]).iloc[0]
    threshold=float(selected.threshold)
    bands=np.quantile(operating[~first],[1/3,2/3]).tolist()
    decision={"winner":winner,"best_tree":besttree,"threshold":threshold,"band_boundaries":bands,
        "calibration":{"applied":use_calibration,"fit_month":"2011-06","assessment_month":"2011-07",
            "raw_july_brier":float(raw_brier),"calibrated_july_brier":float(calibrated_brier),
            "minimum_brier_improvement":.001},
        "selection_metric":"Validation average precision","seed":SEED,
        "selected_action_validation":selected.to_dict(),"features":FEATURES}
    # Persist all decisions before the first test prediction/evaluation.
    (folder/"decision.json").write_text(json.dumps(decision,indent=2),encoding="utf-8")
    pd.DataFrame(trials).to_csv(folder/"validation_trials.csv",index=False)
    tradeoff.to_csv(folder/"threshold_tradeoff.csv",index=False)
    for name,model in fitted.items():joblib.dump(model,folder/(name.replace(" ","_")+".joblib"))
    joblib.dump(calibrator if use_calibration else None,folder/"calibrator.joblib")
    # Frozen comparison: no parameters, thresholds or calibration change after this point.
    te=data.loc[data.split.eq("test")].copy()
    results=[];probs={};validation_results={}
    for name,model in fitted.items():
        p=model.predict_proba(te[FEATURES])[:,1];probs[name]=p
        results.append({"model":name,**metrics(te.target,p)})
        validation_results[name]=metrics(va.target,val_probs[name])
    final_raw=probs[winner]
    final=calibrator.predict_proba(logit(final_raw))[:,1] if use_calibration else final_raw
    te["raw_model_probability"]=final_raw;te["predicted_probability"]=final
    te["predicted_class"]=(final>=threshold).astype(int)
    te["action_candidate"]=final<threshold
    te["opportunity_band"]=np.select([final<bands[0],final<bands[1]],
        ["Low repeat propensity","Medium repeat propensity"],default="High repeat propensity")
    te=te.rename(columns={"target":"actual_label"})
    result={"decision":decision,"test_comparison_raw_at_05":results,"validation_comparison_raw":validation_results,
        "winner_operating_test":metrics(te.actual_label,final,threshold),
        "winner_raw_test":metrics(te.actual_label,final_raw),
        "winner_final_probability_test_at_05":metrics(te.actual_label,final),
        "train_prevalence":float(y.mean()),"transformed_feature_count":len(fitted[winner][:-1].get_feature_names_out())}
    return fitted,te,probs,result,tradeoff
