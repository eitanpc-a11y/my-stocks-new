# execution_ai.py — מנוע ביצוע עם מחיר שוק חי
import streamlit as st
import pandas as pd
import yfinance as yf
import random
from datetime import datetime


def _live_price(symbol, fallback=100.0):
    try:
        h = yf.Ticker(symbol).history(period="1d", interval="1m")
        if not h.empty:
            return float(h["Close"].iloc[-1])
    except Exception:
        pass
    return fallback


def _fill(price, order_type):
    if "Market" in order_type:
        return round(price * (1 + random.uniform(-0.002, 0.003)), 4)
    return round(price, 4)


def render_execution_engine():
    st.markdown(
        '<div class="ai-card" style="border-right-color: #607d8b;">'
        '<b>⚙️ מנוע ביצוע (הדמייה + מחיר שוק חי):</b> '
        'Limit, Market, Stop Loss עם Slippage מציאותי.</div>',
        unsafe_allow_html=True,
    )
    st.info("ℹ️ מצב הדמייה — מחיר השוק נשאב מ-yfinance בזמן אמת.")

    if "exec_orders" not in st.session_state:
        st.session_state.exec_orders = []
    if "exec_log" not in st.session_state:
        st.session_state.exec_log = []

    st.subheader("📋 הגש פקודה")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        symbol = st.text_input("סימול", value="AAPL", key="exec_sym").upper().strip()
    with col2:
        side = st.selectbox("כיוון", ["קנייה 🟢", "מכירה 🔴"], key="exec_side")
    with col3:
        order_type = st.selectbox("סוג", ["Limit Order", "Market Order", "Stop Loss"], key="exec_type")
    with col4:
        qty = st.number_input("כמות", min_value=1, value=10, key="exec_qty")

    col5, col6, col7 = st.columns(3)
    with col5:
        use_live = st.toggle("🔴 מחיר חי מהבורסה", value=True, key="exec_live")
    with col6:
        manual_px = st.number_input("מחיר ידני ($)", min_value=0.01, value=150.0,
                                     step=0.5, key="exec_price", disabled=use_live)
    with col7:
        tif = st.selectbox("תוקף", ["Day", "GTC", "IOC"], key="exec_tif")

    if st.button("🚀 שגר פקודה", type="primary", key="exec_run"):
        market_px = _live_price(symbol, manual_px) if use_live else manual_px
        if use_live:
            st.caption(f"📡 מחיר שוק חי: ${market_px:.2f}")
        filled = _fill(market_px, order_type)
        status = "✅ בוצע" if order_type != "Stop Loss" else "⏳ ממתין לטריגר"
        slip = abs(filled - market_px)
        order = {
            "⏰ זמן": datetime.now().strftime("%H:%M:%S"),
            "📌 סימול": symbol,
            "↔️": side,
            "📑 סוג": order_type,
            "🔢 כמות": qty,
            "💰 שוק": f"${market_px:.2f}",
            "✅ ביצוע": f"${filled:.2f}",
            "Slippage": f"${slip:.4f}",
            "🕐 TIF": tif,
            "📊 סטטוס": status,
            "💵 שווי": f"${filled * qty:,.2f}",
        }
        st.session_state.exec_orders.insert(0, order)
        st.session_state.exec_log.insert(0,
            f"[{order['⏰ זמן']}] {side} {qty}×{symbol} @ ${filled:.2f} ({order_type}) → {status}")
        if status == "✅ בוצע":
            st.success(f"✅ {qty}×{symbol} @ ${filled:.2f} | שווי: ${filled*qty:,.2f} | Slippage: ${slip:.4f}")
        else:
            st.warning(f"⏳ Stop Loss @ ${filled:.2f}")

    if st.session_state.exec_orders:
        st.subheader("📜 היסטוריית פקודות")
        st.dataframe(pd.DataFrame(st.session_state.exec_orders), hide_index=True)
        try:
            buys  = sum(float(o["💵 שווי"].replace("$","").replace(",",""))
                        for o in st.session_state.exec_orders if "קנייה" in o["↔️"])
            sells = sum(float(o["💵 שווי"].replace("$","").replace(",",""))
                        for o in st.session_state.exec_orders if "מכירה" in o["↔️"])
            m1, m2, m3 = st.columns(3)
            m1.metric("📥 קניות", f"${buys:,.2f}")
            m2.metric("📤 מכירות", f"${sells:,.2f}")
            m3.metric("📊 פקודות", len(st.session_state.exec_orders))
        except Exception:
            pass
        if st.button("🗑️ נקה", key="exec_clear"):
            st.session_state.exec_orders = []
            st.session_state.exec_log = []
            st.rerun()

    if st.session_state.exec_log:
        with st.expander("📋 יומן מנוע"):
            for line in st.session_state.exec_log[:30]:
                st.code(line, language=None)
