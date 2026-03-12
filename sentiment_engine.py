# sentiment_engine.py — ניתוח סנטימנט חדשות אמיתי
# ✅ TextBlob לניתוח NLP
# ✅ כתיבה לאוטובוס הסיגנלים (Consensus Voting)
# ✅ כיסוי כל סוגי הנכסים
import yfinance as yf
from datetime import datetime
from storage import load, save
from shared_signals import write_signal
from api_cache import cached_api_call, throttle

try:
    from textblob import TextBlob
    TB_OK = True
except ImportError:
    TB_OK = False


# ── מילון מילות מפתח עם משקל (לגיבוי כשאין TextBlob) ─────────────────────
_BULL_WORDS = {
    "beat": 1.5, "record": 1.2, "growth": 1.0, "upgrade": 1.5, "buy": 1.3,
    "rally": 1.2, "soar": 1.4, "surge": 1.4, "profit": 1.0, "revenue": 0.8,
    "bull": 1.3, "breakout": 1.5, "launch": 0.9, "partnership": 0.9,
    "dividend": 0.8, "strong": 1.0, "innovation": 0.8, "acquire": 0.9,
    "deal": 0.7, "ai": 0.6, "target raised": 1.5, "above expectations": 1.5,
}
_BEAR_WORDS = {
    "miss": 1.5, "downgrade": 1.5, "sell": 1.2, "drop": 1.2, "fall": 1.1,
    "lawsuit": 1.3, "loss": 1.3, "decline": 1.0, "warning": 1.2, "risk": 0.7,
    "bear": 1.2, "recall": 1.4, "investigation": 1.4, "fraud": 1.8,
    "cut": 1.1, "layoff": 1.2, "below expectations": 1.5, "concern": 0.8,
    "fine": 1.0, "penalty": 1.1, "bankruptcy": 2.0, "default": 1.8,
}


def _keyword_score(text: str) -> float:
    """
    ציון סנטימנט לפי מילות מפתח, -1 עד +1.
    חיובי = שורי, שלילי = דובי.
    """
    t = text.lower()
    bull = sum(w for kw, w in _BULL_WORDS.items() if kw in t)
    bear = sum(w for kw, w in _BEAR_WORDS.items() if kw in t)
    total = bull + bear
    if total == 0:
        return 0.0
    return (bull - bear) / total


def _textblob_score(text: str) -> float:
    """TextBlob polarity: -1 עד +1."""
    try:
        return TextBlob(text).sentiment.polarity
    except Exception:
        return 0.0


def score_headline(title: str) -> float:
    """
    מחזיר ציון -1 עד +1 עבור כותרת חדשה.
    משתמש ב-TextBlob אם זמין, אחרת keyword.
    """
    if TB_OK:
        tb = _textblob_score(title)
        kw = _keyword_score(title)
        return round((tb * 0.6 + kw * 0.4), 3)
    return round(_keyword_score(title), 3)


def analyze_symbol(symbol: str, max_news: int = 8, _ttl: int = 3600) -> dict:
    """
    מנתח סנטימנט חדשות לסימול נתון.
    
    מחזיר:
    {
        score: 0-100 (50 = נייטרל, >60 = שורי, <40 = דובי)
        direction: "BUY" | "HOLD" | "SELL"
        confidence: 0-100
        headlines: [{"title":..., "score":..., "label":...}]
        n_news: int
        label: "שורי חזק" / "שורי" / "ניטרלי" / "דובי" / "דובי חזק"
    }
    """
    # קאש 1 שעה — חדשות לא משתנות כל דקה
    cached_val, hit = __import__("api_cache").cache_get(f"sentiment_{symbol}", ttl=_ttl)
    if hit:
        return cached_val

    try:
        throttle("yfinance", 1.0)
        news_items = yf.Ticker(symbol).news or []
    except Exception:
        news_items = []

    if not news_items:
        return {
            "score": 50, "direction": "HOLD", "confidence": 0,
            "headlines": [], "n_news": 0, "label": "ניטרלי — אין חדשות",
            "symbol": symbol,
        }

    headline_scores = []
    for item in news_items[:max_news]:
        title = item.get("title", "")
        if not title and "content" in item:
            title = item["content"].get("title", "")
        if not title:
            continue
        sc = score_headline(title)
        headline_scores.append({
            "title": title[:100],
            "score": sc,
            "label": "🟢 חיובי" if sc > 0.1 else ("🔴 שלילי" if sc < -0.1 else "⚪ ניטרלי"),
        })

    if not headline_scores:
        return {
            "score": 50, "direction": "HOLD", "confidence": 0,
            "headlines": [], "n_news": 0, "label": "ניטרלי",
            "symbol": symbol,
        }

    raw_avg = sum(h["score"] for h in headline_scores) / len(headline_scores)
    normalized = round(50 + raw_avg * 50)          # -1→0, 0→50, +1→100
    normalized  = max(0, min(100, normalized))

    bull_count  = sum(1 for h in headline_scores if h["score"] > 0.1)
    bear_count  = sum(1 for h in headline_scores if h["score"] < -0.1)
    total_count = len(headline_scores)

    if normalized >= 65 and bull_count >= total_count * 0.5:
        direction  = "BUY"
        label      = "שורי חזק" if normalized >= 75 else "שורי"
        confidence = min(95, normalized)
    elif normalized <= 35 and bear_count >= total_count * 0.5:
        direction  = "SELL"
        label      = "דובי חזק" if normalized <= 25 else "דובי"
        confidence = min(95, 100 - normalized)
    else:
        direction  = "HOLD"
        label      = "ניטרלי"
        confidence = max(0, 50 - abs(normalized - 50))

    result = {
        "symbol":     symbol,
        "score":      normalized,
        "direction":  direction,
        "confidence": round(confidence, 1),
        "headlines":  headline_scores,
        "n_news":     len(headline_scores),
        "label":      label,
        "bull_count": bull_count,
        "bear_count": bear_count,
        "raw_avg":    round(raw_avg, 3),
    }
    __import__("api_cache").cache_set(f"sentiment_{symbol}", result)
    return result


def analyze_and_publish(symbol: str) -> dict:
    """
    מנתח סנטימנט וכותב לאוטובוס הסיגנלים.
    הסנטימנט הופך לעוד "קול" ב-Consensus Voting.
    """
    result = analyze_symbol(symbol)
    if result["confidence"] > 30:
        write_signal(
            source="sentiment",
            symbol=symbol,
            direction=result["direction"],
            confidence=result["confidence"],
            reason=f"סנטימנט חדשות: {result['label']} | {result['n_news']} כותרות",
            timeframe="short",
            model_type="NLP",
        )
    return result


def bulk_analyze(symbols: list, min_news: int = 2) -> list:
    """
    מנתח רשימת סימולים ומחזיר מיון לפי סנטימנט.
    """
    results = []
    for sym in symbols:
        try:
            r = analyze_and_publish(sym)
            if r["n_news"] >= min_news:
                results.append(r)
        except Exception:
            pass
    return sorted(results, key=lambda x: x["score"], reverse=True)


def render_sentiment_widget(symbol: str):
    """
    מציג ווידג'ט סנטימנט לסימול — לשימוש ב-UI.
    """
    import streamlit as st

    r = analyze_symbol(symbol)
    color = "#1b5e20" if r["direction"] == "BUY" else (
            "#b71c1c" if r["direction"] == "SELL" else "#424242")
    emoji = "🟢" if r["direction"] == "BUY" else ("🔴" if r["direction"] == "SELL" else "⚪")

    st.markdown(
        f'<div style="background:{color}22;border-right:3px solid {color};'
        f'border-radius:6px;padding:6px 12px;margin:4px 0;">'
        f'<b>{emoji} סנטימנט {symbol}: {r["label"]}</b> | '
        f'ציון: <b>{r["score"]}/100</b> | '
        f'{r["n_news"]} כותרות | '
        f'ביטחון: <b>{r["confidence"]:.0f}%</b>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if r["headlines"]:
        with st.expander(f"📰 כותרות {symbol} ({r['n_news']})", expanded=False):
            for h in r["headlines"][:5]:
                st.markdown(f"{h['label']} `{h['score']:+.2f}` — {h['title']}")


def render_sentiment_dashboard(symbols: list):
    """
    לוח סנטימנט מרכזי — לשימוש בטאב ייעודי.
    """
    import streamlit as st
    import pandas as pd

    st.markdown(
        '<div class="ai-card" style="border-right-color:#ff6f00;">'
        '<b>📊 מנוע סנטימנט חדשות — ניתוח NLP בזמן אמת</b><br>'
        f'{"TextBlob ✅" if TB_OK else "Keyword Engine ✅"} | '
        'כתיבה אוטומטית לאוטובוס הסיגנלים לכל הסוכנים.'
        '</div>',
        unsafe_allow_html=True,
    )

    if st.button("🔍 נתח סנטימנט לכל המניות", type="primary", key="sent_scan_all"):
        with st.spinner("מוריד ומנתח חדשות..."):
            results = bulk_analyze(symbols[:20])
        save("sentiment_cache", {
            "results": results,
            "updated": datetime.now().isoformat()
        })
        st.success(f"✅ נותחו {len(results)} מניות")
        st.rerun()

    cached = load("sentiment_cache", {})
    if cached.get("results"):
        updated = cached.get("updated", "")
        st.caption(f"עודכן: {updated[:16]}")
        results = cached["results"]

        bulls = [r for r in results if r["direction"] == "BUY"]
        bears = [r for r in results if r["direction"] == "SELL"]
        hold  = [r for r in results if r["direction"] == "HOLD"]

        col1, col2, col3 = st.columns(3)
        col1.metric("🟢 שוריים", len(bulls))
        col2.metric("🔴 דוביים", len(bears))
        col3.metric("⚪ ניטרליים", len(hold))

        rows = []
        for r in results:
            emoji = "🟢" if r["direction"] == "BUY" else ("🔴" if r["direction"] == "SELL" else "⚪")
            rows.append({
                "📌 סימול":    r["symbol"],
                "📊 ציון":    r["score"],
                "📈 כיוון":   f"{emoji} {r['label']}",
                "🎯 ביטחון":  f"{r['confidence']:.0f}%",
                "📰 כותרות":  r["n_news"],
                "🐂 חיוביות": r.get("bull_count", 0),
                "🐻 שליליות": r.get("bear_count", 0),
            })
        df = pd.DataFrame(rows).sort_values("📊 ציון", ascending=False)
        st.dataframe(df.reset_index(drop=True), hide_index=True)

        if bulls:
            st.markdown("#### 🟢 מניות עם סנטימנט חיובי — שולחות סיגנל BUY לסוכנים")
            for r in bulls[:5]:
                render_sentiment_widget(r["symbol"])
    else:
        st.info("לחץ 'נתח סנטימנט' כדי לסרוק את כל המניות.")
