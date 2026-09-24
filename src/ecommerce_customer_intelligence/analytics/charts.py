"""Phase 3 charts sharing the project-wide business visual theme."""
import numpy as np
from matplotlib.ticker import FuncFormatter
from .theme import C,canvas,grid,save,money,number,callout,month_axis,ranking,activity_chart

def make_charts(k,tables,folder):
    m=tables["monthly"];x=np.arange(len(m))
    for col,title,name,currency in [
        ("net_revenue","November leads full-month revenue","monthly_net_revenue",True),
        ("orders","Purchase activity builds toward November","monthly_orders",False)]:
        fig,ax=canvas(title,"Monthly "+("net accounting revenue" if currency else "distinct valid merchandise orders"),
            "* Partial December 2011. Highlighted period is not a comparable full month.")
        ax.plot(x,m[col],color=C["primary"],marker="o",ms=4)
        ax.fill_between(x,m[col],color=C["primary"],alpha=.07)
        month_axis(ax,m.month,m.is_partial);grid(ax)
        ax.yaxis.set_major_formatter(FuncFormatter(money if currency else number))
        ax.set_ylabel("Net revenue" if currency else "Valid purchase orders")
        complete=np.flatnonzero(~m.is_partial.to_numpy());idx=complete[np.argmax(m.iloc[complete][col].to_numpy())]
        callout(ax,idx,m.iloc[idx][col],("Peak • "+(money if currency else number)(m.iloc[idx][col])),(-15,22),ha="right")
        ax.set_ylim(0,m[col].max()*1.28)
        save(fig,folder,name)
    ranking(tables["countries"],"net_revenue","Country","The UK anchors retail revenue",
        "Top 10 countries • net accounting revenue, including adjustments",folder,"top_countries")
    ranking(tables["products"],"gross_revenue","description","The leading products by purchase revenue",
        "Top 10 product codes • valid merchandise sales, before returns",folder,"top_products")
    fig,ax=canvas("From gross sales to net revenue",
        f"Returns absorb {k['return_value_rate_pct']:.2f}% of gross sales • adjustments remain visible",
        "Accounting scope includes anonymous and service lines; duplicate contributions are excluded.")
    changes=[k["gross_sales"],-k["return_cancellation_value"],k["signed_adjustments"]]
    running=0
    for i,v in enumerate(changes):
        end=running+v;bottom=min(running,end)
        ax.bar(i,abs(v),bottom=bottom,width=.55,color=C["primary"] if i==0 else C["negative"] if i==1 else C["highlight"])
        if i<2:ax.plot([i+.28,i+.72],[end,end],color=C["muted"],lw=.8,ls=":")
        ax.text(i,max(running,end)+k["gross_sales"]*.035,("−" if v<0 else "")+money(abs(v)),ha="center",weight="bold")
        running=end
    ax.bar(3,k["net_revenue"],width=.55,color=C["ink"])
    ax.text(3,k["net_revenue"]+k["gross_sales"]*.035,money(k["net_revenue"]),ha="center",weight="bold")
    ax.set_xticks(range(4),["Gross sales","Returns / cancellations","Other adjustments","Net revenue"])
    ax.set_ylim(0,k["gross_sales"]*1.22);ax.yaxis.set_major_formatter(FuncFormatter(money));grid(ax)
    save(fig,folder,"revenue_reconciliation")
    activity_chart(m.month,m.new_customers,m.repeat_customers,m.is_partial,folder,"new_vs_repeat_customers")
    c=tables["customer_features"];values=c.loc[c.gross_revenue.gt(0),"gross_revenue"]
    fig,ax=canvas("Customer value spans several orders of magnitude",
        "Gross merchandise purchase revenue per purchasing customer • logarithmic value axis",
        "All positive customer values are shown; no outliers are removed.")
    ax.hist(values,bins=np.geomspace(values.min(),values.max(),36),color=C["primary"],edgecolor="white",linewidth=.7)
    ax.set_xscale("log");ax.xaxis.set_major_formatter(FuncFormatter(money));ax.yaxis.set_major_formatter(FuncFormatter(number))
    ax.set_xlabel("Customer purchase revenue");ax.set_ylabel("Customers");grid(ax)
    ax.axvline(values.median(),color=C["highlight"],ls="--",lw=1.5)
    ax.text(.98,.92,f"Median {money(values.median())}",transform=ax.transAxes,ha="right",weight="bold",color=C["highlight"])
    save(fig,folder,"customer_revenue_distribution")
