# pgr_theme.py

import streamlit as st

# -------- PGR DESIGN TOKENS -------- #
PGR_COLORS = {
    "bg": "#06070A",          # Main background
    "bg_alt": "#101320",      # Cards / secondary
    "accent": "#00F59D",      # Neon green
    "accent_soft": "#28ffb0",
    "danger": "#FF4B6B",
    "warning": "#FFB547",
    "text": "#F2F5F8",
    "muted": "#9BA0B5",
    "border": "#1C2030",
}

PGR_FONTS = {
    "main": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    "mono": "'JetBrains Mono', Menlo, Monaco, Consolas, monospace",
}


def inject_pgr_css() -> None:
    """
    Kör denna högst upp i varje Streamlit-app:
        from pgr_theme import inject_pgr_css
        inject_pgr_css()
    """
    colors = PGR_COLORS
    fonts = PGR_FONTS

    css = f"""
    <style>
    /* ---- GLOBAL ---- */
    html, body, [class*="block-container"] {{
        background: radial-gradient(circle at top, #0b1120 0, {colors["bg"]} 55%);
        color: {colors["text"]};
        font-family: {fonts["main"]};
    }}

    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}

    /* ---- SIDEBAR ---- */
    section[data-testid="stSidebar"] > div {{
        background: linear-gradient(180deg, #050712 0%, #050508 100%);
        border-right: 1px solid {colors["border"]};
    }}

    /* ---- CARDS ---- */
    .pgr-card {{
        padding: 1.1rem 1.2rem;
        border-radius: 18px;
        background: radial-gradient(circle at top left, #151a2c 0, {colors["bg_alt"]} 50%);
        border: 1px solid {colors["border"]};
        box-shadow: 0 18px 40px rgba(0,0,0,0.7);
        position: relative;
        overflow: hidden;
    }}

    .pgr-card::before {{
        content: "";
        position: absolute;
        inset: -30%;
        background:
          radial-gradient(circle at 0% 0%, rgba(0,245,157,0.06) 0, transparent 55%),
          radial-gradient(circle at 100% 100%, rgba(0,245,157,0.05) 0, transparent 55%);
        opacity: 0.9;
        pointer-events: none;
    }}

    .pgr-card-title {{
        font-size: 0.85rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: {colors["muted"]};
        margin-bottom: 0.3rem;
    }}

    .pgr-card-value {{
        font-size: 1.9rem;
        font-weight: 700;
        color: {colors["accent"]};
    }}

    .pgr-card-kicker {{
        font-size: 0.8rem;
        color: {colors["muted"]};
    }}

    /* ---- TAGS / BADGES ---- */
    .pgr-tag {{
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        padding: 0.15rem 0.55rem;
        border-radius: 999px;
        background: rgba(15, 23, 42, 0.9);
        border: 1px solid {colors["border"]};
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.09em;
        color: {colors["muted"]};
    }}

    .pgr-tag--green {{
        border-color: rgba(0,245,157,0.5);
        color: {colors["accent_soft"]};
        background: rgba(34,197,94,0.06);
    }}

    .pgr-tag--red {{
        border-color: rgba(239,68,68,0.7);
        color: {colors["danger"]};
        background: rgba(239,68,68,0.06);
    }}

    /* ---- BUTTONS ---- */
    .pgr-button-primary > button {{
        border-radius: 999px;
        border: 1px solid rgba(0,245,157,0.75);
        background: radial-gradient(circle at top left, #22c55e 0, #00F59D 35%, #059669 90%);
        color: #020617;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        box-shadow: 0 12px 35px rgba(34,197,94,0.45);
    }}

    .pgr-button-primary > button:hover {{
        filter: brightness(1.05);
        box-shadow: 0 16px 45px rgba(34,197,94,0.65);
    }}

    .pgr-button-ghost > button {{
        border-radius: 999px;
        border: 1px solid {colors["border"]};
        background: rgba(15, 23, 42, 0.9);
        color: {colors["muted"]};
        font-weight: 500;
    }}

    .pgr-button-ghost > button:hover {{
        border-color: {colors["accent"]};
        color: {colors["accent"]};
    }}

    /* ---- SECTION TITLES ---- */
    .pgr-section-title {{
        font-size: 1.0rem;
        font-weight: 600;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: {colors["muted"]};
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 1.6rem 0 0.7rem 0;
    }}

    .pgr-section-title span.icon {{
        display: inline-flex;
        width: 22px;
        height: 22px;
        border-radius: 999px;
        align-items: center;
        justify-content: center;
        background: radial-gradient(circle at 25% 0, #22c55e 0, #00F59D 40%, transparent 70%);
        box-shadow: 0 0 18px rgba(34,197,94,0.75);
    }}

    /* ---- TABLES ---- */
    .pgr-table table {{
        border-collapse: collapse;
        width: 100%;
        font-size: 0.82rem;
    }}

    .pgr-table th {{
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-size: 0.72rem;
        color: {colors["muted"]};
        background: rgba(15,23,42,0.9);
        border-bottom: 1px solid {colors["border"]};
        padding: 0.4rem 0.6rem;
    }}

    .pgr-table td {{
        padding: 0.45rem 0.6rem;
        border-bottom: 1px solid rgba(15,23,42,0.6);
        color: {colors["text"]};
    }}

    .pgr-table tr:nth-child(even) td {{
        background: rgba(15,23,42,0.35);
    }}

    .pgr-roi-up   {{ color: {colors["accent"]}; }}
    .pgr-roi-down {{ color: {colors["danger"]}; }}
    </style>
    """

    st.markdown(css, unsafe_allow_html=True)