"""Restyle existing calculated outputs without rerunning analytics."""
from pathlib import Path
import sys,json,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from ecommerce_customer_intelligence.analytics.charts import make_charts
from ecommerce_customer_intelligence.analytics.customer_charts import charts
from ecommerce_customer_intelligence.analytics.theme import TOKENS

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    paths=[ROOT/"data/raw/Online Retail.xlsx",*sorted((ROOT/"data/processed").glob("*csv*")),
        ROOT/"reports/metrics/business_kpis.json",ROOT/"reports/metrics/customer_intelligence.json"]
    before={str(p.relative_to(ROOT)):digest(p) for p in paths}
    def read(name):return pd.read_csv(ROOT/f"data/processed/{name}.csv")
    k=json.loads((ROOT/"reports/metrics/business_kpis.json").read_text())["kpis"]
    make_charts(k,{name:read(name) for name in ["monthly","countries","products","customer_features"]},ROOT/"reports/figures")
    charts(read("rfm_customers"),read("segment_summary"),read("customer_concentration"),
        read("cohort_retention"),read("customer_lifecycle_trend"),read("customer_frequency_distribution"),ROOT/"reports/figures")
    after={str(p.relative_to(ROOT)):digest(p) for p in paths}
    if before!=after:raise RuntimeError("Analytical input changed during rendering")
    (ROOT/"docs/visual_theme.json").write_text(json.dumps(TOKENS,indent=2),encoding="utf-8")
    (ROOT/"reports/metrics/visualization_integrity.json").write_text(json.dumps({
        "inputs_unchanged":True,"input_sha256":before,"png_count":len(list((ROOT/"reports/figures").glob("*.png"))),
        "svg_count":len(list((ROOT/"reports/figures").glob("*.svg"))),"dpi":TOKENS["export_dpi"]},indent=2),encoding="utf-8")
    print("Rendered 15 figures in PNG and SVG; all analytical input checksums unchanged.")
if __name__=="__main__":main()
