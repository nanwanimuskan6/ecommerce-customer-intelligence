"""Document frozen results without retraining or changing model choices."""
from pathlib import Path
import json,sys
import pandas as pd
from sklearn.metrics import precision_score,recall_score,f1_score
ROOT=Path(__file__).resolve().parents[1]
def table(d):
    d=d.copy()
    for col in d.select_dtypes("number"):d[col]=d[col].map(lambda x:f"{x:,.4f}" if pd.notna(x) else "N/A")
    return "| "+" | ".join(d.columns)+" |\n| "+" | ".join(["---"]*len(d.columns))+" |\n"+"\n".join(
        "| "+" | ".join(str(v).replace("|","/") for v in row)+" |" for row in d.itertuples(index=False,name=None))
r=json.loads((ROOT/"reports/metrics/phase5b_model_results.json").read_text());decision=r["decision"]
ex=json.loads((ROOT/"reports/metrics/phase5b_explanations.json").read_text())
a=pd.read_csv(ROOT/"data/processed/phase5b_customer_actions.csv")
selected=a.action_candidate
action_metrics={"precision":precision_score(1-a.actual_label,selected),"recall":recall_score(1-a.actual_label,selected),
    "f1":f1_score(1-a.actual_label,selected),"review_fraction":selected.mean(),"review_count":int(selected.sum())}
(ROOT/"reports/metrics/phase5b_action_metrics.json").write_text(json.dumps(action_metrics,indent=2),encoding="utf-8")
features=[
("recency_days","Snapshot minus latest historical purchase timestamp, fractional days."),
("purchase_frequency","Distinct historical valid purchase invoices; also represents total_orders, avoiding a duplicate predictor."),
("monetary_value","Sum of historical valid customer purchase line_revenue, gross merchandise scope."),
("total_items","Sum of historical valid purchase quantities."),
("average_order_value","Mean invoice-level gross purchase revenue."),
("average_items_per_order","Mean invoice-level item quantity."),
("median_order_value / max_order_value","Median and maximum historical invoice-level gross values."),
("customer_tenure_days","Snapshot minus first observed purchase, fractional days; also represents days_since_first_purchase."),
("average / median / std_days_between_purchases","Mean, median and sample standard deviation of ordered invoice gaps; unavailable statistics stay missing."),
("historical_return_count","Distinct identified nonduplicate cancellation/negative-quantity invoices strictly before cutoff; includes service/adjustment flags."),
("historical_return_rate","Historical reversal invoice count divided by historical valid purchase invoice count; ratio, not matched-order probability."),
("historical_returned_value","Sum of the existing return_cancellation_value for historical identified reversal rows."),
("historical_dataset_days","Elapsed days from observed source start to cutoff; exposure proxy."),
("orders_previous_30/60/90_days","Distinct historical valid invoices in [cutoff - window, cutoff); missing if source coverage is shorter than the window."),
("history_30/60/90_days_complete","1 when the whole historical window lies inside the observed source coverage, otherwise 0.")]
comparison=pd.DataFrame([{**{k:v for k,v in row.items() if k!="confusion_matrix"},
    "TN / FP / FN / TP":" / ".join(map(str,[row["confusion_matrix"][0][0],row["confusion_matrix"][0][1],row["confusion_matrix"][1][0],row["confusion_matrix"][1][1]]))} for row in r["test_comparison_raw_at_05"]])
validation=pd.DataFrame([{"model":name,**{k:v for k,v in metrics.items() if k!="confusion_matrix"}} for name,metrics in r["validation_comparison_raw"].items()])
b=decision["band_boundaries"]
sections=[
"# Phase 5B — Leakage-safe repeat-purchase prediction",
"## Business question and target",
"Estimate the probability that an already observed customer makes a valid purchase during the next 60 days. This supports a retention-review queue; "
"it does not predict verified churn or treatment response. Phase 5A selected 60 days from the observed purchase cadence: median 22.01 days, "
"75th percentile 51.28 days, and 78.82% completed-gap coverage. These earlier results remain unchanged.",
"The Phase 5B target follows the newly requested interval **(snapshot_date, snapshot_date + 60 days]**. Features use timestamps strictly less than "
"snapshot_date. This differs from Phase 5A's [start, end) convention; re-evaluation on the real eligible snapshots changed "
f"**{r['boundary_label_changes_from_phase5a']} labels**. Phase 5A files were not edited. Only its fully observable 60-day snapshots are used; "
"the same 8,263 insufficient-follow-up observations are excluded. No incomplete observation is labeled negative.",
"## Temporal design",
table(pd.DataFrame(r["splits"])),
"Training snapshots are January 1 through April 1, 2011. Validation snapshots are June 1 and July 1. Test snapshots are September 1 and October 1. "
"May and August are embargoed. Latest training outcome ends May 31, before validation begins June 1; latest validation outcome ends August 30, "
"before test begins September 1. Test outcomes end November 30, within actual source coverage. Embargo rows are saved for audit but never fitted or scored.",
"Customers can recur across periods because the intended use is predicting behavior of existing customers. Customer ID is never a predictor. "
"Adjacent windows within a split overlap, so rows are not independent observations. A customer-disjoint split would answer a different cold-customer question. "
"All model choices were persisted in phase5b_models/decision.json before first test prediction. No test-based winner switching or retraining occurred.",
"## Feature contract",
f"**{r['feature_count']} input features**, expanded to **{r['transformed_feature_count']}** for the selected model through missingness indicators.",
table(pd.DataFrame(features,columns=["feature","definition"])),
"Invoice lines are grouped by (CustomerID, InvoiceNo), with earliest timestamp as the occasion. Every feature first restricts the ledger to InvoiceDate < cutoff. "
"No full-window Phase 3 customer features, Phase 4 scores/segments, target-window purchases, future return records, or IDs enter the model. "
"Historical-window exposure refers to dataset coverage; newly observed customers may still have short tenure. "
"Gross values and historical reversal values retain the previously verified Phase 2 scopes.",
"## Models and preprocessing",
"Naive baseline: training-set class prior as the probability, majority class at 0.5. Logistic Regression provides a regularized linear benchmark. "
"Random Forest captures nonlinear relationships and interactions with bounded-depth averaging. XGBoost provides a conservative boosted-tree comparison.",
"All preprocessing is fitted inside a pipeline on training data only. Median imputation adds missingness indicators; Logistic Regression additionally uses "
"StandardScaler. All selected inputs are numeric, so no categorical encoding is needed. Missing purchase gaps and incomplete lookbacks are not fabricated zeros. "
"Scaler parameters and imputation medians are verified against the training rows in tests.",
"Seed 42. Conservative search: Logistic Regression C=0.1/1 without weighting, plus one C=1 balanced-weight alternative; "
"Random Forest 200 trees with max_depth 6/10, min_samples_leaf=20 and max_features=0.8; "
"XGBoost 180 trees, depth 2/3, learning_rate=0.04, min_child_weight=20, subsample/column fraction=0.85, L2=5. "
"No random CV, SMOTE, resampling, or test-set early stopping. Selected configurations and all validation trials are saved.",
"Training has 46.51% positives: imbalance is modest. The balanced Logistic Regression alternative did not beat the selected unweighted C=0.1 configuration "
"on validation average precision, so the simpler unweighted setup was retained. Forest and boosting also remain unweighted.",
"## Validation selection",
table(validation),
f"**{decision['winner']}** was selected by validation average precision, not accuracy. Its lead over XGBoost is small; "
"the ranking is not evidence of statistically significant superiority. Selected forest: depth 6, 200 trees, minimum leaf size 20.",
"## Frozen test comparison",
"All four rows below use raw model probabilities and a common diagnostic threshold of 0.50. AP means Average Precision, not trapezoidal PR area. "
"Precision, recall and F1 use repeat purchase as the positive class.",
table(comparison),
"XGBoost has slightly higher test discrimination, but the validation-selected Random Forest remains the final model. Selecting XGBoost after seeing "
"these test results would misuse the holdout.",
"## Calibration",
f"Logistic sigmoid calibration maps the raw winner probability's logit to observed outcomes. It is fitted on June validation predictions only and "
f"assessed on July. July Brier changes from {decision['calibration']['raw_july_brier']:.6f} to "
f"{decision['calibration']['calibrated_july_brier']:.6f}; calibration was adopted because improvement exceeded the predeclared 0.001 threshold. "
"No test labels fit the calibrator. The calibrator is not refitted on July.",
"June and July are validation/tuning data, not an independent final calibration test: model selection already considered both months and their "
"customer outcome windows overlap. This can make the internal calibration comparison optimistic. Its out-of-period check is the frozen September–October test. "
"Do not interpret July improvement as unbiased forward performance. The final test calibration curve is inspection only and triggers no recalibration.",
f"Test Brier: raw winner {r['winner_raw_test']['brier']:.6f}; calibrated winner "
f"{r['winner_operating_test']['brier']:.6f}. Calibration is not perfect and later-period drift remains visible. "
"Brier combines calibration and discrimination, so a lower value does not by itself prove perfect reliability.",
"## Business threshold and action interpretation",
f"Selected threshold: **{decision['threshold']:.3f}**. Repeat probability at or above this threshold predicts repeat purchase; a lower score flags a "
"retention-review candidate. The objective maximizes July validation F1 for **nonrepeat** observations across thresholds 0.10–0.90 in 0.025 increments, "
"with lower-threshold tie-breaking. It is a transparent provisional screening criterion, not an economic optimum.",
f"Validation review precision {decision['selected_action_validation']['action_precision']:.2%}, recall "
f"{decision['selected_action_validation']['action_recall']:.2%}; review fraction "
f"{decision['selected_action_validation']['action_rate']:.2%}. This is broad screening. Without campaign cost, capacity or treatment-effect data, "
"do not automatically contact everyone flagged or claim they would benefit. The saved trade-off table supports a later capacity-aware decision.",
"### Final model at the selected threshold (repeat is positive)",
table(pd.DataFrame([{"metric":k,"value":str(v)} for k,v in r["winner_operating_test"].items()])),
"### Same decisions viewed as a nonrepeat review queue",
table(pd.DataFrame([action_metrics])),
f"Probability bands use July validation terciles: low < {b[0]:.6f}, medium from {b[0]:.6f} to < {b[1]:.6f}, high >= {b[1]:.6f}. "
"These are relative propensity bands, not universally high/low calibrated confidence. They are separate from the action threshold and are not adjusted to test quantiles.",
"## SHAP explanations",
f"Exact TreeSHAP explains the selected {ex['tree_model']} using its training-path distribution. Contributions are in "
f"**raw tree probability space**, not the calibrated probability. Across {ex['rows_explained']:,} test rows, base value plus contributions "
f"reconstructs raw predictions with maximum absolute error {ex['max_additivity_error']:.3g}. "
"The calibrator monotonically transforms that probability; SHAP values are not falsely relabeled as additive calibrated-probability effects.",
table(pd.DataFrame(ex["top_features"])),
"Missing mean-gap and median-gap indicators largely represent the same one-order-history condition. Their importance is shared among correlated proxies "
"and should not be read as independent behavioral mechanisms. SHAP explains features driving the model's prediction, not causal reasons for behavior.",
table(pd.DataFrame(ex["representatives"])),
"Global importance uses all test snapshots. The summary plot displays a fixed sample of up to 600 real rows; vertical jitter only separates marks and does not "
"alter data. High/low/borderline examples are selected by final calibrated scores; their contribution plots correctly show the underlying raw tree probability.",
"## Customer action table",
"data/processed/phase5b_customer_actions.csv contains test customer_id, snapshot_date, actual_label, raw_model_probability, predicted_probability, "
"predicted_class, action_candidate, opportunity_band, historical features, and the three largest signed model-driving contributions. "
"No customer is labeled churned. This is a historical analytical table, not a live campaign list. Future dates cannot receive actual_label until follow-up completes.",
"## Limitations and interpretation",
"The source covers roughly one year; only two calendar test cutoffs exist, and observations share customers and overlapping 60-day outcomes. "
"No IID confidence intervals or causal campaign benefits are claimed. Aggregate behavior and target selection were explored in prior phases across this dataset: "
"the temporal holdout is untouched during Phase 5B model tuning, but it is not pristine external data untouched by all project exploration. "
"Independent future data is needed for stronger performance claims.",
"Customer identity is missing on part of the raw ledger; first purchases are left-censored; negative means no observed valid purchase, not true churn. "
"Historical exposure is short for early snapshots, and time/exposure proxies may drift or saturate outside the training range. "
"Several input features and missingness indicators are correlated. Calibration and the threshold were tuned on limited validation data. "
"The broad review queue and modest model differences require business validation before use.",
"## Reproduction and artifacts",
"Install into the isolated environment with python -m pip install -r requirements-phase5b.txt. Run scripts/run_phase5b.py, "
"then scripts/explain_phase5b.py, scripts/document_phase5b.py, and scripts/run_phase5b_tests.py. "
"Reproduction retrains the fixed procedure; do not use reruns to optimize against test results.",
"New modeling modules: models/features.py, evaluation.py, training.py, plots.py. Saved pipelines, calibrator, frozen decision and trial table are in "
"data/processed/phase5b_models/ (already covered by the processed-data gitignore). Feature/snapshot and prediction tables are prefixed phase5b. "
"Metrics, SHAP importance, split counts, action metrics and test results use reports/metrics/phase5b_*; no previous results are overwritten.",
"## Technical references",
"[Scikit-learn probability calibration](https://scikit-learn.org/stable/modules/calibration.html) documents disjoint classifier/calibrator fitting and reliability assessment. "
"[SHAP TreeExplainer](https://shap.readthedocs.io/en/stable/generated/shap.TreeExplainer.html) documents model-output scales and perturbation choices.",
"## Figures",
*[f"![{name.replace('_',' ').title()}](../reports/figures/phase5b_{name}.png)" for name in [
"model_comparison","roc","precision_recall","confusion_matrix","calibration","threshold_tradeoff","shap_importance","shap_summary",
"shap_high_repeat_probability","shap_low_repeat_probability","shap_borderline_customer"]],
"Stopped after Phase 5B. No Streamlit, deployment or GitHub push."
]
(ROOT/"docs/PHASE5B.md").write_text("\n\n".join(sections)+"\n",encoding="utf-8")
print(json.dumps(action_metrics,indent=2))
