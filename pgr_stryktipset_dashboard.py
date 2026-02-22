import streamlit as st
import pandas as pd
import sqlite3
import json
import requests
import os
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px

DB_PATH = "app.db"
API_BASE = "http://localhost:8000"
ADMIN_SECRET = os.environ.get("ADMIN_API_KEY", "CHANGE_ME")

def get_stryk_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def api_call(method, path, json_data=None):
    headers = {"X-Admin-Secret": ADMIN_SECRET, "Content-Type": "application/json"}
    try:
        if method == "GET":
            r = requests.get(f"{API_BASE}{path}", headers=headers, timeout=30)
        else:
            r = requests.post(f"{API_BASE}{path}", headers=headers, json=json_data, timeout=60)
        return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
    except Exception as e:
        return 0, str(e)

def render_stryktipset_dashboard():
    st.markdown("""
    <style>
        .stryk-header {
            text-align: center;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            padding: 1.5rem;
            border-radius: 12px;
            margin-bottom: 1rem;
            border: 1px solid #e94560;
        }
        .stryk-header h2 { color: #e94560; margin: 0; }
        .stryk-header p { color: #a0a0a0; margin: 0.3rem 0 0 0; font-size: 0.85rem; }
        .stryk-card {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 1.2rem;
            border-radius: 10px;
            border: 1px solid #333;
            margin-bottom: 0.8rem;
        }
        .stryk-metric {
            background: linear-gradient(135deg, #0f3460 0%, #16213e 100%);
            padding: 1rem;
            border-radius: 8px;
            text-align: center;
            border: 1px solid #e94560;
        }
        .stryk-metric .value { font-size: 1.8rem; font-weight: 700; color: #e94560; }
        .stryk-metric .label { font-size: 0.75rem; color: #a0a0a0; }
        .match-row { padding: 0.4rem 0; border-bottom: 1px solid #222; }
        .spike-tag { background: #e94560; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
        .half-tag { background: #FFC107; color: black; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
        .full-tag { background: #4CAF50; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
        .disclaimer { text-align: center; color: #666; font-size: 0.7rem; margin-top: 1rem; font-style: italic; }
    </style>
    """, unsafe_allow_html=True)

    if "stryk_admin" not in st.session_state:
        st.session_state.stryk_admin = False

    if not st.session_state.stryk_admin:
        st.markdown('<div class="stryk-header"><h2>🎰 Stryktipset (Private)</h2><p>Admin access required</p></div>', unsafe_allow_html=True)
        pwd = st.text_input("Admin Password", type="password", key="stryk_pwd")
        if st.button("Login", key="stryk_login"):
            if pwd == ADMIN_SECRET:
                st.session_state.stryk_admin = True
                st.rerun()
            else:
                st.error("Wrong password")
        return

    st.markdown('<div class="stryk-header"><h2>🎰 Stryktipset (Private)</h2><p>AI-Powered Reduced System Generator | Jackpot Strategy</p></div>', unsafe_allow_html=True)

    try:
        conn = get_stryk_db()
    except Exception as e:
        st.error(f"Database error: {e}")
        return

    render_coupon_selector(conn)

    st.markdown('<p class="disclaimer">Private tool – tracks correct picks (0–13), not ROI</p>', unsafe_allow_html=True)
    conn.close()


def render_coupon_selector(conn):
    coupons = conn.execute("SELECT * FROM stryk_coupons ORDER BY created_at DESC").fetchall()

    col_sel, col_new = st.columns([3, 1])
    with col_sel:
        if coupons:
            options = {f"#{c['id']} — {c['name']} ({c['status']})": c["id"] for c in coupons}
            selected_key = st.selectbox("Select Coupon", list(options.keys()), key="stryk_coupon_sel")
            coupon_id = options[selected_key]
        else:
            st.info("No coupons yet. Create one below.")
            coupon_id = None

    with col_new:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ New Coupon", key="stryk_new_coupon", use_container_width=True):
            st.session_state.stryk_show_create = True

    if st.session_state.get("stryk_show_create", False):
        render_create_coupon(conn)

    if coupon_id:
        render_coupon_detail(conn, coupon_id)


def render_create_coupon(conn):
    st.markdown("---")
    st.markdown("### Create New Coupon")

    c1, c2 = st.columns(2)
    name = c1.text_input("Coupon Name", value="Stryktipset", key="new_coupon_name")
    week_tag = c2.text_input("Week Tag", value="", key="new_coupon_week", placeholder="e.g. V7")

    st.markdown("**Enter 13 matches:**")
    matches = []
    for i in range(1, 14):
        cols = st.columns([0.5, 2, 2, 2])
        cols[0].markdown(f"**{i}**")
        home = cols[1].text_input("Home", key=f"nc_home_{i}", label_visibility="collapsed", placeholder=f"Home {i}")
        away = cols[2].text_input("Away", key=f"nc_away_{i}", label_visibility="collapsed", placeholder=f"Away {i}")
        league = cols[3].text_input("League", key=f"nc_league_{i}", label_visibility="collapsed", placeholder="League")
        matches.append({"match_no": i, "home_team": home, "away_team": away, "league": league or None})

    c_save, c_cancel = st.columns(2)
    if c_save.button("Create Coupon", key="stryk_create_save", type="primary", use_container_width=True):
        missing = [m for m in matches if not m["home_team"].strip() or not m["away_team"].strip()]
        if missing:
            st.error(f"Please fill in all 13 matches (missing: {[m['match_no'] for m in missing]})")
        elif not name.strip():
            st.error("Please enter a coupon name")
        else:
            payload = {"name": name.strip(), "week_tag": week_tag.strip() or None, "matches": matches}
            status, resp = api_call("POST", "/admin/stryk/coupons", payload)
            if status == 200:
                st.success(f"Coupon created! ID: {resp.get('coupon_id')}")
                st.session_state.stryk_show_create = False
                st.rerun()
            else:
                st.error(f"Error: {resp}")

    if c_cancel.button("Cancel", key="stryk_create_cancel", use_container_width=True):
        st.session_state.stryk_show_create = False
        st.rerun()


def render_coupon_detail(conn, coupon_id):
    coupon = conn.execute("SELECT * FROM stryk_coupons WHERE id = ?", (coupon_id,)).fetchone()
    if not coupon:
        st.error("Coupon not found")
        return

    status_icon = {"draft": "🟡", "published": "🟢", "settled": "🔵"}.get(coupon["status"], "⚪")

    st.markdown("---")

    mc1, mc2, mc3 = st.columns(3)
    mc1.markdown(f"""<div class="stryk-metric"><div class="value">{status_icon} {coupon['status'].upper()}</div><div class="label">Status</div></div>""", unsafe_allow_html=True)
    mc2.markdown(f"""<div class="stryk-metric"><div class="value">{coupon['week_tag'] or '—'}</div><div class="label">Week Tag</div></div>""", unsafe_allow_html=True)
    mc3.markdown(f"""<div class="stryk-metric"><div class="value">#{coupon['id']}</div><div class="label">Coupon ID</div></div>""", unsafe_allow_html=True)

    tabs = st.tabs(["📋 Matches", "⚡ Actions", "📊 Public %", "⚙️ Generate System", "📐 System Rows", "🏆 Scoring"])

    with tabs[0]:
        render_matches_overview(conn, coupon_id)

    with tabs[1]:
        render_actions(conn, coupon_id, coupon["status"])

    with tabs[2]:
        render_public_input(conn, coupon_id)

    with tabs[3]:
        render_generate_system(conn, coupon_id)

    with tabs[4]:
        render_system_rows(conn, coupon_id)

    with tabs[5]:
        render_scoring(conn, coupon_id, coupon["status"])


def render_matches_overview(conn, coupon_id):
    matches = conn.execute("SELECT * FROM stryk_matches WHERE coupon_id = ? ORDER BY match_no", (coupon_id,)).fetchall()
    probs = conn.execute("""
        SELECT sp.*, sm.match_no
        FROM stryk_probs sp
        JOIN stryk_matches sm ON sp.match_id = sm.id
        WHERE sp.coupon_id = ?
        ORDER BY sm.match_no
    """, (coupon_id,)).fetchall()
    probs_by_no = {p["match_no"]: p for p in probs}

    if not matches:
        st.warning("No matches in this coupon.")
        return

    rows = []
    for m in matches:
        p = probs_by_no.get(m["match_no"])
        odds_str = ""
        if m["odds_1"]:
            odds_str = f"{m['odds_1']:.2f} / {m['odds_x']:.2f} / {m['odds_2']:.2f}"

        pub_str = ""
        if m["public_pct_1"] is not None:
            pub_str = f"{m['public_pct_1']:.0f} / {m['public_pct_x']:.0f} / {m['public_pct_2']:.0f}"

        prob_str = ""
        if p:
            prob_str = f"{p['p1']:.0%} / {p['px']:.0%} / {p['p2']:.0%}"

        pick = ""
        if p:
            best = max(p["p1"], p["px"], p["p2"])
            if best == p["p1"]: pick = "1"
            elif best == p["px"]: pick = "X"
            else: pick = "2"

        result = m["result"] or ""
        correct = ""
        if result and pick:
            correct = "✅" if pick == result else "❌"

        rows.append({
            "#": m["match_no"],
            "Home": m["home_team"],
            "Away": m["away_team"],
            "League": m["league"] or "",
            "Odds (1/X/2)": odds_str or "—",
            "Public %": pub_str or "—",
            "Prob (1/X/2)": prob_str or "—",
            "Pick": pick or "—",
            "Result": result or "—",
            "": correct,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    if probs:
        prob_data = []
        for p in probs:
            prob_data.append({"Match": f"#{p['match_no']}", "Outcome": "1", "Probability": p["p1"]})
            prob_data.append({"Match": f"#{p['match_no']}", "Outcome": "X", "Probability": p["px"]})
            prob_data.append({"Match": f"#{p['match_no']}", "Outcome": "2", "Probability": p["p2"]})

        fig = px.bar(
            pd.DataFrame(prob_data), x="Match", y="Probability", color="Outcome",
            barmode="group",
            color_discrete_map={"1": "#4CAF50", "X": "#FFC107", "2": "#F44336"},
            height=300
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="white", yaxis_tickformat=".0%",
            margin=dict(l=20, r=20, t=30, b=20)
        )
        st.plotly_chart(fig, use_container_width=True, key="stryktipset_overview_chart")


def render_actions(conn, coupon_id, status):
    st.markdown("### Quick Actions")

    has_probs = conn.execute("SELECT COUNT(*) as c FROM stryk_probs WHERE coupon_id = ?", (coupon_id,)).fetchone()["c"] > 0
    has_system = conn.execute("SELECT COUNT(*) as c FROM stryk_systems WHERE coupon_id = ?", (coupon_id,)).fetchone()["c"] > 0

    c1, c2 = st.columns(2)

    with c1:
        pred_status = "✅ Done" if has_probs else "⏳ Pending"
        st.markdown(f"**Predict** — {pred_status}")
        if st.button("🔮 Run Predictions", key="act_predict", use_container_width=True, type="primary"):
            with st.spinner("Running AI predictions..."):
                code, resp = api_call("POST", f"/admin/stryk/coupons/{coupon_id}/predict")
            if code == 200:
                preds = resp.get("predictions", [])
                st.success(f"Predictions generated for {len(preds)} matches!")
                st.rerun()
            else:
                st.error(f"Error: {resp}")

    with c2:
        sys_status = "✅ Done" if has_system else "⏳ Pending"
        st.markdown(f"**System** — {sys_status}")
        st.caption("Use the 'Generate System' tab for full config")

    st.markdown("---")

    c3, c4 = st.columns(2)

    with c3:
        st.markdown(f"**Status:** {status}")
        if status != "settled":
            if st.button("🔵 Settle Results", key="act_settle", use_container_width=True):
                st.session_state.stryk_show_settle = True
        else:
            st.success("Coupon is settled")

    with c4:
        if status == "settled" and has_system:
            systems = conn.execute("SELECT id FROM stryk_systems WHERE coupon_id = ?", (coupon_id,)).fetchall()
            if st.button("📊 Score All Systems", key="act_score_all", use_container_width=True, type="primary"):
                for sys in systems:
                    code, resp = api_call("POST", f"/admin/stryk/coupons/{coupon_id}/score_system/{sys['id']}")
                if code == 200:
                    st.success("All systems scored!")
                    st.rerun()
                else:
                    st.error(f"Error: {resp}")

    if st.session_state.get("stryk_show_settle", False):
        render_settle_form(conn, coupon_id)


def render_settle_form(conn, coupon_id):
    st.markdown("---")
    st.markdown("### Enter Results")
    matches = conn.execute("SELECT * FROM stryk_matches WHERE coupon_id = ? ORDER BY match_no", (coupon_id,)).fetchall()

    results = {}
    for m in matches:
        cols = st.columns([0.5, 2, 2, 2])
        cols[0].markdown(f"**{m['match_no']}**")
        cols[1].caption(f"{m['home_team']} vs {m['away_team']}")
        res = cols[2].selectbox(
            "Result", ["1", "X", "2"],
            key=f"settle_{m['match_no']}",
            label_visibility="collapsed"
        )
        results[str(m["match_no"])] = res

    if st.button("Submit Results", key="settle_submit", type="primary", use_container_width=True):
        code, resp = api_call("POST", f"/admin/stryk/coupons/{coupon_id}/settle", {"results": results})
        if code == 200:
            st.success("Coupon settled!")
            st.session_state.stryk_show_settle = False
            st.rerun()
        else:
            st.error(f"Error: {resp}")


def render_public_input(conn, coupon_id):
    st.markdown("### Update Public Betting %")
    st.caption("Enter the public betting distribution for each match (must sum to ~100)")

    matches = conn.execute("SELECT * FROM stryk_matches WHERE coupon_id = ? ORDER BY match_no", (coupon_id,)).fetchall()
    if not matches:
        st.warning("No matches found.")
        return

    public_data = {}
    all_valid = True

    for m in matches:
        cols = st.columns([0.5, 2, 1.2, 1.2, 1.2, 1])
        cols[0].markdown(f"**{m['match_no']}**")
        cols[1].caption(f"{m['home_team']} vs {m['away_team']}")

        default_1 = m["public_pct_1"] if m["public_pct_1"] is not None else 33.0
        default_x = m["public_pct_x"] if m["public_pct_x"] is not None else 33.0
        default_2 = m["public_pct_2"] if m["public_pct_2"] is not None else 34.0

        p1 = cols[2].number_input("1", value=default_1, min_value=0.0, max_value=100.0, step=1.0,
                                   key=f"pub_1_{m['match_no']}", label_visibility="collapsed")
        px_val = cols[3].number_input("X", value=default_x, min_value=0.0, max_value=100.0, step=1.0,
                                      key=f"pub_x_{m['match_no']}", label_visibility="collapsed")
        p2 = cols[4].number_input("2", value=default_2, min_value=0.0, max_value=100.0, step=1.0,
                                   key=f"pub_2_{m['match_no']}", label_visibility="collapsed")

        total = p1 + px_val + p2
        if 98.0 <= total <= 102.0:
            cols[5].markdown(f"<span style='color:#4CAF50'>✓ {total:.0f}%</span>", unsafe_allow_html=True)
        else:
            cols[5].markdown(f"<span style='color:#F44336'>✗ {total:.0f}%</span>", unsafe_allow_html=True)
            all_valid = False

        public_data[str(m["match_no"])] = {"1": p1, "X": px_val, "2": p2}

    st.markdown("---")
    if st.button("💾 Save Public %", key="pub_save", type="primary", use_container_width=True, disabled=not all_valid):
        code, resp = api_call("POST", f"/admin/stryk/coupons/{coupon_id}/public", {"public": public_data})
        if code == 200:
            st.success(f"Public % updated for {resp.get('updated', 13)} matches!")
            st.rerun()
        else:
            st.error(f"Error: {resp}")

    if not all_valid:
        st.warning("Some matches don't sum to ~100%. Fix them before saving.")


def render_generate_system(conn, coupon_id):
    st.markdown("### Generate Reduced System")

    has_probs = conn.execute("SELECT COUNT(*) as c FROM stryk_probs WHERE coupon_id = ?", (coupon_id,)).fetchone()["c"]
    if has_probs == 0:
        st.warning("Run predictions first before generating a system.")
        return

    c1, c2 = st.columns(2)
    preset = c1.selectbox("Preset", ["jackpot_aggressive"], key="gen_preset")
    target_rows = c2.selectbox("Target Rows", [64, 128, 256, 512, 1024], index=2, key="gen_target")

    with st.expander("⚙️ Advanced Settings"):
        ac1, ac2, ac3 = st.columns(3)
        min_spikes = ac1.number_input("Min Spikes", value=4, min_value=1, max_value=10, key="gen_spikes")
        max_full = ac2.number_input("Max Full Guards", value=2, min_value=0, max_value=6, key="gen_full")
        max_half = ac3.number_input("Max Half Guards", value=7, min_value=1, max_value=11, key="gen_half")

        ac4, ac5, ac6 = st.columns(3)
        draws_policy = ac4.selectbox("Draws Policy", ["high", "normal", "low"], key="gen_draws")
        min_prob = ac5.number_input("Min Outcome Prob", value=0.10, min_value=0.01, max_value=0.30, step=0.01, key="gen_minprob")
        alpha = ac6.number_input("Public Bias (alpha)", value=0.25, min_value=0.0, max_value=0.7, step=0.05, key="gen_alpha")

    if st.button("🚀 Generate System", key="gen_submit", type="primary", use_container_width=True):
        payload = {
            "preset": preset,
            "target_rows": target_rows,
            "min_spikes": min_spikes,
            "max_full_guards": max_full,
            "max_half_guards": max_half,
            "include_draws_policy": draws_policy,
            "min_outcome_prob": min_prob,
            "alpha_public_bias": alpha,
        }
        with st.spinner(f"Generating {target_rows}-row system..."):
            code, resp = api_call("POST", f"/admin/stryk/coupons/{coupon_id}/generate_system", payload)

        if code == 200:
            st.success(f"System #{resp.get('system_id')} generated!")

            rc1, rc2, rc3, rc4 = st.columns(4)
            rc1.metric("Rows", resp.get("final_rows"))
            rc2.metric("Spikes", resp.get("spikes"))
            rc3.metric("Half", resp.get("half_guards"))
            rc4.metric("Full", resp.get("full_guards"))

            st.caption(resp.get("summary", ""))
            st.info(f"Theoretical rows: {resp.get('theoretical_rows')} → Reduced to {resp.get('final_rows')}")
        else:
            st.error(f"Error: {resp}")

    existing = conn.execute("""
        SELECT * FROM stryk_systems WHERE coupon_id = ? ORDER BY created_at DESC
    """, (coupon_id,)).fetchall()

    if existing:
        st.markdown("---")
        st.markdown("### Existing Systems")
        for sys in existing:
            rules = json.loads(sys["rules_json"]) if isinstance(sys["rules_json"], str) else (sys["rules_json"] or {})
            allowed = rules.get("allowed", {})

            with st.expander(f"System #{sys['id']} — {sys['final_rows']} rows | {sys['spik_count']}S {sys['half_count']}H {sys['full_count']}F"):
                sc1, sc2, sc3, sc4, sc5 = st.columns(5)
                sc1.metric("Rows", sys["final_rows"])
                sc2.metric("Spikes", sys["spik_count"])
                sc3.metric("Half", sys["half_count"])
                sc4.metric("Full", sys["full_count"])
                sc5.metric("Theoretical", rules.get("theoretical_rows", "—"))

                if allowed:
                    class_data = []
                    for no_str in sorted(allowed.keys(), key=lambda x: int(x)):
                        outcomes = allowed[no_str]
                        match_info = conn.execute("SELECT home_team, away_team FROM stryk_matches WHERE coupon_id = ? AND match_no = ?", (coupon_id, int(no_str))).fetchone()
                        teams = f"{match_info['home_team']} vs {match_info['away_team']}" if match_info else f"Match {no_str}"

                        if len(outcomes) == 1:
                            tag = f"🔒 Spike ({outcomes[0]})"
                        elif len(outcomes) == 2:
                            tag = f"↔️ Half ({'/'.join(outcomes)})"
                        else:
                            tag = "🛡️ Full (1/X/2)"

                        class_data.append({"#": no_str, "Match": teams, "Type": tag, "Allowed": ", ".join(outcomes)})

                    st.dataframe(pd.DataFrame(class_data), use_container_width=True, hide_index=True)


def render_system_rows(conn, coupon_id):
    st.markdown("### System Rows Viewer")

    systems = conn.execute("SELECT * FROM stryk_systems WHERE coupon_id = ? ORDER BY created_at DESC", (coupon_id,)).fetchall()
    if not systems:
        st.info("No systems generated for this coupon.")
        return

    sys_options = {f"System #{s['id']} ({s['final_rows']} rows)": s["id"] for s in systems}
    sel_sys = st.selectbox("Select System", list(sys_options.keys()), key="rows_sys_sel")
    system_id = sys_options[sel_sys]

    total_count = conn.execute("SELECT COUNT(*) as c FROM stryk_rows WHERE system_id = ?", (system_id,)).fetchone()["c"]

    fc1, fc2, fc3 = st.columns(3)
    search = fc1.text_input("Search rows (e.g. 'X' or '1X2')", key="rows_search", placeholder="Filter...")
    sort_by = fc2.selectbox("Sort by", ["Row #", "Model Prob ↓", "Contrarian ↓", "Public Prob ↑"], key="rows_sort")
    max_show = fc3.number_input("Show rows", value=100, min_value=10, max_value=2000, step=50, key="rows_max")

    order_clause = "row_no ASC"
    if sort_by == "Model Prob ↓":
        order_clause = "row_prob DESC"
    elif sort_by == "Contrarian ↓":
        order_clause = "contrarian_score DESC"
    elif sort_by == "Public Prob ↑":
        order_clause = "row_public_prob ASC"

    all_rows = conn.execute(f"SELECT * FROM stryk_rows WHERE system_id = ? ORDER BY {order_clause}", (system_id,)).fetchall()

    if search.strip():
        filtered = [r for r in all_rows if search.upper() in r["row_string"].upper()]
    else:
        filtered = list(all_rows)

    st.caption(f"Showing {min(len(filtered), max_show)} of {len(filtered)} rows (total: {total_count})")

    if not filtered:
        st.info("No rows match your filter.")
        return

    draw_counts = {}
    row_data = []
    for r in filtered[:max_show]:
        row_str = r["row_string"]
        draws = row_str.count("X")
        draw_counts[draws] = draw_counts.get(draws, 0) + 1

        formatted = " ".join(row_str)
        row_data.append({
            "#": r["row_no"],
            "Row": formatted,
            "Draws": draws,
            "Prob": f"{r['row_prob']:.2e}" if r["row_prob"] else "—",
            "Pub Prob": f"{r['row_public_prob']:.2e}" if r["row_public_prob"] else "—",
            "Contrarian": f"{r['contrarian_score']:.1f}" if r["contrarian_score"] else "—"
        })

    st.dataframe(pd.DataFrame(row_data), use_container_width=True, hide_index=True, height=400)

    if draw_counts:
        st.markdown("**Draw Distribution in System:**")
        dc1, dc2 = st.columns([2, 3])
        with dc1:
            draw_df = pd.DataFrame([{"Draws": k, "Rows": v} for k, v in sorted(draw_counts.items())])
            st.dataframe(draw_df, use_container_width=True, hide_index=True)

        with dc2:
            fig = go.Figure(data=[go.Bar(
                x=list(sorted(draw_counts.keys())),
                y=[draw_counts[k] for k in sorted(draw_counts.keys())],
                marker_color="#FFC107",
                text=[draw_counts[k] for k in sorted(draw_counts.keys())],
                textposition="outside"
            )])
            fig.update_layout(
                xaxis_title="Number of X's",
                yaxis_title="Rows",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="white", height=250,
                margin=dict(l=20, r=20, t=20, b=20)
            )
            st.plotly_chart(fig, use_container_width=True, key="stryktipset_match_chart")


def render_scoring(conn, coupon_id, status):
    st.markdown("### Scoring & Results")

    if status != "settled":
        st.info("Settle the coupon first to score systems.")

        systems = conn.execute("SELECT * FROM stryk_systems WHERE coupon_id = ?", (coupon_id,)).fetchall()
        if systems:
            st.caption(f"{len(systems)} system(s) ready — settle coupon to score.")
        return

    scores = conn.execute("""
        SELECT * FROM stryk_system_scores WHERE coupon_id = ? ORDER BY computed_at DESC
    """, (coupon_id,)).fetchall()

    systems = conn.execute("SELECT * FROM stryk_systems WHERE coupon_id = ?", (coupon_id,)).fetchall()
    unscored = [s for s in systems if not any(sc["system_id"] == s["id"] for sc in scores)]

    if unscored:
        st.warning(f"{len(unscored)} system(s) not yet scored.")
        if st.button("📊 Score Unscored Systems", key="score_unscored", type="primary"):
            for sys in unscored:
                code, resp = api_call("POST", f"/admin/stryk/coupons/{coupon_id}/score_system/{sys['id']}")
            st.success("Done!")
            st.rerun()

    if not scores:
        return

    best_overall = max(s["best_correct"] for s in scores)
    avg_best = sum(s["best_correct"] for s in scores) / len(scores)

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.markdown(f"""<div class="stryk-metric"><div class="value">{best_overall}/13</div><div class="label">Best Score</div></div>""", unsafe_allow_html=True)
    mc2.markdown(f"""<div class="stryk-metric"><div class="value">{avg_best:.1f}</div><div class="label">Avg Best</div></div>""", unsafe_allow_html=True)
    ge10 = sum(1 for s in scores if s["best_correct"] >= 10)
    mc3.markdown(f"""<div class="stryk-metric"><div class="value">{ge10}/{len(scores)}</div><div class="label">10+ Correct</div></div>""", unsafe_allow_html=True)
    ge12 = sum(1 for s in scores if s["best_correct"] >= 12)
    mc4.markdown(f"""<div class="stryk-metric"><div class="value">{ge12}/{len(scores)}</div><div class="label">12+ Correct</div></div>""", unsafe_allow_html=True)

    for s in scores:
        dist = json.loads(s["dist_json"]) if isinstance(s["dist_json"], str) else (s["dist_json"] or {})

        with st.expander(f"System #{s['system_id']} — Best: {s['best_correct']}/13 | {s['total_rows']} rows", expanded=True):
            if s["notes"]:
                st.caption(s["notes"])

            if dist:
                dist_data = []
                for k in range(14):
                    count = dist.get(str(k), 0)
                    dist_data.append({"Correct": k, "Rows": count})

                fig = go.Figure(data=[go.Bar(
                    x=[d["Correct"] for d in dist_data],
                    y=[d["Rows"] for d in dist_data],
                    marker_color=[
                        "#F44336" if d["Correct"] < 8 else
                        "#FFC107" if d["Correct"] < 10 else
                        "#4CAF50" if d["Correct"] < 13 else
                        "#FFD700"
                        for d in dist_data
                    ],
                    text=[d["Rows"] if d["Rows"] > 0 else "" for d in dist_data],
                    textposition="outside"
                )])
                fig.update_layout(
                    xaxis_title="Correct Matches", yaxis_title="Number of Rows",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font_color="white", height=300,
                    margin=dict(l=20, r=20, t=20, b=20)
                )
                st.plotly_chart(fig, use_container_width=True, key=f"stryktipset_scoring_chart_{s['system_id']}")

    st.markdown("---")
    st.markdown("### All-Time Summary")
    code, resp = api_call("GET", "/admin/stryk/scores/summary?last_n=50")
    if code == 200:
        agg = resp.get("aggregate", {})
        items = resp.get("items", [])

        ac1, ac2, ac3, ac4 = st.columns(4)
        ac1.metric("10+ Correct", agg.get("ge10", 0))
        ac2.metric("11+ Correct", agg.get("ge11", 0))
        ac3.metric("12+ Correct", agg.get("ge12", 0))
        ac4.metric("13/13 Jackpot", agg.get("eq13", 0))

        if len(items) >= 2:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=list(range(len(items))),
                y=[i["best_correct"] for i in reversed(items)],
                mode="lines+markers",
                name="Best Correct",
                line=dict(color="#e94560", width=2),
                marker=dict(size=8)
            ))
            fig.add_hline(y=10, line_dash="dash", line_color="#FFC107", annotation_text="10")
            fig.add_hline(y=13, line_dash="dash", line_color="#FFD700", annotation_text="Jackpot")
            fig.update_layout(
                xaxis_title="System #", yaxis_title="Best Correct",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="white", yaxis_range=[0, 14], height=300,
                margin=dict(l=20, r=20, t=30, b=20)
            )
            st.plotly_chart(fig, use_container_width=True, key="stryktipset_history_chart")


render_stryktipset_dashboard()
