# telegram_ai.py — בוט טלגרם מלא עם התראות חיות
# ════════════════════════════════════════════════════════════════
# הרשמה: t.me/BotFather → /newbot → קבל TOKEN
# Chat ID: שלח הודעה לבוט שלך, אח"כ:
#   https://api.telegram.org/bot<TOKEN>/getUpdates
# ════════════════════════════════════════════════════════════════

import streamlit as st
import requests
import json
from datetime import datetime
from storage import save, load

TG_TOKEN_KEY  = "telegram_token"
TG_CHATID_KEY = "telegram_chat_id"
TG_ACTIVE_KEY = "telegram_active"
TG_ALERTS_KEY = "telegram_alert_settings"
TG_LOG_KEY    = "telegram_sent_log"


def _send_message(token: str, chat_id: str, text: str, parse_mode="HTML") -> bool:
    """שולח הודעה לטלגרם. מחזיר True אם הצליח."""
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=8
        )
        return r.status_code == 200
    except Exception:
        return False


def _test_connection(token: str, chat_id: str) -> bool:
    msg = (
        "🌐 <b>Investment Hub Elite 2026</b>\n"
        "✅ חיבור טלגרם הצליח!\n"
        f"🕒 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    return _send_message(token, chat_id, msg)


def send_trade_alert(symbol: str, action: str, price: float,
                     reason: str, pnl: float = None):
    """שלח התראת עסקה — קרא מ-ai_portfolio ומ-simulator."""
    token   = load(TG_TOKEN_KEY,  "")
    chat_id = load(TG_CHATID_KEY, "")
    active  = load(TG_ACTIVE_KEY, False)
    if not (token and chat_id and active):
        return
    alerts = load(TG_ALERTS_KEY, {})
    if not alerts.get("trades", True):
        return

    emoji = "🟢" if action == "קנייה" else "🔴"
    pnl_line = f"\n💰 רווח/הפסד: {'🟢 +' if pnl>=0 else '🔴 '}₪{abs(pnl):,.0f}" if pnl is not None else ""
    msg = (
        f"📊 <b>Investment Hub — עסקה חדשה</b>\n"
        f"{emoji} <b>{action}</b>: <code>{symbol}</code>\n"
        f"💵 מחיר: ${price:,.2f}\n"
        f"📋 סיבה: {reason[:80]}"
        f"{pnl_line}\n"
        f"🕒 {datetime.now().strftime('%H:%M:%S')}"
    )
    ok = _send_message(token, chat_id, msg)
    if ok:
        log = load(TG_LOG_KEY, [])
        log.insert(0, {"time": datetime.now().isoformat()[:16], "msg": f"{action} {symbol}", "ok": True})
        save(TG_LOG_KEY, log[:50])


def send_alert_notification(title: str, body: str):
    """שלח התראה כללית (SL, TP, דוח קרוב...)"""
    token   = load(TG_TOKEN_KEY,  "")
    chat_id = load(TG_CHATID_KEY, "")
    active  = load(TG_ACTIVE_KEY, False)
    if not (token and chat_id and active):
        return
    msg = f"🔔 <b>{title}</b>\n{body}\n🕒 {datetime.now().strftime('%H:%M')}"
    _send_message(token, chat_id, msg)


def send_daily_summary(portfolio_value: float, pnl: float, n_positions: int):
    """שלח סיכום יומי אוטומטי."""
    token   = load(TG_TOKEN_KEY,  "")
    chat_id = load(TG_CHATID_KEY, "")
    active  = load(TG_ACTIVE_KEY, False)
    if not (token and chat_id and active):
        return
    alerts = load(TG_ALERTS_KEY, {})
    if not alerts.get("daily_summary", True):
        return
    sign = "🟢" if pnl >= 0 else "🔴"
    msg = (
        f"📈 <b>סיכום יומי — Investment Hub</b>\n"
        f"💼 שווי תיק AI: ₪{portfolio_value:,.0f}\n"
        f"{sign} רווח/הפסד: {'+'if pnl>=0 else ''}₪{pnl:,.0f}\n"
        f"📊 פוזיציות פתוחות: {n_positions}\n"
        f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    _send_message(token, chat_id, msg)


def render_telegram_integration():
    st.markdown(
        '<div class="ai-card" style="border-right-color:#2CA5E0;">'
        '<b>📱 בוט טלגרם — התראות Push לטלפון</b><br>'
        '<small>קבל התראות על עסקות, Stop-Loss, דוחות קרובים ועוד</small></div>',
        unsafe_allow_html=True,
    )

    # טעינת מצב שמור
    token   = load(TG_TOKEN_KEY,  "")
    chat_id = load(TG_CHATID_KEY, "")
    active  = load(TG_ACTIVE_KEY, False)
    alerts  = load(TG_ALERTS_KEY, {
        "trades": True, "stop_loss": True, "earnings": True,
        "daily_summary": True, "fear_greed": False,
    })

    # ── מצב חיבור ────────────────────────────────────────────────────────────
    status_color = "#2e7d32" if (token and active) else "#888"
    status_text  = "🟢 מחובר ופעיל" if (token and active) else "⚪ לא מחובר"
    st.markdown(
        f'<div style="background:{"#e8f5e9" if active else "#f5f5f5"};'
        f'border:2px solid {status_color};border-radius:8px;'
        f'padding:10px 16px;font-weight:700;color:{status_color};">'
        f'סטטוס: {status_text}</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # ── הגדרת חיבור ──────────────────────────────────────────────────────────
    st.markdown("### 🔧 הגדרת בוט")

    with st.expander("📖 איך מקבלים Token?", expanded=not bool(token)):
        st.markdown("""
**שלב 1:** פתח טלגרם וחפש `@BotFather`

**שלב 2:** שלח `/newbot` ועקוב אחרי ההוראות

**שלב 3:** קבל `TOKEN` בפורמט: `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`

**שלב 4:** שלח הודעה כלשהי לבוט שיצרת

**שלב 5:** פתח בדפדפן:
`https://api.telegram.org/bot<TOKEN>/getUpdates`

**שלב 6:** מצא את `"id"` בתוך `"chat"` — זה ה-Chat ID שלך
        """)

    c1, c2 = st.columns(2)
    with c1:
        new_token = st.text_input("🔑 Bot Token:", value=token,
                                   type="password", placeholder="123456:ABCdef...",
                                   key="tg_token_input")
    with c2:
        new_chat  = st.text_input("💬 Chat ID:", value=chat_id,
                                   placeholder="123456789", key="tg_chat_input")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("💾 שמור & בדוק", type="primary", key="tg_save"):
            if new_token and new_chat:
                with st.spinner("מתחבר..."):
                    ok = _test_connection(new_token, new_chat)
                if ok:
                    save(TG_TOKEN_KEY,  new_token)
                    save(TG_CHATID_KEY, new_chat)
                    save(TG_ACTIVE_KEY, True)
                    st.success("✅ מחובר! קיבלת הודעת ניסיון בטלגרם")
                    st.rerun()
                else:
                    st.error("❌ חיבור נכשל. בדוק Token ו-Chat ID")
            else:
                st.warning("הכנס Token ו-Chat ID")

    with col2:
        if token and st.button("📤 שלח ניסיון", key="tg_test"):
            ok = _test_connection(token, chat_id)
            st.success("✅ נשלח!") if ok else st.error("❌ שליחה נכשלה")

    with col3:
        if token and st.button("🔌 נתק", key="tg_disconnect"):
            save(TG_ACTIVE_KEY, False)
            st.rerun()

    st.divider()

    # ── הגדרות התראות ────────────────────────────────────────────────────────
    st.markdown("### 🔔 סוגי התראות")
    c1, c2 = st.columns(2)
    new_alerts = {}
    with c1:
        new_alerts["trades"]        = st.toggle("📈 עסקות קנייה/מכירה",    value=alerts.get("trades", True),  key="tg_al1")
        new_alerts["stop_loss"]     = st.toggle("🛡️ Stop-Loss / Take-Profit", value=alerts.get("stop_loss",True), key="tg_al2")
        new_alerts["earnings"]      = st.toggle("📅 דוחות כספיים קרובים",  value=alerts.get("earnings",True), key="tg_al3")
    with c2:
        new_alerts["daily_summary"] = st.toggle("📊 סיכום יומי (22:00)",   value=alerts.get("daily_summary",True), key="tg_al4")
        new_alerts["fear_greed"]    = st.toggle("😱 Fear<20 / Greed>80",   value=alerts.get("fear_greed",False),   key="tg_al5")

    if st.button("💾 שמור הגדרות התראות", key="tg_save_alerts"):
        save(TG_ALERTS_KEY, new_alerts)
        st.success("✅ נשמר!")

    st.divider()

    # ── לוג שליחות ────────────────────────────────────────────────────────────
    log = load(TG_LOG_KEY, [])
    if log:
        st.markdown("### 📋 הודעות אחרונות שנשלחו")
        log_df = pd.DataFrame(log[:10])
        st.dataframe(log_df, hide_index=True)

    # ── תצוגה מקדימה ─────────────────────────────────────────────────────────
    st.markdown("### 👁️ תצוגה מקדימה להודעות")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        <div style="background:#e3f2fd;border-radius:12px;padding:14px;font-family:monospace;font-size:13px;">
        📊 <b>Investment Hub — עסקה חדשה</b><br>
        🟢 <b>קנייה</b>: NVDA<br>
        💵 מחיר: $125.40<br>
        📋 סיבה: ציון PDF 5/6 | RSI 36<br>
        🕒 14:32:05
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown("""
        <div style="background:#fff8e1;border-radius:12px;padding:14px;font-family:monospace;font-size:13px;">
        📈 <b>סיכום יומי</b><br>
        💼 שווי תיק AI: ₪12,450<br>
        🟢 רווח: +₪450<br>
        📊 פוזיציות: 3<br>
        📅 01/03/2026 22:00
        </div>""", unsafe_allow_html=True)


import pandas as pd
