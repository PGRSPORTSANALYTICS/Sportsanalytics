"""
Simulation Lab — Intern verktyg
Kör simulate_match N gånger och visar fullständig sannolikhetsanalys.
Endast tillgänglig internt via Replit port 7000.
"""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from monte_carlo_simulator import simulate_match, get_top_exact_scores

st.set_page_config(
    page_title="Simulation Lab",
    page_icon="🔬",
    layout="wide",
)

st.title("🔬 Simulation Lab")
st.caption("Intern simulationsverktyg — körs lokalt i Replit, delas ej")

# ── Inputs ────────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)

with col1:
    home_team = st.text_input("Hemmalag", value="Arsenal")
    xg_home = st.number_input("Hemma xG (λ)", min_value=0.1, max_value=6.0, value=1.60, step=0.05)

with col2:
    away_team = st.text_input("Bortalag", value="Chelsea")
    xg_away = st.number_input("Borta xG (λ)", min_value=0.1, max_value=6.0, value=1.20, step=0.05)

with col3:
    n_sim = st.select_slider(
        "Antal simuleringar",
        options=[100, 500, 1000, 5000, 10000, 50000, 100000],
        value=1000,
    )
    run_btn = st.button("▶ Kör simulering", type="primary", use_container_width=True)
    st.caption(f"Simulerar {n_sim:,} matcher")

# Optional: input live odds for EV-beräkning
with st.expander("📊 Lägg in odds för EV-analys (valfritt)"):
    oc1, oc2, oc3 = st.columns(3)
    odds_home = oc1.number_input("Hemmavinst", min_value=1.01, max_value=50.0, value=2.00, step=0.05)
    odds_draw = oc2.number_input("Oavgjort", min_value=1.01, max_value=50.0, value=3.50, step=0.05)
    odds_away = oc3.number_input("Bortavinst", min_value=1.01, max_value=50.0, value=3.80, step=0.05)
    oc4, oc5, oc6 = st.columns(3)
    odds_o25 = oc4.number_input("Över 2.5", min_value=1.01, max_value=20.0, value=1.90, step=0.05)
    odds_u25 = oc5.number_input("Under 2.5", min_value=1.01, max_value=20.0, value=1.90, step=0.05)
    odds_btts = oc6.number_input("BTTS Ja", min_value=1.01, max_value=20.0, value=1.80, step=0.05)

st.divider()

# ── Run ───────────────────────────────────────────────────────────────────────
if run_btn or "sim_result" in st.session_state:
    if run_btn:
        with st.spinner(f"Simulerar {n_sim:,} matcher..."):
            result = simulate_match(xg_home, xg_away, n_sim=n_sim)
        st.session_state["sim_result"] = result
        st.session_state["sim_params"] = (home_team, away_team, xg_home, xg_away, n_sim)
    else:
        result = st.session_state["sim_result"]
        home_team, away_team, xg_home, xg_away, n_sim = st.session_state["sim_params"]

    ht = result["one_x_two"]
    st.subheader(f"📊 {home_team} vs {away_team} — {n_sim:,} simuleringar (xG: {xg_home:.2f} – {xg_away:.2f})")

    # ── 1X2 + Totals ─────────────────────────────────────────────────────────
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Hemmavinst", f"{ht['1']:.1%}", delta=f"EV {(ht['1']*odds_home-1)*100:.1f}%")
    m2.metric("Oavgjort",   f"{ht['X']:.1%}", delta=f"EV {(ht['X']*odds_draw-1)*100:.1f}%")
    m3.metric("Bortavinst", f"{ht['2']:.1%}", delta=f"EV {(ht['2']*odds_away-1)*100:.1f}%")
    m4.metric("Över 2.5",   f"{result['over_25']:.1%}", delta=f"EV {(result['over_25']*odds_o25-1)*100:.1f}%")
    m5.metric("Under 2.5",  f"{result['under_25']:.1%}", delta=f"EV {(result['under_25']*odds_u25-1)*100:.1f}%")
    m6.metric("BTTS Ja",    f"{result['btts_yes']:.1%}", delta=f"EV {(result['btts_yes']*odds_btts-1)*100:.1f}%")

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Sannolikheter", "⚽ Exakta resultat", "📈 Fördelning", "🎯 EV-analys"])

    # ── Tab 1: All markets ────────────────────────────────────────────────────
    with tab1:
        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("**1X2**")
            st.dataframe(pd.DataFrame({
                "Marknad": ["Hemmavinst", "Oavgjort", "Bortavinst"],
                "Sannolikhet": [f"{ht['1']:.1%}", f"{ht['X']:.1%}", f"{ht['2']:.1%}"],
                "Fair odds": [f"{1/ht['1']:.2f}", f"{1/ht['X']:.2f}", f"{1/ht['2']:.2f}"],
            }), use_container_width=True, hide_index=True)

            st.markdown("**BTTS**")
            st.dataframe(pd.DataFrame({
                "Marknad": ["Ja", "Nej"],
                "Sannolikhet": [f"{result['btts_yes']:.1%}", f"{result['btts_no']:.1%}"],
                "Fair odds": [f"{1/result['btts_yes']:.2f}", f"{1/result['btts_no']:.2f}"],
            }), use_container_width=True, hide_index=True)

        with c2:
            st.markdown("**Totalmål (Over/Under)**")
            totals = [
                ("Ö 0.5", result['over_05'], 1-result['over_05']),
                ("Ö 1.5", result['over_15'], result['under_15']),
                ("Ö 2.5", result['over_25'], result['under_25']),
                ("Ö 3.5", result['over_35'], result['under_35']),
                ("Ö 4.5", result['over_45'], result['under_45']),
            ]
            rows = []
            for label, over_p, under_p in totals:
                rows.append({
                    "Linje": label,
                    "Over %": f"{over_p:.1%}",
                    "Under %": f"{under_p:.1%}",
                    "Fair Over": f"{1/over_p:.2f}" if over_p > 0 else "—",
                    "Fair Under": f"{1/under_p:.2f}" if under_p > 0 else "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        with c3:
            st.markdown("**Asiatiska handicap (hemma)**")
            ahs = [
                ("AH -1.5", result.get("home_ah_-1.5", 0)),
                ("AH -1.0", result.get("home_ah_-1.0", 0)),
                ("AH -0.5", result.get("home_ah_-0.5", 0)),
                ("AH +0.5", result.get("home_ah_+0.5", 0)),
                ("AH +1.0", result.get("home_ah_+1.0", 0)),
                ("AH +1.5", result.get("home_ah_+1.5", 0)),
            ]
            ah_rows = []
            for label, p in ahs:
                ah_rows.append({
                    "Handicap": label,
                    "Sannolikhet": f"{p:.1%}",
                    "Fair odds": f"{1/p:.2f}" if p > 0 else "—",
                })
            st.dataframe(pd.DataFrame(ah_rows), use_container_width=True, hide_index=True)

    # ── Tab 2: Exact scores ───────────────────────────────────────────────────
    with tab2:
        scores_raw = result.get("scores", {})
        top_scores = get_top_exact_scores(result, top_n=20)

        labels = [s["score"] for s in top_scores]
        probs  = [s["probability_pct"] for s in top_scores]

        fig = go.Figure(go.Bar(
            x=labels, y=probs,
            marker_color=["#00cc44" if i < 3 else "#2196F3" if i < 8 else "#888"
                          for i in range(len(labels))],
            text=[f"{p:.1f}%" for p in probs],
            textposition="outside",
        ))
        fig.update_layout(
            title=f"Topp 20 exakta resultat — {home_team} vs {away_team}",
            xaxis_title="Resultat",
            yaxis_title="Sannolikhet (%)",
            height=420,
            paper_bgcolor="#0f1117",
            plot_bgcolor="#0f1117",
            font_color="white",
        )
        st.plotly_chart(fig, use_container_width=True)

        score_df = pd.DataFrame(top_scores)
        score_df["probability"] = score_df["probability"].apply(lambda x: f"{x:.2%}")
        score_df["probability_pct"] = score_df["probability_pct"].apply(lambda x: f"{x:.2f}%")
        score_df["fair_odds"] = score_df["fair_odds"].apply(lambda x: f"{x:.2f}")
        score_df.columns = ["Resultat", "Sannolikhet", "Sannolikhet %", "Fair odds"]
        st.dataframe(score_df, use_container_width=True, hide_index=True)

    # ── Tab 3: Goal distribution ──────────────────────────────────────────────
    with tab3:
        np.random.seed(None)
        home_sims = np.random.poisson(xg_home, n_sim)
        away_sims = np.random.poisson(xg_away, n_sim)
        total_sims = home_sims + away_sims

        c1, c2 = st.columns(2)
        with c1:
            fig2 = go.Figure()
            for label, data, color in [
                (f"{home_team} mål", home_sims, "#2196F3"),
                (f"{away_team} mål", away_sims, "#F44336"),
            ]:
                vals, counts = np.unique(data, return_counts=True)
                fig2.add_trace(go.Bar(
                    x=vals, y=counts/n_sim,
                    name=label, marker_color=color, opacity=0.7,
                ))
            fig2.update_layout(
                barmode="overlay",
                title="Målfördelning per lag",
                xaxis_title="Antal mål",
                yaxis_title="Sannolikhet",
                height=380,
                paper_bgcolor="#0f1117",
                plot_bgcolor="#0f1117",
                font_color="white",
            )
            st.plotly_chart(fig2, use_container_width=True)

        with c2:
            vals, counts = np.unique(total_sims, return_counts=True)
            fig3 = go.Figure(go.Bar(
                x=vals, y=counts/n_sim,
                marker_color=["#4CAF50" if v > 2.5 else "#F44336" for v in vals],
                text=[f"{c/n_sim:.1%}" for c in counts],
                textposition="outside",
            ))
            fig3.add_vline(x=2.5, line_dash="dash", line_color="white",
                          annotation_text="2.5-gränsen")
            fig3.update_layout(
                title="Totala mål — fördelning",
                xaxis_title="Totala mål",
                yaxis_title="Sannolikhet",
                height=380,
                paper_bgcolor="#0f1117",
                plot_bgcolor="#0f1117",
                font_color="white",
            )
            st.plotly_chart(fig3, use_container_width=True)

        st.metric("Genomsnittliga totalmål", f"{total_sims.mean():.2f}")

    # ── Tab 4: EV analysis ────────────────────────────────────────────────────
    with tab4:
        st.markdown("Ange odds ovan i expanderingsrutan för automatisk EV-beräkning.")

        markets = {
            "Hemmavinst":  (ht['1'],              odds_home),
            "Oavgjort":    (ht['X'],              odds_draw),
            "Bortavinst":  (ht['2'],              odds_away),
            "Över 2.5":    (result['over_25'],    odds_o25),
            "Under 2.5":   (result['under_25'],   odds_u25),
            "BTTS Ja":     (result['btts_yes'],   odds_btts),
        }

        ev_rows = []
        for market, (prob, odds) in markets.items():
            ev = prob * odds - 1
            fair = 1 / prob if prob > 0 else 0
            ev_rows.append({
                "Marknad": market,
                "Modell %": f"{prob:.1%}",
                "Bokmaker odds": f"{odds:.2f}",
                "Fair odds": f"{fair:.2f}",
                "EV %": f"{ev*100:+.1f}%",
                "Värde?": "✅ JA" if ev > 0.05 else ("🔶 Marginellt" if ev > 0 else "❌ NEJ"),
            })

        ev_df = pd.DataFrame(ev_rows)
        st.dataframe(
            ev_df.style.apply(
                lambda col: ["background-color: #1a3a1a" if "✅" in v
                             else "background-color: #3a2a0a" if "🔶" in v
                             else "background-color: #2a1a1a" if "❌" in v
                             else "" for v in col],
                subset=["Värde?"]
            ),
            use_container_width=True,
            hide_index=True,
        )

else:
    st.info("Ange xG-värden och klicka **Kör simulering** för att starta.")
    st.markdown("""
    **Hur använder du det här?**
    - Ange förväntade mål (xG) för hemma- och bortalag
    - Välj antal simuleringar (1 000 = snabbt, 100 000 = exakt)
    - Jämför modellsannolikheten mot bokmakare-odds för EV
    - Resultaten delas inte — detta är ett internt analysverktyg
    """)
