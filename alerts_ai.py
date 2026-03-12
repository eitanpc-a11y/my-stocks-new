# alerts_ai.py — מרכז התראות חכם מלא + שליחת Telegram
import streamlit as st
import pandas as pd
from datetime import datetime
from storage import save, load


def _send_to_telegram(title: str, body: str):
    """שולח ל-Telegram אם מחובר."""
    try:
        import telegram_ai
        telegram_ai.send_alert_notification(title, body)
    except Exception:
        pass


def render_smart_alerts(df_all):
    st.markdown(
        '<div class="ai-card" style="border-right-color:#ff9800;">'
        '<b>🔔 מרכז התראות AI</b> — דוחות, RSI, Insider, Stop-Loss + שליחה לטלגרם</div>',
        unsafe_allow_html=True,
    )

    if df_all is None or df_all.empty:
        st.warning("אין נתונים.")
        return

    # ── מדדים מהירים ─────────────────────────────────────────────────────────
    overbought = df_all[df_all["RSI"] > 70]
    oversold   = df_all[df_all["RSI"] < 30]
    earnings14 = df_all[df_all["DaysToEarnings"].between(0, 14)]
    high_ins   = df_all[df_all["InsiderHeld"] > 5.0]
    gold_stocks= df_all[df_all["Score"] >= 5]

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("📅 דוחות קרובים",    len(earnings14), help="ב-14 ימים הקרובים")
    c2.metric("🟢 RSI נמוך (<30)",   len(oversold),   help="קנייה יתר — הזדמנות")
    c3.metric("🔴 RSI גבוה (>70)",   len(overbought), help="מכירה יתר — שקול מימוש")
    c4.metric("💎 מניות זהב (≥5)",   len(gold_stocks))
    st.divider()

    t1,t2,t3,t4,t5 = st.tabs(["📅 דוחות","📊 RSI","🏛️ Insider","💎 זהב","⚙️ הגדרות"])

    # ── דוחות ────────────────────────────────────────────────────────────────
    with t1:
        st.markdown("### 📅 דוחות קרובים (30 יום)")
        soon30 = df_all[df_all["DaysToEarnings"].between(0, 30)].sort_values("DaysToEarnings")
        if not soon30.empty:
            for _, r in soon30.iterrows():
                days = int(r["DaysToEarnings"])
                color = "#c62828" if days <= 3 else "#e65100" if days <= 7 else "#1565c0"
                urgency = "🚨 מחר!" if days <= 1 else f"בעוד {days} ימים"
                st.markdown(
                    f'<div style="background:#fff8e1;border-right:5px solid {color};'
                    f'border-radius:8px;padding:10px 14px;margin:5px 0;">'
                    f'<b>{r["Symbol"]}</b> — {urgency} ({r["EarningsDate"]}) | '
                    f'מחיר: {r["PriceStr"]} | ציון: {r["Score"]}/6</div>',
                    unsafe_allow_html=True,
                )
                if days <= 3:
                    _send_to_telegram(
                        f"📅 דוח קרוב: {r['Symbol']}",
                        f"בעוד {days} ימים | מחיר: {r['PriceStr']}"
                    )
        else:
            st.info("אין דוחות ב-30 הימים הקרובים.")

    # ── RSI ───────────────────────────────────────────────────────────────────
    with t2:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🟢 מכירת יתר — RSI < 30 (הזדמנות)")
            if not oversold.empty:
                for _, r in oversold.sort_values("RSI").iterrows():
                    st.success(
                        f"**{r['Symbol']}** — RSI **{r['RSI']:.1f}** | "
                        f"{r['PriceStr']} | ציון {r['Score']}/6"
                    )
            else:
                st.info("אין מניות ב-oversold")
        with c2:
            st.markdown("### 🔴 קנייה יתר — RSI > 70 (שקול מימוש)")
            if not overbought.empty:
                for _, r in overbought.sort_values("RSI", ascending=False).iterrows():
                    st.error(
                        f"**{r['Symbol']}** — RSI **{r['RSI']:.1f}** | "
                        f"{r['PriceStr']} | ציון {r['Score']}/6"
                    )
            else:
                st.info("אין מניות ב-overbought")

        # התראות RSI ל-Telegram
        if (not oversold.empty or not overbought.empty):
            if st.button("📤 שלח התראות RSI לטלגרם", key="al_rsi_tg"):
                for _, r in oversold.iterrows():
                    _send_to_telegram(f"🟢 RSI נמוך: {r['Symbol']}",
                                      f"RSI={r['RSI']:.0f} | {r['PriceStr']}")
                for _, r in overbought.iterrows():
                    _send_to_telegram(f"🔴 RSI גבוה: {r['Symbol']}",
                                      f"RSI={r['RSI']:.0f} | {r['PriceStr']}")
                st.success("✅ נשלח!")

    # ── Insider ───────────────────────────────────────────────────────────────
    with t3:
        st.markdown("### 🏛️ החזקות בעלי עניין")
        if not high_ins.empty:
            # Build column list safely
            cols_to_show = ["Symbol","PriceStr","InsiderHeld","Score"]
            if "Action" in high_ins.columns:
                cols_to_show.append("Action")
            
            df_ins = high_ins[cols_to_show].copy()
            df_ins["InsiderHeld"] = df_ins["InsiderHeld"].apply(lambda x: f"{x:.1f}%")
            st.dataframe(df_ins.sort_values("InsiderHeld", ascending=False), hide_index=True)
            st.info("💡 אחזקת insider גבוהה = האמונה של ההנהלה במניה. "
                    "מעל 10% = חיובי מאוד.")
        else:
            st.info("אין נתוני insider בולטים.")

    # ── זהב ──────────────────────────────────────────────────────────────────
    with t4:
        st.markdown("### 💎 מניות זהב — ציון 5+ (כל הקריטריונים)")
        if not gold_stocks.empty:
            for _, r in gold_stocks.sort_values("Score", ascending=False).iterrows():
                gap = ((r["FairValue"]-r["Price"])/r["Price"]*100) if r.get("FairValue",0)>0 else 0
                st.markdown(
                    f'<div style="background:linear-gradient(90deg,#fff8e1,#fff);'
                    f'border-right:6px solid #f9a825;border-radius:10px;'
                    f'padding:12px 16px;margin:5px 0;">'
                    f'<b>💎 {r["Symbol"]}</b> ציון {r["Score"]}/6 | '
                    f'{r["PriceStr"]} | RSI: {r["RSI"]:.0f} | '
                    f'{"הנחה: " + str(round(gap,1)) + "% מהשווי ההוגן" if gap > 0 else ""}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("אין מניות זהב כרגע.")

    # ── הגדרות ────────────────────────────────────────────────────────────────
    with t5:
        st.markdown("### ⚙️ הגדרות התראות")
        rsi_low  = st.slider("RSI נמוך — סף קנייה", 20, 40, 30, key="al_rsi_l")
        rsi_high = st.slider("RSI גבוה — סף מכירה", 60, 85, 70, key="al_rsi_h")
        earn_days = st.slider("ימים לפני דוח — התראה", 1, 14, 3, key="al_earn")
        if st.button("💾 שמור", key="al_save"):
            save("alert_rsi_low",  rsi_low)
            save("alert_rsi_high", rsi_high)
            save("alert_earn_days", earn_days)
            st.success("✅ נשמר!")
