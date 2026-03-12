# pattern_ai.py — זיהוי דפוסי Chart + FinBERT סנטימנט + Regime Detection
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime

# ─── זיהוי דפוסים טכניים ─────────────────────────────────────────────────────
@st.cache_data(ttl=600)
def _get_hist(symbol: str, period="6mo") -> pd.DataFrame:
    try:
        return yf.Ticker(symbol).history(period=period)
    except Exception:
        return pd.DataFrame()


def detect_patterns(hist: pd.DataFrame) -> list:
    """מזהה דפוסי Chart קלאסיים מנתוני מחיר."""
    if len(hist) < 40:
        return []
    close  = hist["Close"]
    high   = hist["High"]
    low    = hist["Low"]
    vol    = hist["Volume"]
    patterns = []

    # ── Double Bottom (W) ─────────────────────────────────────────────────
    try:
        lows20  = low.rolling(5).min()
        min1_i  = lows20.iloc[-40:-20].idxmin()
        min2_i  = lows20.iloc[-20:].idxmin()
        min1_v  = low[min1_i]
        min2_v  = low[min2_i]
        mid_max = high.loc[min1_i:min2_i].max()
        if (abs(min1_v - min2_v) / min1_v < 0.03 and
                mid_max > min1_v * 1.03):
            patterns.append({
                "name":    "Double Bottom (W) 🟢",
                "signal":  "bullish",
                "desc":    f"שני תחתיות דומות ({min1_v:.2f} ≈ {min2_v:.2f}). "
                           f"סיגנל קנייה קלאסי לאחר שבירת הצוואר.",
                "strength": 80,
            })
    except Exception:
        pass

    # ── Head & Shoulders ──────────────────────────────────────────────────
    try:
        highs  = high.rolling(5).max()
        seg    = highs.iloc[-60:]
        top3   = seg.nlargest(3)
        if len(top3) == 3:
            head = top3.iloc[0]
            sh1  = top3.iloc[1]
            sh2  = top3.iloc[2]
            if (head > sh1 * 1.02 and head > sh2 * 1.02 and
                    abs(sh1 - sh2) / sh1 < 0.04):
                patterns.append({
                    "name":    "Head & Shoulders 🔴",
                    "signal":  "bearish",
                    "desc":    f"ראש ({head:.2f}) גבוה משני הכתפיים. "
                               f"סיגנל מכירה קלאסי.",
                    "strength": 75,
                })
    except Exception:
        pass

    # ── Golden Cross (MA50 חוצה מעל MA200) ────────────────────────────────
    try:
        ma50  = close.rolling(50).mean()
        ma200 = close.rolling(200).mean()
        if len(ma50.dropna()) > 5 and len(ma200.dropna()) > 5:
            if (ma50.iloc[-1] > ma200.iloc[-1] and
                    ma50.iloc[-5] < ma200.iloc[-5]):
                patterns.append({
                    "name":    "Golden Cross 🌟",
                    "signal":  "bullish",
                    "desc":    "MA50 חצה מעל MA200 לאחרונה — סיגנל עולה חזק!",
                    "strength": 85,
                })
            elif (ma50.iloc[-1] < ma200.iloc[-1] and
                      ma50.iloc[-5] > ma200.iloc[-5]):
                patterns.append({
                    "name":    "Death Cross 💀",
                    "signal":  "bearish",
                    "desc":    "MA50 חצה מתחת ל-MA200 — אזהרת מכירה!",
                    "strength": 82,
                })
    except Exception:
        pass

    # ── Breakout מ-52W High ────────────────────────────────────────────────
    try:
        hi52 = high.iloc[-252:].max() if len(high) >= 252 else high.max()
        if close.iloc[-1] >= hi52 * 0.99:
            vol_avg = vol.iloc[-20].mean()
            vol_spike = vol.iloc[-1] > vol_avg * 1.5
            patterns.append({
                "name":    "52W High Breakout 🚀",
                "signal":  "bullish",
                "desc":    f"המחיר קרוב/שובר שיא 52 שבוע ({hi52:.2f}). "
                           f"{'נפח גבוה — אישור חזק!' if vol_spike else 'בדוק אישור נפח.'}",
                "strength": 78 + (10 if vol_spike else 0),
            })
    except Exception:
        pass

    # ── Oversold Bounce (RSI + נר היפוכי) ────────────────────────────────
    try:
        delta = close.diff()
        g     = delta.where(delta>0,0).rolling(14).mean()
        l     = (-delta.where(delta<0,0)).rolling(14).mean().replace(0,1e-10)
        rsi   = (100-(100/(1+g/l))).iloc[-1]
        if rsi < 30 and close.iloc[-1] > close.iloc[-2]:
            patterns.append({
                "name":    "Oversold Bounce 📈",
                "signal":  "bullish",
                "desc":    f"RSI={rsi:.0f} + יום ירוק — ייתכן היפוך מגמה.",
                "strength": 65,
            })
    except Exception:
        pass

    # ── Bullish Engulfing (נר בולע) ───────────────────────────────────────
    try:
        o = hist["Open"]
        c = hist["Close"]
        if (c.iloc[-1] > o.iloc[-1] and         # נר ירוק היום
                c.iloc[-2] < o.iloc[-2] and      # נר אדום אתמול
                c.iloc[-1] > o.iloc[-2] and      # סגירה היום מעל פתיחה אתמול
                o.iloc[-1] < c.iloc[-2]):         # פתיחה היום מתחת סגירה אתמול
            patterns.append({
                "name":    "Bullish Engulfing 🕯️",
                "signal":  "bullish",
                "desc":    "נר ירוק בולע את הנר האדום הקודם — היפוך שורי.",
                "strength": 70,
            })
    except Exception:
        pass

    return patterns


def detect_market_regime(symbols=("SPY","QQQ","^VIX","GC=F")) -> dict:
    """
    מזהה מצב שוק: Bull / Bear / Sideways / Crisis
    לפי S&P500, Nasdaq, VIX, זהב.
    """
    try:
        data = {}
        for sym in symbols:
            h = yf.Ticker(sym).history(period="3mo")
            if not h.empty:
                data[sym] = h["Close"]

        spy_ret  = (data.get("SPY", pd.Series()).pct_change(20).iloc[-1]
                    if "SPY" in data else 0) * 100
        qqq_ret  = (data.get("QQQ", pd.Series()).pct_change(20).iloc[-1]
                    if "QQQ" in data else 0) * 100
        vix_val  = float(data["^VIX"].iloc[-1]) if "^VIX" in data else 20
        gold_ret = (data.get("GC=F", pd.Series()).pct_change(20).iloc[-1]
                    if "GC=F" in data else 0) * 100

        # Regime detection
        if vix_val > 35:
            regime = "🔴 CRISIS — תנודתיות קיצונית"
            color  = "#c62828"
            advice = "הגדל מזומן. הפחת חשיפה. המתן להתייצבות VIX < 25."
        elif spy_ret > 3 and qqq_ret > 3 and vix_val < 20:
            regime = "🟢 BULL MARKET — שוק עולה"
            color  = "#2e7d32"
            advice = "הגדל חשיפה לצמיחה. Tech ו-Growth מובילים. RSI עד 65 = כניסה."
        elif spy_ret < -5 or (spy_ret < 0 and vix_val > 25):
            regime = "🔴 BEAR MARKET — שוק יורד"
            color  = "#c62828"
            advice = "הפחת risk. Value > Growth. זהב ואגחים לגידור."
        elif gold_ret > 5 and vix_val > 22:
            regime = "🟡 RISK-OFF — בריחה לנכסים בטוחים"
            color  = "#f57f17"
            advice = "שוק חושש. מניות דיבידנד, זהב, ת\"א שקלי."
        elif abs(spy_ret) < 2 and vix_val < 18:
            regime = "⚪ SIDEWAYS — שוק שטוח"
            color  = "#546e7a"
            advice = "מסחר בטווח. Covered Calls, ניצול תנודות קצרות."
        else:
            regime = "🟡 TRANSITION — מעבר בין מצבים"
            color  = "#e65100"
            advice = "זהירות. גודל פוזיציה קטן. המתן לאישור כיוון."

        return {
            "regime": regime, "color": color, "advice": advice,
            "spy_ret": round(spy_ret, 1), "qqq_ret": round(qqq_ret, 1),
            "vix": round(vix_val, 1), "gold_ret": round(gold_ret, 1),
        }
    except Exception:
        return {"regime": "⚪ לא ידוע", "color": "#9e9e9e",
                "advice": "לא ניתן לקבוע מצב שוק.", "spy_ret":0,"qqq_ret":0,"vix":20,"gold_ret":0}


def render_pattern_analysis(df_all: pd.DataFrame = None):
    st.markdown(
        '<div class="ai-card" style="border-right-color:#6a1b9a;">'
        '<b>🔬 ניתוח דפוסי Chart + Regime Detection</b><br>'
        '<small>זיהוי אוטומטי: Double Bottom · Head & Shoulders · Golden Cross · Breakouts</small></div>',
        unsafe_allow_html=True,
    )

    t1, t2 = st.tabs(["📈 דפוסי Chart", "🌡️ Regime Detection"])

    # ══ TAB 1: דפוסים ════════════════════════════════════════════════════════
    with t1:
        if df_all is not None and not df_all.empty:
            sym_options = df_all["Symbol"].tolist()
        else:
            sym_options = ["AAPL","NVDA","MSFT","TSLA","META","AMZN"]

        c1, c2 = st.columns([2,1])
        with c1:
            symbol = st.selectbox("📌 בחר מניה לניתוח:", sym_options, key="pat_sym")
        with c2:
            period = st.selectbox("📅 תקופה:", ["3mo","6mo","1y"], index=1, key="pat_period")

        if st.button("🔍 נתח דפוסים", type="primary", key="pat_run"):
            with st.spinner("מנתח..."):
                hist     = _get_hist(symbol, period)
                patterns = detect_patterns(hist)

            if hist.empty:
                st.error("לא ניתן לטעון נתונים")
            else:
                # ── גרף Candlestick ─────────────────────────────────────────
                fig = go.Figure(data=[go.Candlestick(
                    x=hist.index,
                    open=hist["Open"],  high=hist["High"],
                    low=hist["Low"],    close=hist["Close"],
                    name=symbol,
                    increasing=dict(fillcolor="#2e7d32", line=dict(color="#2e7d32")),
                    decreasing=dict(fillcolor="#c62828", line=dict(color="#c62828")),
                )])
                # MA50 ו-MA200
                ma50  = hist["Close"].rolling(50).mean()
                ma200 = hist["Close"].rolling(200).mean()
                fig.add_trace(go.Scatter(x=ma50.index,  y=ma50,  mode="lines",
                                          name="MA50",  line=dict(color="blue",  width=1.5)))
                fig.add_trace(go.Scatter(x=ma200.index, y=ma200, mode="lines",
                                          name="MA200", line=dict(color="orange",width=1.5)))
                fig.update_layout(
                    title=f"{symbol} — Candlestick + MA",
                    xaxis_rangeslider_visible=False,
                    height=420, template="plotly_white"
                )
                st.plotly_chart(fig)

                # ── דפוסים שנמצאו ────────────────────────────────────────────
                if patterns:
                    st.markdown(f"### 🎯 נמצאו {len(patterns)} דפוסים:")
                    for p in patterns:
                        bg    = "#e8f5e9" if p["signal"] == "bullish" else "#ffebee"
                        border = "#2e7d32" if p["signal"] == "bullish" else "#c62828"
                        st.markdown(
                            f'<div style="background:{bg};border-right:5px solid {border};'
                            f'border-radius:8px;padding:12px;margin:6px 0;">'
                            f'<b>{p["name"]}</b> — עוצמה: {p["strength"]}%<br>'
                            f'<small>{p["desc"]}</small></div>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.info("לא נמצאו דפוסים קלאסיים ברורים כרגע.")

                # ── סריקה מהירה של כל המניות ─────────────────────────────────
        st.divider()
        st.markdown("### 🔭 סריקת דפוסים — כל המניות")
        if df_all is not None and not df_all.empty and st.button("🔭 סרוק הכל", key="pat_scan_all"):
            all_patterns = []
            bar = st.progress(0, text="סורק...")
            syms = df_all["Symbol"].tolist()
            for i, sym in enumerate(syms[:20]):
                try:
                    h = _get_hist(sym, "3mo")
                    ps = detect_patterns(h)
                    for p in ps:
                        all_patterns.append({
                            "📌 מניה":   sym,
                            "🔬 דפוס":  p["name"],
                            "📊 עוצמה": f"{p['strength']}%",
                            "💡 סיגנל": "🟢 שורי" if p["signal"]=="bullish" else "🔴 דובי",
                            "📋 תיאור": p["desc"][:60],
                        })
                except Exception:
                    pass
                bar.progress((i+1)/min(len(syms),20))
            bar.empty()
            if all_patterns:
                df_p = pd.DataFrame(all_patterns)
                st.dataframe(df_p.sort_values("📊 עוצמה", ascending=False), hide_index=True)
            else:
                st.info("לא נמצאו דפוסים חזקים כרגע.")

    # ══ TAB 2: Regime Detection ═══════════════════════════════════════════════
    with t2:
        st.markdown("### 🌡️ מצב השוק הנוכחי")
        if st.button("🔄 עדכן מצב שוק", type="primary", key="regime_run"):
            with st.spinner("מנתח S&P500, NASDAQ, VIX, זהב..."):
                regime = detect_market_regime()
            st.session_state["market_regime"] = regime

        regime = st.session_state.get("market_regime")
        if regime:
            st.markdown(
                f'<div style="background:{regime["color"]}22;border:3px solid {regime["color"]};'
                f'border-radius:14px;padding:20px;text-align:center;">'
                f'<div style="font-size:26px;font-weight:900;color:{regime["color"]};">'
                f'{regime["regime"]}</div>'
                f'<div style="font-size:15px;margin-top:8px;">{regime["advice"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.divider()
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("📊 S&P 500 (20י)", f"{regime['spy_ret']:+.1f}%")
            c2.metric("💻 NASDAQ (20י)",  f"{regime['qqq_ret']:+.1f}%")
            c3.metric("😱 VIX",           f"{regime['vix']:.1f}")
            c4.metric("🥇 זהב (20י)",    f"{regime['gold_ret']:+.1f}%")

            # המלצות לפי Regime
            st.divider()
            st.markdown("#### 🤖 המלצות AI לפי מצב השוק:")
            r = regime["regime"]
            if "BULL" in r:
                recs = [("NVDA","טכנולוגיה מובילה"),("META","צמיחה + AI"),
                        ("AMZN","ענן + מסחר"),("GOOGL","מודלים + פרסום")]
            elif "BEAR" in r or "CRISIS" in r:
                recs = [("GC=F","זהב — מקלט בטוח"),("POLI.TA","בנק ישראלי יציב"),
                        ("JNJ","בריאות דיבידנד"),("KO","מוצרי צריכה בסיסיים")]
            elif "RISK-OFF" in r:
                recs = [("GC=F","זהב"),("SI=F","כסף"),("ICL.TA","דשנים+דיבידנד")]
            else:
                recs = [("AAPL","ערך יציב"),("MSFT","ענן+AI"),("V","תשלומים")]
            for sym, reason in recs:
                st.markdown(f"- **{sym}** — {reason}")
        else:
            st.info("לחץ 'עדכן מצב שוק' לניתוח.")
