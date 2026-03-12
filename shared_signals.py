# shared_signals.py — אוטובוס נתונים משותף לכל הסוכנים
"""
כל סוכן כותב ל-shared signals וקורא ממנו.
זה מאפשר ל-ML לספק מידע לסוכן הערך וסוכן היומי בזמן אמת.
"""
from datetime import datetime
from storage import load, save


SIGNAL_KEY   = "shared_signals"
CONSENSUS_KEY = "agent_consensus"


def write_signal(
    source: str,           # "ml_value", "ml_day", "value_agent", "day_agent", "scheduler"
    symbol: str,
    direction: str,        # "BUY", "SELL", "HOLD", "WATCH"
    confidence: float,     # 0-100
    reason: str = "",
    timeframe: str = "long",  # "intraday", "short" (1-5d), "long" (15d+)
    price: float = 0.0,
    model_type: str = "",
):
    """כתוב סיגנל חדש — כל סוכן משתמש בזה."""
    signals = load(SIGNAL_KEY, [])
    signals.insert(0, {
        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "📌": symbol,
        "↔️": direction,
        "🎯": round(confidence, 1),
        "📝": reason[:120],
        "🕐": timeframe,
        "💰": round(price, 4),
        "🤖": source,
        "🔬": model_type,
    })
    # שמור רק 500 סיגנלים אחרונים
    save(SIGNAL_KEY, signals[:500])


def read_signals(
    symbol: str = None,
    timeframe: str = None,
    direction: str = None,
    min_confidence: float = 0,
    hours_back: int = 48,
    limit: int = 50,
) -> list:
    """קרא סיגנלים עם פילטורים אופציונליים."""
    signals = load(SIGNAL_KEY, [])
    cutoff = None
    if hours_back:
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(hours=hours_back)).strftime("%Y-%m-%d %H:%M")

    out = []
    for s in signals:
        if cutoff and s.get("⏰", "") < cutoff:
            continue
        if symbol and s.get("📌") != symbol:
            continue
        if timeframe and s.get("🕐") != timeframe:
            continue
        if direction and s.get("↔️") != direction:
            continue
        if s.get("🎯", 0) < min_confidence:
            continue
        out.append(s)
        if len(out) >= limit:
            break
    return out


def get_consensus(symbol: str, hours_back: int = 24) -> dict:
    """
    מחזיר קונצנזוס של כל הסוכנים על סימול נתון.
    result: {"direction": "BUY"/"SELL"/"HOLD", "confidence": 0-100,
             "sources": [...], "ml_long": ..., "ml_short": ...}
    """
    sigs = read_signals(symbol=symbol, hours_back=hours_back, min_confidence=50)
    if not sigs:
        return {"direction": "HOLD", "confidence": 0, "sources": [], "count": 0}

    buy_conf  = [s["🎯"] for s in sigs if s["↔️"] == "BUY"]
    sell_conf = [s["🎯"] for s in sigs if s["↔️"] == "SELL"]
    sources   = list({s["🤖"] for s in sigs})

    ml_long  = next((s for s in sigs if s.get("🕐") == "long"  and "ml" in s.get("🤖","")), None)
    ml_short = next((s for s in sigs if s.get("🕐") == "short" and "ml" in s.get("🤖","")), None)

    avg_buy  = sum(buy_conf)  / len(buy_conf)  if buy_conf  else 0
    avg_sell = sum(sell_conf) / len(sell_conf) if sell_conf else 0

    if avg_buy > avg_sell and avg_buy >= 55:
        direction  = "BUY"
        confidence = avg_buy
    elif avg_sell > avg_buy and avg_sell >= 55:
        direction  = "SELL"
        confidence = avg_sell
    else:
        direction  = "HOLD"
        confidence = max(avg_buy, avg_sell)

    return {
        "direction":  direction,
        "confidence": round(confidence, 1),
        "sources":    sources,
        "count":      len(sigs),
        "ml_long":    ml_long,
        "ml_short":   ml_short,
        "buy_signals":  len(buy_conf),
        "sell_signals": len(sell_conf),
    }


def get_top_buys(timeframe: str = None, min_confidence: float = 60,
                 hours_back: int = 24, limit: int = 10) -> list:
    """מחזיר רשימת נכסים עם הכי הרבה סיגנלי קנייה."""
    sigs = read_signals(direction="BUY", timeframe=timeframe,
                        min_confidence=min_confidence, hours_back=hours_back, limit=200)
    from collections import defaultdict
    sym_conf = defaultdict(list)
    for s in sigs:
        sym_conf[s["📌"]].append(s["🎯"])
    ranked = sorted(sym_conf.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True)
    return [{"symbol": sym, "avg_conf": round(sum(c)/len(c), 1), "n_signals": len(c)}
            for sym, c in ranked[:limit]]


def render_shared_signals():
    """הצג את מרכז הסיגנלים — לשימוש ב-app.py."""
    import streamlit as st
    import pandas as pd

    st.markdown(
        '<div class="ai-card" style="border-right-color:#ff6f00;">'
        '<b>🔗 מרכז הסיגנלים המשותף</b><br>'
        'כל הסוכנים (ML, ערך, יומי, סקדולר) כותבים כאן — שיתוף מלא בזמן אמת.'
        '</div>',
        unsafe_allow_html=True,
    )

    signals = load(SIGNAL_KEY, [])
    if not signals:
        st.info("אין סיגנלים עדיין. הרץ ML או סוכן כלשהו.")
        return

    df = pd.DataFrame(signals[:100])
    st.metric("סה\"כ סיגנלים", len(signals))

    # פילטרים
    col1, col2, col3 = st.columns(3)
    with col1:
        dir_f = st.selectbox("כיוון", ["הכל", "BUY", "SELL", "HOLD", "WATCH"], key="sig_dir")
    with col2:
        tf_f  = st.selectbox("מסגרת זמן", ["הכל", "intraday", "short", "long"], key="sig_tf")
    with col3:
        conf_f = st.slider("ביטחון מינימלי", 0, 100, 50, key="sig_conf")

    filtered = [s for s in signals
                if (dir_f == "הכל" or s.get("↔️") == dir_f)
                and (tf_f == "הכל" or s.get("🕐") == tf_f)
                and s.get("🎯", 0) >= conf_f]

    st.dataframe(pd.DataFrame(filtered[:50]), hide_index=True)

    # קונצנזוס
    st.divider()
    st.subheader("🏆 קונצנזוס — נכסים הכי מומלצים")
    top = get_top_buys(min_confidence=conf_f, limit=10)
    if top:
        st.dataframe(pd.DataFrame(top), hide_index=True)
    else:
        st.info("אין קונצנזוס קנייה עם הפרמטרים הנוכחיים.")

    if st.button("🗑️ נקה סיגנלים", key="sig_clear"):
        save(SIGNAL_KEY, [])
        st.success("נוקה!")
        st.rerun()
