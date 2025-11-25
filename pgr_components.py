# pgr_components.py

from typing import Optional, Literal
import pandas as pd
import streamlit as st

from pgr_theme import PGR_COLORS


def section_title(label: str, icon: str = "📈") -> None:
    """Stor sektionstitel med liten glow-ikon."""
    st.markdown(
        f"""
        <div class="pgr-section-title">
            <span class="icon">{icon}</span>
            <span>{label}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(
    label: str,
    value: str,
    kicker: str = "",
    variant: Literal["default", "good", "bad"] = "default",
):
    """Litet fet KPI-kort."""
    color = {
        "default": PGR_COLORS["accent"],
        "good": PGR_COLORS["accent"],
        "bad": PGR_COLORS["danger"],
    }[variant]

    st.markdown(
        f"""
        <div class="pgr-card">
            <div class="pgr-card-title">{label}</div>
            <div class="pgr-card-value" style="color:{color}">{value}</div>
            <div class="pgr-card-kicker">{kicker}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def roi_delta_tag(roi: float) -> str:
    """Returnerar HTML-tag med ↑ / ↓ och ROI %."""
    cls = "pgr-tag pgr-tag--green" if roi >= 0 else "pgr-tag pgr-tag--red"
    arrow = "↑" if roi >= 0 else "↓"
    return f'<span class="{cls}">{arrow} {roi:+.1f}% ROI</span>'


def pgr_button(label: str, key: Optional[str] = None, primary: bool = True) -> bool:
    """PGR-stylad knapp – returnerar True när den klickas."""
    container_class = "pgr-button-primary" if primary else "pgr-button-ghost"
    with st.container():
        st.markdown(f'<div class="{container_class}">', unsafe_allow_html=True)
        clicked = st.button(label, key=key)
        st.markdown("</div>", unsafe_allow_html=True)
    return clicked


def roi_chart(
    df: pd.DataFrame,
    x_col: str = "bet_index",
    y_col: str = "roi",
    height: int = 260,
    title: str = "ROI over time",
):
    """
    Enkel ROI-line chart.
    df[x_col] = index eller datum
    df[y_col] = kumulativ ROI i %
    """
    df = df.copy()
    df = df[[x_col, y_col]].set_index(x_col)

    section_title(title, icon="📉" if df[y_col].iloc[-1] < 0 else "📈")
    st.line_chart(df, height=height)


def picks_table(df: pd.DataFrame, title: str = "Latest picks", max_rows: int = 25):
    """Tabell med senaste spelen."""
    section_title(title, icon="🎯")
    df = df.head(max_rows).copy()

    for col in df.columns:
        cl = col.lower()
        if "odds" in cl:
            df[col] = df[col].map(
                lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else x
            )
        if "ev" in cl or "roi" in cl:
            df[col] = df[col].map(
                lambda x: f"{x:+.1f}%" if isinstance(x, (int, float)) else x
            )

    st.markdown('<div class="pgr-table">', unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)
