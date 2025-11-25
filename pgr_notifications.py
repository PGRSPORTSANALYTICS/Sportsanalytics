# pgr_notifications.py
"""
PGR Real-Time Notifications System
Toast alerts, notification center, and live alert banners
"""

from typing import Optional, Literal, List, Dict
from datetime import datetime
import streamlit as st

from pgr_theme import PGR_COLORS


def inject_notification_css():
    """Inject CSS for notification components"""
    st.markdown(
        f"""
        <style>
        /* Notification Center */
        .pgr-notification-center {{
            position: relative;
        }}
        
        .pgr-notification-badge {{
            position: absolute;
            top: -5px;
            right: -5px;
            background: {PGR_COLORS["danger"]};
            color: white;
            font-size: 0.65rem;
            font-weight: 700;
            padding: 2px 6px;
            border-radius: 10px;
            min-width: 18px;
            text-align: center;
        }}
        
        .pgr-notification-bell {{
            font-size: 1.4rem;
            cursor: pointer;
            padding: 0.5rem;
            border-radius: 8px;
            transition: background 0.2s;
        }}
        
        .pgr-notification-bell:hover {{
            background: {PGR_COLORS["bg_alt"]};
        }}
        
        /* Alert Banner */
        .pgr-alert-banner {{
            padding: 0.75rem 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            animation: slideIn 0.3s ease;
        }}
        
        @keyframes slideIn {{
            from {{ opacity: 0; transform: translateY(-10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .pgr-alert-banner.info {{
            background: rgba(0, 245, 157, 0.1);
            border: 1px solid {PGR_COLORS["accent"]};
            color: {PGR_COLORS["accent"]};
        }}
        
        .pgr-alert-banner.warning {{
            background: rgba(255, 181, 71, 0.1);
            border: 1px solid {PGR_COLORS["warning"]};
            color: {PGR_COLORS["warning"]};
        }}
        
        .pgr-alert-banner.danger {{
            background: rgba(255, 75, 107, 0.1);
            border: 1px solid {PGR_COLORS["danger"]};
            color: {PGR_COLORS["danger"]};
        }}
        
        .pgr-alert-banner.live {{
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid #EF4444;
            color: #EF4444;
        }}
        
        .pgr-alert-icon {{
            font-size: 1.2rem;
        }}
        
        .pgr-alert-content {{
            flex: 1;
        }}
        
        .pgr-alert-title {{
            font-weight: 600;
            font-size: 0.9rem;
        }}
        
        .pgr-alert-message {{
            font-size: 0.8rem;
            opacity: 0.9;
        }}
        
        .pgr-alert-time {{
            font-size: 0.7rem;
            opacity: 0.7;
        }}
        
        /* Notification Item */
        .pgr-notification-item {{
            padding: 0.75rem;
            border-radius: 8px;
            background: {PGR_COLORS["bg_alt"]};
            border: 1px solid {PGR_COLORS["border"]};
            margin-bottom: 0.5rem;
            cursor: pointer;
            transition: all 0.2s;
        }}
        
        .pgr-notification-item:hover {{
            border-color: {PGR_COLORS["accent"]};
            transform: translateX(4px);
        }}
        
        .pgr-notification-item.unread {{
            border-left: 3px solid {PGR_COLORS["accent"]};
        }}
        
        .pgr-notification-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.25rem;
        }}
        
        .pgr-notification-type {{
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: {PGR_COLORS["accent"]};
            font-weight: 600;
        }}
        
        .pgr-notification-time {{
            font-size: 0.7rem;
            color: {PGR_COLORS["muted"]};
        }}
        
        .pgr-notification-text {{
            font-size: 0.85rem;
            color: {PGR_COLORS["text"]};
        }}
        
        /* Live Indicator */
        .pgr-live-dot {{
            width: 8px;
            height: 8px;
            background: #EF4444;
            border-radius: 50%;
            display: inline-block;
            margin-right: 6px;
            animation: pulse 1.5s infinite;
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.5; transform: scale(1.2); }}
        }}
        
        /* Toast Container */
        .pgr-toast-container {{
            position: fixed;
            top: 80px;
            right: 20px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }}
        
        .pgr-toast {{
            padding: 0.75rem 1rem;
            border-radius: 8px;
            min-width: 280px;
            max-width: 380px;
            animation: toastIn 0.3s ease;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }}
        
        @keyframes toastIn {{
            from {{ opacity: 0; transform: translateX(100%); }}
            to {{ opacity: 1; transform: translateX(0); }}
        }}
        
        .pgr-toast.success {{
            background: {PGR_COLORS["bg_alt"]};
            border: 1px solid {PGR_COLORS["accent"]};
        }}
        
        .pgr-toast.error {{
            background: {PGR_COLORS["bg_alt"]};
            border: 1px solid {PGR_COLORS["danger"]};
        }}
        
        .pgr-toast.warning {{
            background: {PGR_COLORS["bg_alt"]};
            border: 1px solid {PGR_COLORS["warning"]};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def alert_banner(
    title: str,
    message: str = "",
    variant: Literal["info", "warning", "danger", "live"] = "info",
    icon: Optional[str] = None,
    show_time: bool = True,
):
    """Display an alert banner at the top of the page"""
    icons = {
        "info": "💡",
        "warning": "⚠️",
        "danger": "🚨",
        "live": "🔴",
    }
    
    display_icon = icon or icons.get(variant, "💡")
    time_str = datetime.now().strftime("%H:%M") if show_time else ""
    
    st.markdown(
        f"""
        <div class="pgr-alert-banner {variant}">
            <span class="pgr-alert-icon">{display_icon}</span>
            <div class="pgr-alert-content">
                <div class="pgr-alert-title">{title}</div>
                {"<div class='pgr-alert-message'>" + message + "</div>" if message else ""}
            </div>
            {"<span class='pgr-alert-time'>" + time_str + "</span>" if show_time else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )


def live_match_alert(
    home_team: str,
    away_team: str,
    score: str,
    minute: int,
    event: str = "",
):
    """Display a live match alert with pulsing indicator"""
    st.markdown(
        f"""
        <div class="pgr-alert-banner live">
            <span class="pgr-live-dot"></span>
            <div class="pgr-alert-content">
                <div class="pgr-alert-title">{home_team} {score} {away_team}</div>
                <div class="pgr-alert-message">{minute}' {event}</div>
            </div>
            <span class="pgr-alert-time">LIVE</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def notification_center(notifications: List[Dict], max_display: int = 5):
    """
    Display a notification center with recent alerts
    
    notifications format:
    [
        {
            "type": "prediction",  # prediction, result, alert
            "text": "New exact score: Arsenal 2-1 Chelsea",
            "time": "10:30",
            "unread": True
        }
    ]
    """
    unread_count = sum(1 for n in notifications if n.get("unread", False))
    
    with st.expander(f"🔔 Notifications ({unread_count} new)", expanded=False):
        if not notifications:
            st.caption("No notifications yet")
            return
            
        for notif in notifications[:max_display]:
            unread_class = "unread" if notif.get("unread", False) else ""
            notif_type = notif.get("type", "alert").upper()
            
            st.markdown(
                f"""
                <div class="pgr-notification-item {unread_class}">
                    <div class="pgr-notification-header">
                        <span class="pgr-notification-type">{notif_type}</span>
                        <span class="pgr-notification-time">{notif.get("time", "")}</span>
                    </div>
                    <div class="pgr-notification-text">{notif.get("text", "")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        
        if len(notifications) > max_display:
            st.caption(f"+{len(notifications) - max_display} more notifications")


def prediction_toast(
    match: str,
    prediction: str,
    odds: float,
    ev: float,
):
    """Show a toast notification for a new prediction"""
    st.toast(
        f"🎯 **New Pick**: {match}\n{prediction} @ {odds:.2f} ({ev:+.1f}% EV)",
        icon="🎯",
    )


def result_toast(
    match: str,
    result: str,
    won: bool,
    profit: float,
):
    """Show a toast notification for a settled result"""
    if won:
        st.toast(
            f"✅ **WIN**: {match}\n{result} | +{profit:.0f} SEK",
            icon="✅",
        )
    else:
        st.toast(
            f"❌ **Loss**: {match}\n{result} | {profit:.0f} SEK",
            icon="❌",
        )


def stats_update_toast(
    metric: str,
    old_value: float,
    new_value: float,
):
    """Show a toast for stats updates"""
    change = new_value - old_value
    direction = "📈" if change > 0 else "📉"
    st.toast(
        f"{direction} **{metric}** updated: {old_value:.1f}% → {new_value:.1f}%",
        icon=direction,
    )


def quick_stats_banner(
    pending_bets: int = 0,
    live_matches: int = 0,
    new_picks_today: int = 0,
):
    """Display a quick stats banner with key numbers"""
    cols = st.columns(3)
    
    with cols[0]:
        if pending_bets > 0:
            st.markdown(
                f"""
                <div style="text-align: center; padding: 0.5rem; background: {PGR_COLORS["bg_alt"]}; border-radius: 8px;">
                    <div style="font-size: 1.5rem; font-weight: 700; color: {PGR_COLORS["accent"]};">{pending_bets}</div>
                    <div style="font-size: 0.75rem; color: {PGR_COLORS["muted"]};">Pending Bets</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    
    with cols[1]:
        if live_matches > 0:
            st.markdown(
                f"""
                <div style="text-align: center; padding: 0.5rem; background: {PGR_COLORS["bg_alt"]}; border-radius: 8px;">
                    <div style="font-size: 1.5rem; font-weight: 700; color: #EF4444;">
                        <span class="pgr-live-dot"></span>{live_matches}
                    </div>
                    <div style="font-size: 0.75rem; color: {PGR_COLORS["muted"]};">Live Matches</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    
    with cols[2]:
        if new_picks_today > 0:
            st.markdown(
                f"""
                <div style="text-align: center; padding: 0.5rem; background: {PGR_COLORS["bg_alt"]}; border-radius: 8px;">
                    <div style="font-size: 1.5rem; font-weight: 700; color: {PGR_COLORS["accent"]};">{new_picks_today}</div>
                    <div style="font-size: 0.75rem; color: {PGR_COLORS["muted"]};">New Picks Today</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
