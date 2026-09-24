"""Shared visual language for static analytics and future product surfaces."""
from pathlib import Path
import textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from matplotlib.colors import LinearSegmentedColormap
import pandas as pd
import numpy as np

TOKENS = {
    "ink":"#172D3B", "muted":"#607482", "primary":"#157D82",
    "secondary":"#476780", "highlight":"#B67B27", "negative":"#B65B52",
    "soft":"#AEC8CA", "grid":"#E7ECEF", "background":"#FFFFFF",
    "font_family":["Segoe UI","DejaVu Sans"], "export_dpi":300,
}
C=TOKENS
def number(x,pos=None):
    return f"{x:,.0f}"
def money(x,pos=None):
    a=abs(x); prefix="−" if x<0 else ""
    return prefix+"£"+(f"{a/1e6:,.1f}M" if a>=1e6 else f"{a/1000:,.0f}K" if a>=1000 else f"{a:,.0f}")
def percent(x,pos=None): return f"{x:.0f}%"
def apply_theme():
    plt.rcParams.update({"font.family":C["font_family"],"font.size":11,
        "text.color":C["ink"],"axes.labelcolor":C["muted"],"xtick.color":C["muted"],
        "ytick.color":C["muted"],"axes.spines.top":False,"axes.spines.right":False,
        "axes.spines.left":False,"axes.spines.bottom":False,"axes.axisbelow":True,
        "xtick.major.size":0,"ytick.major.size":0,"axes.labelpad":12,
        "figure.facecolor":"white","axes.facecolor":"white","savefig.facecolor":"white",
        "svg.fonttype":"none","legend.frameon":False,"lines.linewidth":2.5})
def canvas(title,subtitle,footer="",height=6.7,left=.1):
    apply_theme()
    fig,ax=plt.subplots(figsize=(12,height))
    fig.subplots_adjust(left=left,right=.94,top=.76,bottom=.19)
    fig.text(.06,.95,"RETAIL INTELLIGENCE  /  CUSTOMER & REVENUE ANALYTICS",fontsize=9,color=C["primary"],weight="bold")
    fig.text(.06,.885,title,fontsize=21,weight="bold")
    fig.text(.06,.825,subtitle,fontsize=10.5,color=C["muted"])
    fig.text(.06,.045,footer or "Source: UCI Online Retail • validated project outputs",fontsize=9,color=C["muted"])
    return fig,ax
def grid(ax,axis="y"):
    ax.grid(axis=axis,color=C["grid"],lw=.8)
def save(fig,folder,name):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    for ext in ["png","svg"]:
        fig.savefig(folder/f"{name}.{ext}",dpi=C["export_dpi"],bbox_inches="tight",pad_inches=.22)
    plt.close(fig)
def callout(ax,x,y,label,offset=(12,16),ha="left"):
    ax.scatter([x],[y],s=45,color=C["highlight"],zorder=5)
    ax.annotate(label,(x,y),xytext=offset,textcoords="offset points",ha=ha,fontsize=10,
        color=C["ink"],weight="bold",bbox={"boxstyle":"round,pad=.45","fc":"white","ec":C["grid"]},
        arrowprops={"arrowstyle":"-","color":C["highlight"],"lw":1})
def month_axis(ax,months,partial):
    labels=[pd.Period(str(m)).strftime("%b %y")+("*" if p else "") for m,p in zip(months,partial)]
    ax.set_xticks(np.arange(len(labels)),labels,rotation=35,ha="right")
    for i,p in enumerate(partial):
        if p:ax.axvspan(i-.45,i+.45,color=C["highlight"],alpha=.08,lw=0)
def ranking(frame,value,label,title,subtitle,folder,name,currency=True):
    x=frame.sort_values(value,ascending=False).head(10).iloc[::-1]
    fig,ax=canvas(title,subtitle,height=8,left=.34)
    y=np.arange(len(x))
    ax.barh(y,x[value],height=.58,color=[C["soft"]]*(len(x)-1)+[C["primary"]])
    labels=["\n".join(textwrap.wrap(str(v).title(),32)) for v in x[label]]
    ax.set_yticks(y,labels,fontsize=10)
    fmt=money if currency else number
    ax.xaxis.set_major_formatter(FuncFormatter(fmt));grid(ax,"x")
    maximum=float(x[value].max());ax.set_xlim(0,maximum*1.22)
    for i,v in enumerate(x[value]):
        ax.text(v+maximum*.015,i,fmt(v),va="center",fontsize=10,weight="bold" if i==len(x)-1 else "normal")
    ax.set_xlabel(("Net accounting revenue" if value == "net_revenue" else "Gross merchandise purchase revenue") if currency else "Customers")
    save(fig,folder,name)
def activity_chart(months,new,returning,partial,folder,name):
    fig,ax=canvas("Returning customers drive the year-end peak",
        "Distinct identified purchasers • new = first observed purchase month",
        "* Partial month: limited follow-up; not comparable with complete months.")
    x=np.arange(len(months))
    for vals,label,color in [(new,"New customers",C["secondary"]),(returning,"Returning customers",C["primary"])]:
        ax.plot(x,vals,marker="o",ms=4,label=label,color=color)
    month_axis(ax,months,partial);grid(ax);ax.yaxis.set_major_formatter(FuncFormatter(number))
    ax.set_ylabel("Customers");ax.set_ylim(0,max(max(new),max(returning))*1.22)
    ax.legend(loc="upper left",bbox_to_anchor=(0,1.11),ncol=2,fontsize=10)
    save(fig,folder,name)
def heatmap_palette():
    cmap=LinearSegmentedColormap.from_list("retail_teal",["#F0F6F6","#95C2C4","#157D82","#113E47"])
    cmap.set_bad("#F3F5F6")
    return cmap
