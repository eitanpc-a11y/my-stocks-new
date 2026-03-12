# commodities_tab.py — סחורות: זהב, כסף, נפט, גז
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from config import COMMODITIES

@st.cache_data(ttl=300)
def _fetch_commodity(symbol: str) -> dict:
    try:
        h = yf.Ticker(symbol).history(period="3mo")
        if h.empty or len(h) < 5: return None
        px   = float(h["Close"].iloc[-1])
        prev = float(h["Close"].iloc[-2]) if len(h)>=2 else px
        chg  = (px/prev-1)*100
        hi52 = float(h["Close"].max())
        lo52 = float(h["Close"].min())
        # RSI
        d    = h["Close"].diff()
        g    = d.where(d>0,0).rolling(14).mean()
        l    = (-d.where(d<0,0)).rolling(14).mean().replace(0,1e-10)
        rsi  = float(100-(100/(1+g/l)).iloc[-1])
        ma50 = float(h["Close"].rolling(min(50,len(h))).mean().iloc[-1])
        # מגמה 30 יום
        trend_30d = (px / float(h["Close"].iloc[max(0,len(h)-30)])-1)*100
        return {
            "symbol": symbol, "price": px, "change": chg,
            "hi52": hi52, "lo52": lo52, "rsi": rsi,
            "ma50": ma50, "trend_30d": trend_30d,
        }
    except Exception:
        return None


def render_commodities():
    st.markdown(
        '<div class="ai-card" style="border-right-color:#f9a825;">'
        '<b>🏅 מרכז סחורות — זהב, כסף, נפט, גז</b><br>'
        '<small>נתוני Futures חיים ממכות החוזים העתידיים</small></div>',
        unsafe_allow_html=True,
    )

    # ── שלוף נתונים ──────────────────────────────────────────────────────────
    data = {}
    with st.spinner("שולף נתוני סחורות..."):
        for sym in COMMODITIES:
            r = _fetch_commodity(sym)
            if r: data[sym] = r

    if not data:
        st.error("לא ניתן לטעון נתוני סחורות.")
        return

    # ── כרטיסי סחורות ────────────────────────────────────────────────────────
    st.markdown("### 📊 סחורות מובילות")
    cols = st.columns(4)
    for i, (sym, info) in enumerate(data.items()):
        meta   = COMMODITIES[sym]
        chg_c  = "#2e7d32" if info["change"]>=0 else "#c62828"
        arrow  = "▲" if info["change"]>=0 else "▼"
        rsi    = info["rsi"]
        rsi_c  = "#c62828" if rsi>65 else ("#2e7d32" if rsi<35 else "#555")
        unit   = meta["unit"]
        cols[i % 4].markdown(f"""
        <div style="background:white;border-radius:12px;padding:12px;margin-bottom:10px;
                    box-shadow:0 2px 8px rgba(0,0,0,.08);border-top:4px solid #f9a825;">
            <div style="font-size:22px">{meta['emoji']} <b>{meta['name']}</b></div>
            <div style="font-size:20px;font-weight:800;margin:4px 0">{info['price']:,.2f}
                <span style="font-size:12px;color:#888">{unit}</span>
            </div>
            <div style="color:{chg_c};font-size:14px;font-weight:700">
                {arrow} {abs(info['change']):.2f}%
            </div>
            <div style="font-size:11px;color:{rsi_c};margin-top:4px">RSI: {rsi:.0f}</div>
            <div style="font-size:11px;color:#888">MA50: {info['ma50']:,.1f}</div>
        </div>
        """, unsafe_allow_html=True)

    # ── טבלה מפורטת ──────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 📋 ניתוח מפורט + המלצת AI")
    rows = []
    for sym, info in data.items():
        meta = COMMODITIES[sym]
        rsi  = info["rsi"]
        # המלצה
        if rsi < 30:
            rec = "קנייה חזקה 💎"
        elif rsi < 40:
            rec = "קנייה 🟢"
        elif rsi > 70:
            rec = "מכירה 🔴"
        elif rsi > 60:
            rec = "מכירה חלקית ⚠️"
        elif info["price"] > info["ma50"] and info["trend_30d"] > 2:
            rec = "החזק/קנה 📈"
        else:
            rec = "המתן ⚖️"
        # % מ-52W High
        pct_from_hi = (info["price"]/info["hi52"]-1)*100
        rows.append({
            "📌 סחורה":     f"{meta['emoji']} {meta['name']}",
            "💰 מחיר":      f"{info['price']:,.2f} {meta['unit']}",
            "📈 שינוי יומי":f"{'▲' if info['change']>=0 else '▼'}{abs(info['change']):.2f}%",
            "📊 RSI":       f"{rsi:.0f}",
            "📉 מ-52W High":f"{pct_from_hi:.1f}%",
            "📅 מגמה 30י":  f"{'▲' if info['trend_30d']>=0 else '▼'}{abs(info['trend_30d']):.1f}%",
            "🤖 המלצה AI":  rec,
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True)

    # ── קורלציות ─────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 🔗 קורלציות בין סחורות (30 יום)")
    price_data = {}
    for sym in list(COMMODITIES.keys())[:6]:
        try:
            h = yf.Ticker(sym).history(period="1mo")["Close"]
            if len(h) > 10: price_data[COMMODITIES[sym]["name"]] = h
        except Exception: pass
    if len(price_data) >= 3:
        import plotly.express as px
        corr_df = pd.DataFrame(price_data).pct_change().dropna().corr().fillna(0).round(2)
        fig_corr = px.imshow(
            corr_df, text_auto=True,
            color_continuous_scale="RdYlGn", zmin=-1, zmax=1,
            title="קורלציה בין סחורות"
        )
        fig_corr.update_layout(height=380, font=dict(size=11))
        st.plotly_chart(fig_corr)
        st.caption("🔴 +1 = זזים יחד (לא מגן) | 🟢 -1 = זזים הפוך (גידור מושלם!) | 🟡 0 = ללא קשר")
