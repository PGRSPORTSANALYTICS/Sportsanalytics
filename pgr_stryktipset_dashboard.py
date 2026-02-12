import streamlit as st
import pandas as pd
import sqlite3
import json
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px

DB_PATH = "app.db"

def get_stryk_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def render_stryktipset_dashboard():
    st.markdown("## 🎰 Stryktipset System")
    st.caption("AI-Powered Reduced System Generator | Jackpot Strategy")

    try:
        conn = get_stryk_db()
    except Exception as e:
        st.error(f"Could not connect to Stryktipset database: {e}")
        return

    tabs = st.tabs(["📋 Coupons", "🔮 Predictions", "⚙️ Systems", "📊 Results & Scoring"])

    with tabs[0]:
        render_coupons_tab(conn)

    with tabs[1]:
        render_predictions_tab(conn)

    with tabs[2]:
        render_systems_tab(conn)

    with tabs[3]:
        render_scoring_tab(conn)

    conn.close()


def render_coupons_tab(conn):
    st.markdown("### Active Coupons")

    coupons = conn.execute("SELECT * FROM stryk_coupons ORDER BY created_at DESC").fetchall()

    if not coupons:
        st.info("No coupons created yet. Use the API to create one.")
        return

    for c in coupons:
        status_colors = {"draft": "🟡", "published": "🟢", "settled": "🔵"}
        icon = status_colors.get(c["status"], "⚪")

        with st.expander(f"{icon} {c['name']} (ID: {c['id']}) — {c['status'].upper()}", expanded=(c["status"] != "settled")):
            col1, col2, col3 = st.columns(3)
            col1.metric("Status", c["status"].upper())
            col2.metric("Week", c["week_tag"] or "—")
            col3.metric("Created", str(c["created_at"])[:16] if c["created_at"] else "—")

            matches = conn.execute(
                "SELECT * FROM stryk_matches WHERE coupon_id = ? ORDER BY match_no",
                (c["id"],)
            ).fetchall()

            if matches:
                rows = []
                for m in matches:
                    result_display = m["result"] if m["result"] else "—"
                    odds_str = f"{m['odds_1'] or '—'} / {m['odds_x'] or '—'} / {m['odds_2'] or '—'}"
                    pub_str = ""
                    if m["public_pct_1"] is not None:
                        pub_str = f"{m['public_pct_1']:.0f}% / {m['public_pct_x']:.0f}% / {m['public_pct_2']:.0f}%"

                    rows.append({
                        "#": m["match_no"],
                        "Home": m["home_team"],
                        "Away": m["away_team"],
                        "League": m["league"] or "—",
                        "Odds (1/X/2)": odds_str,
                        "Public %": pub_str or "—",
                        "Result": result_display
                    })

                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)


def render_predictions_tab(conn):
    st.markdown("### Model Predictions")

    coupons = conn.execute("SELECT * FROM stryk_coupons ORDER BY created_at DESC").fetchall()
    if not coupons:
        st.info("No coupons available.")
        return

    coupon_options = {f"{c['name']} (ID: {c['id']})": c["id"] for c in coupons}
    selected = st.selectbox("Select Coupon", list(coupon_options.keys()), key="pred_coupon")
    coupon_id = coupon_options[selected]

    probs = conn.execute("""
        SELECT sp.*, sm.match_no, sm.home_team, sm.away_team, sm.odds_1, sm.odds_x, sm.odds_2, sm.result
        FROM stryk_probs sp
        JOIN stryk_matches sm ON sp.match_id = sm.id
        WHERE sp.coupon_id = ?
        ORDER BY sm.match_no
    """, (coupon_id,)).fetchall()

    if not probs:
        st.warning("No predictions yet. Run /predict via the API first.")
        return

    rows = []
    picks_correct = 0
    picks_total = 0

    for p in probs:
        p1, px, p2 = p["p1"], p["px"], p["p2"]
        best = max(p1, px, p2)
        if best == p1:
            pick = "1"
        elif best == px:
            pick = "X"
        else:
            pick = "2"

        result = p["result"]
        correct = ""
        if result:
            picks_total += 1
            if pick == result:
                correct = "✅"
                picks_correct += 1
            else:
                correct = "❌"

        rows.append({
            "#": p["match_no"],
            "Home": p["home_team"],
            "Away": p["away_team"],
            "P(1)": f"{p1:.1%}",
            "P(X)": f"{px:.1%}",
            "P(2)": f"{p2:.1%}",
            "Pick": pick,
            "Result": result or "—",
            "": correct,
            "Model": p["model_version"] or "—"
        })

    if picks_total > 0:
        col1, col2 = st.columns(2)
        col1.metric("Picks Correct", f"{picks_correct}/{picks_total}")
        col2.metric("Hit Rate", f"{picks_correct/picks_total:.0%}")

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("#### Probability Distribution")
    prob_data = []
    for p in probs:
        prob_data.append({"Match": f"#{p['match_no']}", "Outcome": "1", "Probability": p["p1"]})
        prob_data.append({"Match": f"#{p['match_no']}", "Outcome": "X", "Probability": p["px"]})
        prob_data.append({"Match": f"#{p['match_no']}", "Outcome": "2", "Probability": p["p2"]})

    fig = px.bar(
        pd.DataFrame(prob_data),
        x="Match", y="Probability", color="Outcome",
        barmode="group",
        color_discrete_map={"1": "#4CAF50", "X": "#FFC107", "2": "#F44336"},
        height=350
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="white",
        yaxis_tickformat=".0%",
        margin=dict(l=20, r=20, t=30, b=20)
    )
    st.plotly_chart(fig, use_container_width=True)


def render_systems_tab(conn):
    st.markdown("### Generated Systems")

    systems = conn.execute("""
        SELECT ss.*, sc.name as coupon_name
        FROM stryk_systems ss
        JOIN stryk_coupons sc ON ss.coupon_id = sc.id
        ORDER BY ss.created_at DESC
    """).fetchall()

    if not systems:
        st.info("No systems generated yet. Use the API to generate one.")
        return

    for sys in systems:
        rules = json.loads(sys["rules_json"]) if isinstance(sys["rules_json"], str) else (sys["rules_json"] or {})

        with st.expander(f"System #{sys['id']} — {sys['coupon_name']} | {sys['final_rows']} rows", expanded=True):
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Total Rows", sys["final_rows"])
            col2.metric("Spikes", sys["spik_count"])
            col3.metric("Half Guards", sys["half_count"])
            col4.metric("Full Guards", sys["full_count"])
            col5.metric("Theoretical", rules.get("theoretical_rows", "—"))

            st.caption(sys["system_summary"] or "")

            allowed = rules.get("allowed", {})
            if allowed:
                st.markdown("**Match Classification:**")
                class_rows = []
                for no_str in sorted(allowed.keys(), key=lambda x: int(x)):
                    outcomes = allowed[no_str]
                    if len(outcomes) == 1:
                        label = f"🔒 Spike ({outcomes[0]})"
                    elif len(outcomes) == 2:
                        label = f"↔️ Half ({'/'.join(outcomes)})"
                    else:
                        label = f"🛡️ Full (1/X/2)"
                    class_rows.append({"Match": f"#{no_str}", "Type": label, "Allowed": ", ".join(outcomes)})

                st.dataframe(pd.DataFrame(class_rows), use_container_width=True, hide_index=True)

            rows = conn.execute(
                "SELECT * FROM stryk_rows WHERE system_id = ? ORDER BY row_prob DESC LIMIT 20",
                (sys["id"],)
            ).fetchall()

            if rows:
                st.markdown(f"**Top 20 Rows by Probability** (of {sys['final_rows']} total):")
                row_data = []
                for r in rows:
                    row_str = r["row_string"]
                    formatted = " ".join(row_str)
                    row_data.append({
                        "#": r["row_no"],
                        "Row": formatted,
                        "Model Prob": f"{r['row_prob']:.2e}" if r["row_prob"] else "—",
                        "Public Prob": f"{r['row_public_prob']:.2e}" if r["row_public_prob"] else "—",
                        "Contrarian": f"{r['contrarian_score']:.1f}" if r["contrarian_score"] else "—"
                    })

                st.dataframe(pd.DataFrame(row_data), use_container_width=True, hide_index=True)


def render_scoring_tab(conn):
    st.markdown("### System Scoring & Results")

    scores = conn.execute("""
        SELECT sss.*, sc.name as coupon_name
        FROM stryk_system_scores sss
        JOIN stryk_coupons sc ON sss.coupon_id = sc.id
        ORDER BY sss.computed_at DESC
        LIMIT 20
    """).fetchall()

    if not scores:
        st.info("No systems scored yet. Settle a coupon and score a system via the API.")

        settled = conn.execute("SELECT * FROM stryk_coupons WHERE status = 'settled' ORDER BY created_at DESC").fetchall()
        if settled:
            st.markdown("**Settled coupons ready for scoring:**")
            for c in settled:
                st.write(f"- {c['name']} (ID: {c['id']})")
        return

    col1, col2, col3, col4 = st.columns(4)
    avg_best = sum(s["best_correct"] for s in scores) / len(scores) if scores else 0
    ge10 = sum(1 for s in scores if s["best_correct"] >= 10)
    ge12 = sum(1 for s in scores if s["best_correct"] >= 12)
    eq13 = sum(1 for s in scores if s["best_correct"] == 13)

    col1.metric("Avg Best Correct", f"{avg_best:.1f}/13")
    col2.metric("10+ Correct", f"{ge10}/{len(scores)}")
    col3.metric("12+ Correct", f"{ge12}/{len(scores)}")
    col4.metric("13/13 Jackpot", f"{eq13}/{len(scores)}")

    for s in scores:
        dist = json.loads(s["dist_json"]) if isinstance(s["dist_json"], str) else (s["dist_json"] or {})

        with st.expander(f"System #{s['system_id']} — {s['coupon_name']} | Best: {s['best_correct']}/13", expanded=True):
            st.metric("Best Row Correct", f"{s['best_correct']}/13")

            if s["notes"]:
                st.caption(s["notes"])

            if dist:
                dist_data = []
                for k in range(14):
                    count = dist.get(str(k), 0)
                    dist_data.append({"Correct": k, "Rows": count})

                fig = go.Figure(data=[
                    go.Bar(
                        x=[d["Correct"] for d in dist_data],
                        y=[d["Rows"] for d in dist_data],
                        marker_color=["#F44336" if d["Correct"] < 8 else "#FFC107" if d["Correct"] < 10 else "#4CAF50" if d["Correct"] < 13 else "#FFD700" for d in dist_data],
                        text=[d["Rows"] for d in dist_data],
                        textposition="outside"
                    )
                ])
                fig.update_layout(
                    title="Distribution of Correct Predictions per Row",
                    xaxis_title="Correct Matches",
                    yaxis_title="Number of Rows",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="white",
                    height=300,
                    margin=dict(l=20, r=20, t=40, b=20)
                )
                st.plotly_chart(fig, use_container_width=True)

    if len(scores) >= 2:
        st.markdown("### Performance Over Time")
        trend_data = []
        for s in reversed(scores):
            trend_data.append({
                "Coupon": s["coupon_name"],
                "Best Correct": s["best_correct"],
                "Total Rows": s["total_rows"]
            })

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[d["Coupon"] for d in trend_data],
            y=[d["Best Correct"] for d in trend_data],
            mode="lines+markers",
            name="Best Correct",
            line=dict(color="#4CAF50", width=2),
            marker=dict(size=8)
        ))
        fig.add_hline(y=10, line_dash="dash", line_color="#FFC107", annotation_text="10 correct")
        fig.add_hline(y=13, line_dash="dash", line_color="#FFD700", annotation_text="Jackpot")
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="white",
            yaxis_range=[0, 14],
            height=300,
            margin=dict(l=20, r=20, t=30, b=20)
        )
        st.plotly_chart(fig, use_container_width=True)


render_stryktipset_dashboard()
