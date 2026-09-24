"""Phase 4 charts sharing the project-wide business visual theme."""
import numpy as np
from matplotlib.ticker import FuncFormatter
from .theme import C,canvas,grid,save,money,number,percent,callout,ranking,activity_chart,heatmap_palette

def charts(rfm,s,pareto,cohort,trend,freq,folder):
    largest=s.loc[s.customer_count.idxmax()]
    top=s.loc[s.total_revenue.idxmax()]
    ranking(s,"customer_count","segment","Customer segments at a glance",
        f"{largest.segment}: {int(largest.customer_count):,} customers • largest segment",folder,"rfm_segment_distribution",False)
    ranking(s,"total_revenue","segment","Champions account for most customer revenue",
        f"{top.segment} contribute {top.revenue_pct:.2f}% • gross identified merchandise revenue",folder,"segment_revenue")
    x=s.sort_values("revenue_pct")
    fig,ax=canvas("Customer share and revenue share diverge",
        "Each segment's share of customers versus gross purchase revenue",height=8,left=.25)
    y=np.arange(len(x))
    ax.hlines(y,x.customer_pct,x.revenue_pct,color=C["soft"],lw=3)
    ax.scatter(x.customer_pct,y,color=C["secondary"],s=40,label="Customer share",zorder=3)
    ax.scatter(x.revenue_pct,y,color=C["primary"],s=55,label="Revenue share",zorder=3)
    ax.set_yticks(y,x.segment);ax.xaxis.set_major_formatter(FuncFormatter(percent));grid(ax,"x")
    ax.legend(loc="upper left",bbox_to_anchor=(0,1.13),ncol=2)
    ax.set_xlabel("Share of identified customers / gross purchase revenue")
    ax.set_xlim(0,max(x.customer_pct.max(),x.revenue_pct.max())*1.17)
    ax.text(top.revenue_pct+1,list(x.segment).index(top.segment),f"{top.revenue_pct:.1f}%",va="center",weight="bold",color=C["primary"])
    save(fig,folder,"segment_count_vs_revenue")
    crossing=pareto.loc[pareto.cumulative_revenue_pct.ge(80)].iloc[0]
    fig,ax=canvas("Revenue is concentrated in a minority of customers",
        f"{crossing.cumulative_customer_pct:.2f}% of customers account for at least 80% of purchase revenue",
        "Customers ranked by gross purchase revenue; no 80/20 assumption is imposed.")
    ax.plot(pareto.cumulative_customer_pct,pareto.cumulative_revenue_pct,color=C["primary"])
    ax.axhline(80,color=C["highlight"],ls="--",lw=1)
    ax.vlines(crossing.cumulative_customer_pct,0,80,color=C["highlight"],ls=":",lw=1)
    callout(ax,crossing.cumulative_customer_pct,crossing.cumulative_revenue_pct,f"80% at {crossing.cumulative_customer_pct:.2f}%",(28,-45))
    ax.set(xlim=(0,100),ylim=(0,105),xlabel="Customers ranked by purchase revenue",ylabel="Cumulative purchase revenue")
    ax.xaxis.set_major_formatter(FuncFormatter(percent));ax.yaxis.set_major_formatter(FuncFormatter(percent));grid(ax)
    save(fig,folder,"customer_pareto")
    matrix=cohort.pivot(index="cohort",columns="month_index",values="complete_retention")
    status=cohort.pivot(index="cohort",columns="month_index",values="period_status")
    m1=cohort.loc[cohort.month_index.eq(1)&cohort.period_status.eq("complete")]
    rate=m1.active_customers.sum()/m1.cohort_size.sum()
    fig,ax=canvas("Retention after the first purchase month",
        f"Month-1 retention: {rate:.2%} • weighted across {len(m1)} complete follow-up cohorts",
        "P = partial period; blank = future / unavailable. Neither is treated as zero retention.",height=8.5,left=.14)
    im=ax.imshow(matrix.to_numpy(),vmin=0,vmax=1,cmap=heatmap_palette(),aspect="auto")
    for i in range(len(matrix)):
        for j in range(len(matrix.columns)):
            v=matrix.iloc[i,j]
            if np.isfinite(v):ax.text(j,i,f"{v:.0%}",ha="center",va="center",fontsize=9,color="white" if v>.6 else C["ink"])
            elif status.iloc[i,j]=="partial":ax.text(j,i,"P",ha="center",va="center",fontsize=9,color=C["muted"])
    ax.set_xticks(range(len(matrix.columns)),matrix.columns);ax.set_yticks(range(len(matrix)),matrix.index)
    ax.set(xlabel="Months since first observed purchase",ylabel="First-observed purchase cohort")
    bar=fig.colorbar(im,ax=ax,pad=.025,fraction=.025,format=FuncFormatter(lambda v,p:f"{v:.0%}"));bar.outline.set_visible(False)
    save(fig,folder,"cohort_retention_heatmap")
    one=int(rfm.frequency.eq(1).sum())
    fig,ax=canvas("Most customers place a small number of orders",
        f"{one:,} customers purchased once ({one/len(rfm):.1%}) • both axes use logarithmic scales",
        "One point per observed purchase frequency; no frequency bins or customer records are invented.")
    ax.scatter(freq.frequency,freq.customer_count,s=35,color=C["primary"],alpha=.85)
    ax.set_xscale("log");ax.set_yscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(number));ax.yaxis.set_major_formatter(FuncFormatter(number))
    ax.set(xlabel="Distinct purchase orders",ylabel="Customers");grid(ax)
    save(fig,folder,"purchase_frequency_distribution")
    activity_chart(trend.purchase_month,trend.new_customers,trend.returning_customers,trend.is_partial,folder,"customer_activity_trend")
    risk=rfm.segment.isin(["At Risk","Cannot Lose Them"])
    fig,ax=canvas("Valuable inactive customers merit a closer look",
        "Gross purchase value versus days since last purchase • value axis is logarithmic",
        "Highlighted groups are rule-based segments, not churn predictions. Gross values may include refunded purchases.",height=7)
    ax.scatter(rfm.loc[~risk,"recency"],rfm.loc[~risk,"monetary"],s=12,color=C["soft"],alpha=.5,label="Other customers",rasterized=True)
    for label,color,marker in [("At Risk",C["secondary"],"o"),("Cannot Lose Them",C["highlight"],"D")]:
        g=rfm.loc[rfm.segment.eq(label)]
        ax.scatter(g.recency,g.monetary,s=20,color=color,alpha=.85,label=label,marker=marker,rasterized=True)
    ax.set_yscale("log");ax.yaxis.set_major_formatter(FuncFormatter(money));ax.xaxis.set_major_formatter(FuncFormatter(number))
    ax.set(xlabel="Days since last valid purchase",ylabel="Gross customer purchase revenue");grid(ax)
    ax.legend(loc="upper left",bbox_to_anchor=(0,1.12),ncol=3,fontsize=9)
    save(fig,folder,"recency_vs_monetary")
