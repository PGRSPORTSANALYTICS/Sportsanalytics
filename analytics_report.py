import argparse, os, math
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

# ---------- Helpers ----------
def safe_cols(df, cols):
    missing = [c for c in cols if c not in df.columns]
    return len(missing) == 0, missing

def to_bool(x):
    if isinstance(x, (int, float)): return bool(int(x))
    if isinstance(x, str): return x.strip().lower() in ["1","true","yes","y"]
    return False

def result_to_profit(row):
    stake = row.get("stake", 1.0) or 1.0
    odds  = row.get("odds", np.nan)
    res   = str(row.get("result","")).upper()
    if res in ["WIN","W","1"]:  return stake*(odds-1.0)
    if res in ["PUSH","VOID","V"]: return 0.0
    return -stake

def ensure_dir(p):
    os.makedirs(p, exist_ok=True)

def save_df(df, path):
    df.to_csv(path, index=False)
    print(f"✔ saved: {path}")

def save_bar(series, title, ylabel, path, rot=0):
    plt.figure()
    series.plot(kind="bar")
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xticks(rotation=rot, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()
    print(f"✔ saved: {path}")

def save_scatter(x, y, title, path):
    plt.figure()
    plt.scatter(x, y, alpha=0.6)
    m, b = np.polyfit(x, y, 1)
    xs = np.linspace(min(x), max(x), 50)
    plt.plot(xs, m*xs+b)
    plt.title(title)
    plt.xlabel("EV (model)")
    plt.ylabel("Actual ROI")
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()
    print(f"✔ saved: {path}")

# ---------- Main ----------
def run_report(csv_path, out_dir):
    ensure_dir(out_dir)
    df = pd.read_csv(csv_path)

    # Normalize columns
    df.columns = [c.strip().lower() for c in df.columns]
    if "stake" not in df.columns: df["stake"] = 1.0
    if "odds"  not in df.columns: df["odds"]  = np.nan
    if "ev"    not in df.columns: df["ev"]    = np.nan
    if "combo" not in df.columns: df["combo"] = df.get("market","Unknown")
    if "market" not in df.columns: df["market"] = df["combo"]

    # Profit calc
    if "profit" not in df.columns:
        df["profit"] = df.apply(result_to_profit, axis=1)

    # Basic filters
    if "settled" in df.columns:
        settled_mask = df["settled"].apply(to_bool)
        df_settled = df[settled_mask].copy()
    else:
        df_settled = df.copy()

    # -------- 1) League ROI Heatmap --------
    need = ["league","profit","stake"]
    ok, miss = safe_cols(df_settled, need)
    if ok:
        league = (df_settled
                  .groupby("league")
                  .agg(games=("profit","count"),
                       units=("profit","sum"),
                       staked=("stake","sum")))
        league["roi_%"] = (league["units"]/league["staked"])*100
        league = league.sort_values("roi_%", ascending=False).reset_index()
        save_df(league, os.path.join(out_dir,"league_roi.csv"))
        save_bar(league.set_index("league")["roi_%"],
                 "ROI per liga (%)","ROI %", os.path.join(out_dir,"league_roi.png"), rot=45)
    else:
        print(f"⚠ Skipping league ROI (saknar: {miss})")

    # -------- 2) xG differential buckets --------
    need = ["home_xg","away_xg","profit","stake"]
    ok, miss = safe_cols(df_settled, need)
    if ok:
        df_settled["xg_diff"] = (df_settled["home_xg"] - df_settled["away_xg"]).abs()
        bins  = [0,0.3,0.7,1.0,9]
        labels= ["0–0.3","0.3–0.7","0.7–1.0","1.0+"]
        df_settled["xg_bucket"] = pd.cut(df_settled["xg_diff"], bins=bins, labels=labels, include_lowest=True)
        xg = (df_settled
              .groupby("xg_bucket")
              .agg(games=("profit","count"),
                   hitrate=("profit", lambda s: (s>0).mean()*100),
                   units=("profit","sum"),
                   staked=("stake","sum")))
        xg["roi_%"] = (xg["units"]/xg["staked"])*100
        xg = xg.reset_index()
        save_df(xg, os.path.join(out_dir,"xg_buckets.csv"))
        save_bar(xg.set_index("xg_bucket")["roi_%"],
                 "ROI per xG-differens","ROI %", os.path.join(out_dir,"xg_roi.png"))
    else:
        print(f"⚠ Skipping xG analysis (saknar: {miss})")

    # -------- 3) EV vs Actual ROI curve --------
    need = ["ev","profit","stake"]
    ok, miss = safe_cols(df_settled, need)
    if ok:
        # bucket EV in 2.5%-steg
        df_ev = df_settled.dropna(subset=["ev"]).copy()
        df_ev["ev_bucket"] = (np.round(df_ev["ev"].astype(float)/0.025)*0.025).clip(-1,1)
        ev_agg = (df_ev.groupby("ev_bucket")
                  .agg(games=("profit","count"),
                       units=("profit","sum"),
                       staked=("stake","sum")))
        ev_agg["roi"] = ev_agg["units"]/ev_agg["staked"]
        ev_agg = ev_agg[(ev_agg["games"]>=10)].reset_index()
        save_df(ev_agg, os.path.join(out_dir,"ev_vs_roi.csv"))
        if len(ev_agg):
            save_scatter(ev_agg["ev_bucket"].values, ev_agg["roi"].values,
                         "EV vs faktisk ROI", os.path.join(out_dir,"ev_vs_roi.png"))
    else:
        print(f"⚠ Skipping EV calibration (saknar: {miss})")

    # -------- 4) SGP Combination efficiency --------
    need = ["combo","profit","stake"]
    ok, miss = safe_cols(df_settled, need)
    if ok:
        # Normalisera combo-typ (t.ex. 'BTTS + Over2.5' => sorterade tokens)
        def norm_combo(s):
            if pd.isna(s): return "Unknown"
            parts = [p.strip() for p in str(s).split("+")]
            parts = sorted([p for p in parts if p])
            return " + ".join(parts) if parts else "Unknown"
        df_settled["combo_norm"] = df_settled["combo"].apply(norm_combo)

        sgp = (df_settled
               .groupby("combo_norm")
               .agg(games=("profit","count"),
                    hitrate=("profit", lambda s: (s>0).mean()*100),
                    units=("profit","sum"),
                    staked=("stake","sum")))
        sgp["roi_%"] = (sgp["units"]/sgp["staked"])*100
        sgp = sgp.sort_values(["roi_%","games"], ascending=[False,False]).reset_index()
        save_df(sgp, os.path.join(out_dir,"sgp_combo_efficiency.csv"))
        top = sgp[sgp["games"]>=20].head(12).set_index("combo_norm")["roi_%"]
        if len(top):
            save_bar(top, "Topp-SGP combos (ROI %)", "ROI %", os.path.join(out_dir,"sgp_combo_top.png"), rot=45)
    else:
        print(f"⚠ Skipping SGP combo analysis (saknar: {miss})")

    # -------- 5) Momentum test (form bias) --------
    need = ["home_form_last5","away_form_last5","profit","stake"]
    ok, miss = safe_cols(df_settled, need)
    if ok:
        def parse_form(s):
            # exempel: "WDLWW" -> poäng 3/1/0 = 3.0 medel
            if pd.isna(s): return np.nan
            pts = {"W":3,"D":1,"L":0}
            arr = [pts.get(ch.upper(), np.nan) for ch in str(s) if ch.strip()]
            arr = [x for x in arr if not np.isnan(x)]
            return np.mean(arr) if arr else np.nan
        df_settled["home_form_pts"] = df_settled["home_form_last5"].apply(parse_form)
        df_settled["away_form_pts"] = df_settled["away_form_last5"].apply(parse_form)
        df_settled["form_diff"] = (df_settled["home_form_pts"] - df_settled["away_form_pts"]).abs()

        bins  = [0,0.5,1.5,9]
        labels= ["Even","Moderate","Strong"]
        df_settled["form_bucket"] = pd.cut(df_settled["form_diff"], bins=bins, labels=labels, include_lowest=True)

        form = (df_settled
                .groupby("form_bucket")
                .agg(games=("profit","count"),
                     units=("profit","sum"),
                     staked=("stake","sum")))
        form["roi_%"] = (form["units"]/form["staked"])*100
        form = form.reset_index()
        save_df(form, os.path.join(out_dir,"momentum_form.csv"))
        save_bar(form.set_index("form_bucket")["roi_%"],
                 "ROI vs form-skillnad","ROI %", os.path.join(out_dir,"momentum_form.png"))
    else:
        print(f"⚠ Skipping momentum test (saknar: {miss})")

    # ------- Executive summary -------
    summary_rows = []
    if 'league_roi.csv' in os.listdir(out_dir):
        top_league = pd.read_csv(os.path.join(out_dir,'league_roi.csv')).head(3)
        worst_league= pd.read_csv(os.path.join(out_dir,'league_roi.csv')).tail(3)
        summary_rows.append(("Top ligor (ROI%)", ", ".join(f"{r.league} {r.roi_%:.1f}%" for _,r in top_league.iterrows())))
        summary_rows.append(("Sämsta ligor (ROI%)", ", ".join(f"{r.league} {r.roi_%:.1f}%" for _,r in worst_league.iterrows())))

    if 'xg_buckets.csv' in os.listdir(out_dir):
        xg = pd.read_csv(os.path.join(out_dir,'xg_buckets.csv')).sort_values("roi_%", ascending=False)
        best_bucket = xg.iloc[0]
        summary_rows.append(("Bästa xG-spann", f"{best_bucket.xg_bucket} (ROI {best_bucket.roi_%:.1f}%, hit {best_bucket.hitrate:.1f}%)"))

    if 'sgp_combo_efficiency.csv' in os.listdir(out_dir):
        sgp = pd.read_csv(os.path.join(out_dir,'sgp_combo_efficiency.csv'))
        sgp_top = sgp[sgp["games"]>=20].sort_values("roi_%", ascending=False).head(3)
        if len(sgp_top):
            summary_rows.append(("Top SGP-combos", ", ".join(f"{r.combo_norm} ({r.roi_%:.1f}%, n={int(r.games)})" for _,r in sgp_top.iterrows())))

    summary = pd.DataFrame(summary_rows, columns=["Nyckelpunkt","Rekommendation/insikt"])
    save_df(summary, os.path.join(out_dir,"EXEC_SUMMARY.csv"))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Sökväg till predictions.csv")
    ap.add_argument("--out", default="./report_out", help="Mapp för rapporter")
    args = ap.parse_args()
    run_report(args.csv, args.out)
