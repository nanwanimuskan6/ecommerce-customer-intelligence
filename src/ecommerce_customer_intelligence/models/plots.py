"""Themed ML diagnostics and tree-model explanations."""
import numpy as np
from matplotlib.ticker import FuncFormatter
from sklearn.metrics import roc_curve,precision_recall_curve,confusion_matrix
from sklearn.calibration import calibration_curve
from matplotlib.colors import LinearSegmentedColormap
from ..analytics.theme import canvas,C,grid,save,number,percent
COLORS=[C["soft"],C["secondary"],C["primary"],C["highlight"]]
def diagnostics(result,pred,actions,tradeoff,folder):
    winner=result["decision"]["winner"];y=pred.actual_label
    comparison=result["test_comparison_raw_at_05"]
    fig,ax=canvas("Model discrimination on the temporal holdout",
        "Frozen configurations • average precision and ROC-AUC on September–October snapshots",height=7,left=.23)
    names=[r["model"] for r in comparison];yy=np.arange(len(names))
    ax.hlines(yy,[r["average_precision"] for r in comparison],[r["roc_auc"] for r in comparison],color=C["soft"],lw=3)
    ax.scatter([r["average_precision"] for r in comparison],yy,color=C["primary"],s=60,label="Average precision")
    ax.scatter([r["roc_auc"] for r in comparison],yy,color=C["secondary"],s=40,label="ROC-AUC")
    ax.set_yticks(yy,names);ax.set_xlim(0,1);ax.legend(loc="upper left",bbox_to_anchor=(0,1.13),ncol=2);grid(ax,"x")
    save(fig,folder,"phase5b_model_comparison")
    for kind in ["roc","precision_recall"]:
        fig,ax=canvas("Ranking customers by repeat-purchase propensity" if kind=="roc" else "Precision and recall for observed repeat purchases",
            "Temporal test set • positive class = a valid purchase in the next 60 days")
        for color,name in zip(COLORS,names):
            if kind=="roc":x,v,_=roc_curve(y,pred[name])
            else:v,x,_=precision_recall_curve(y,pred[name])
            ax.plot(x,v,color=color,label=name)
        if kind=="roc":ax.plot([0,1],[0,1],ls=":",lw=1,color=C["muted"])
        else:ax.axhline(y.mean(),ls=":",color=C["muted"],lw=1)
        ax.set(xlim=(0,1),ylim=(0,1.02),xlabel="False-positive rate" if kind=="roc" else "Recall",
               ylabel="True-positive rate" if kind=="roc" else "Precision")
        ax.legend(loc="lower right" if kind=="roc" else "lower left",fontsize=9)
        grid(ax);save(fig,folder,"phase5b_"+kind)
    t=result["decision"]["threshold"]
    fig,ax=canvas("Operating decisions at the validation-selected threshold",
        f"{winner} • repeat probability ≥ {t:.3f} predicts a purchase; lower scores flag a review candidate",
        "Counts are snapshot-level. Actual class 0 means no observed purchase, not confirmed churn.")
    matrix=confusion_matrix(actions.actual_label,actions.predicted_class)
    im=ax.imshow(matrix,cmap=LinearSegmentedColormap.from_list("matrix",["#EDF5F5",C["primary"]]),aspect="auto")
    for i in range(2):
        for j in range(2):ax.text(j,i,f"{matrix[i,j]:,}",ha="center",va="center",fontsize=23,
            color="white" if matrix[i,j]>matrix.max()*.6 else C["ink"])
    ax.set_xticks([0,1],["No repeat predicted","Repeat predicted"]);ax.set_yticks([0,1],["No repeat observed","Repeat observed"])
    save(fig,folder,"phase5b_confusion_matrix")
    fig,ax=canvas("How predicted probabilities compare with observed outcomes",
        "Reliability curves • quantile bins on the temporal test set",
        "Brier score assesses both calibration and discrimination; bins are descriptive, not independent confidence intervals.")
    ax.plot([0,1],[0,1],ls=":",lw=1,color=C["muted"],label="Perfect reliability")
    for color,name in zip(COLORS,names):
        true,mean=calibration_curve(y,pred[name],n_bins=8,strategy="quantile")
        ax.plot(mean,true,color=color,marker="o",ms=4,label=name)
    if result["decision"]["calibration"]["applied"]:
        true,mean=calibration_curve(y,actions.predicted_probability,n_bins=8,strategy="quantile")
        ax.plot(mean,true,color=C["negative"],ls="--",marker="s",label="Final calibrated winner")
    ax.set(xlim=(0,1),ylim=(0,1),xlabel="Mean predicted repeat probability",ylabel="Observed repeat rate")
    ax.legend(loc="upper left",fontsize=8);grid(ax);save(fig,folder,"phase5b_calibration")
    fig,ax=canvas("Retention review involves a precision–recall trade-off",
        f"July validation only • flag customers below repeat probability {t:.3f}",
        "Action metrics treat no observed repeat as the positive class. No campaign uplift or ROI is assumed.")
    for col,label,color in [("action_precision","Review precision",C["secondary"]),("action_recall","Review recall",C["primary"]),
        ("action_f1","Review F1",C["highlight"])]:
        ax.plot(tradeoff.threshold,tradeoff[col],label=label,color=color)
    ax.axvline(t,ls=":",color=C["muted"]);ax.set(xlabel="Repeat-probability threshold for review",ylabel="Metric value",ylim=(0,1))
    ax.legend(loc="lower right");grid(ax);save(fig,folder,"phase5b_threshold_tradeoff")

def explanation_charts(values,features,names,base,probabilities,representatives,model_name,scale,folder):
    importance=np.abs(values).mean(axis=0);top=np.argsort(importance)[-12:]
    labels=[names[i].replace("missingindicator_","Missing: ").replace("_"," ").title() for i in top]
    fig,ax=canvas("Features driving the tree model's predictions",
        f"{model_name} • mean absolute SHAP contribution on observed test snapshots",
        "Associations within the model, not causal reasons for customer behavior.",height=8,left=.36)
    ax.barh(labels,importance[top],color=C["primary"]);ax.set_xlabel("Mean |SHAP value| • "+scale);grid(ax,"x")
    save(fig,folder,"phase5b_shap_importance")
    fig,ax=canvas("Feature effects vary across customer snapshots",
        f"{model_name} • SHAP summary on a fixed sample of real test records",
        "Horizontal position = model contribution; color = relative feature value (low teal, high amber).",height=8,left=.36)
    sample=np.linspace(0,len(values)-1,min(600,len(values)),dtype=int)
    rng=np.random.default_rng(42)
    cmap=LinearSegmentedColormap.from_list("values",[C["primary"],"#DFE6E6",C["highlight"]])
    for row,col in enumerate(top):
        vals=features[sample,col];lo,hi=np.quantile(vals,[.05,.95])
        colors=np.clip((vals-lo)/(hi-lo if hi>lo else 1),0,1)
        ax.scatter(values[sample,col],row+rng.uniform(-.23,.23,len(sample)),c=colors,cmap=cmap,vmin=0,vmax=1,s=7,alpha=.65,rasterized=True)
    ax.axvline(0,color=C["muted"],lw=.8);ax.set_yticks(range(len(top)),labels);ax.set_xlabel("SHAP contribution • "+scale)
    save(fig,folder,"phase5b_shap_summary")
    for role,i in representatives.items():
        idx=np.argsort(np.abs(values[i]))[-8:]
        vals=list(values[i,idx]);labs=[names[j].replace("_"," ").title() for j in idx]
        remainder=float(values[i].sum()-sum(vals));vals=[remainder]+vals;labs=["Other features"]+labs
        fig,ax=canvas(f"Model explanation: {role.replace('_',' ')}",
            f"{model_name} • raw repeat probability {probabilities[i]:.1%} • baseline {base[i]:.3f} ({scale})",
            "Signed contributions drive this model prediction; they do not establish causal effects.",height=8,left=.37)
        ax.barh(labs,vals,color=[C["primary"] if v>=0 else C["negative"] for v in vals])
        ax.axvline(0,color=C["muted"],lw=.8);ax.set_xlabel("Contribution toward / away from repeat prediction • "+scale);grid(ax,"x")
        save(fig,folder,"phase5b_shap_"+role)
    return importance
