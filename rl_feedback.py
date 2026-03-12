# rl_feedback.py — Reinforcement Learning: לימוד מעסקאות עבר
# ✅ מעקב תוצאות כל עסקה (TP/SL/ידנית)
# ✅ Win Rate לכל סימול
# ✅ מגן על הסוכנים מלקנות שוב נכסים שנפלו
# ✅ Adaptive Confidence — ניסיון אמיתי מגדיל ביטחון
from datetime import datetime, timedelta
from storage import load, save


FEEDBACK_KEY = "rl_trade_feedback"
MAX_RECORDS  = 1000


# ════════════════════════════════════════════════════════════════════════
# כתיבה
# ════════════════════════════════════════════════════════════════════════

def record_trade_outcome(
    symbol:    str,
    pnl_pct:   float,       # % רווח/הפסד בפועל
    outcome:   str,         # "TP" | "SL" | "manual_profit" | "manual_loss"
    agent:     str = "",    # "val" | "day"
    entry_price: float = 0,
    exit_price:  float = 0,
    hold_days:   int = 0,
):
    """
    רושם תוצאת עסקה לבסיס הידע.
    נקרא אוטומטית מ-_run_auto_exit ב-simulator.py
    ומ-run_val_agent / run_day_agent ב-scheduler_agents.py
    """
    records = load(FEEDBACK_KEY, [])
    records.insert(0, {
        "ts":          datetime.now().isoformat(),
        "symbol":      symbol,
        "pnl_pct":     round(pnl_pct, 2),
        "outcome":     outcome,
        "win":         pnl_pct > 0,
        "agent":       agent,
        "entry_price": round(entry_price, 4),
        "exit_price":  round(exit_price, 4),
        "hold_days":   hold_days,
    })
    save(FEEDBACK_KEY, records[:MAX_RECORDS])


# ════════════════════════════════════════════════════════════════════════
# קריאה וניתוח
# ════════════════════════════════════════════════════════════════════════

def get_symbol_stats(symbol: str, days_back: int = 180) -> dict:
    """
    מחזיר סטטיסטיקות RL לסימול: Win Rate, Avg PnL, מספר עסקאות.
    """
    records = load(FEEDBACK_KEY, [])
    cutoff  = (datetime.now() - timedelta(days=days_back)).isoformat()

    sym_records = [
        r for r in records
        if r.get("symbol") == symbol and r.get("ts", "") >= cutoff
    ]

    if not sym_records:
        return {
            "symbol":   symbol,
            "n_trades": 0,
            "win_rate": None,     # None = אין היסטוריה
            "avg_pnl":  None,
            "last_outcome": None,
        }

    wins    = sum(1 for r in sym_records if r.get("win"))
    total   = len(sym_records)
    avg_pnl = round(sum(r.get("pnl_pct", 0) for r in sym_records) / total, 2)

    return {
        "symbol":       symbol,
        "n_trades":     total,
        "win_rate":     round(wins / total * 100, 1),
        "avg_pnl":      avg_pnl,
        "last_outcome": sym_records[0].get("outcome"),
        "last_pnl":     sym_records[0].get("pnl_pct"),
    }


def should_buy(symbol: str, min_trades: int = 3,
               min_win_rate: float = 35.0) -> dict:
    """
    שאלה מרכזית: "לפי ניסיון העבר — כדאי לקנות את הסימול הזה?"
    
    החלטה:
    - אין היסטוריה → מותר (ניסיון ראשון)
    - Win Rate >= min_win_rate → מותר
    - Win Rate < min_win_rate ו-≥ min_trades → אסור + אזהרה
    - SL ברצף 2+ → ממליץ להמתין
    """
    stats = get_symbol_stats(symbol)

    if stats["n_trades"] < min_trades:
        return {
            "allowed":  True,
            "reason":   f"ניסיון ראשון — {stats['n_trades']} עסקאות בלבד",
            "stats":    stats,
            "caution":  False,
        }

    win_rate = stats["win_rate"]

    if win_rate >= min_win_rate:
        return {
            "allowed":  True,
            "reason":   f"היסטוריה טובה: {win_rate:.0f}% Win Rate ({stats['n_trades']} עסקאות)",
            "stats":    stats,
            "caution":  False,
        }

    # Win Rate נמוך — בדוק אם SL ברצף
    records   = load(FEEDBACK_KEY, [])
    sym_recs  = [r for r in records if r.get("symbol") == symbol]
    last_two  = [r.get("outcome") for r in sym_recs[:2]]
    repeat_sl = all(o == "SL" for o in last_two) if len(last_two) == 2 else False

    if repeat_sl:
        return {
            "allowed":  False,
            "reason":   f"⚠️ 2 Stop-Loss ברצף — RL חוסם קנייה ב-{symbol}",
            "stats":    stats,
            "caution":  True,
        }

    return {
        "allowed":  False,
        "reason":   f"Win Rate נמוך: {win_rate:.0f}% מתוך {stats['n_trades']} עסקאות",
        "stats":    stats,
        "caution":  True,
    }


def get_adaptive_confidence_boost(symbol: str) -> float:
    """
    מחזיר +/- להוסיף לביטחון ML על בסיס ניסיון עבר.
    
    Win Rate > 70% → +15
    Win Rate > 50% → +5
    Win Rate < 30% → -20
    Win Rate < 40% → -10
    אין היסטוריה   → 0
    """
    stats = get_symbol_stats(symbol)
    if stats["n_trades"] < 2:
        return 0.0
    wr = stats["win_rate"]
    if wr is None:
        return 0.0
    if wr >= 70:   return +15.0
    if wr >= 50:   return +5.0
    if wr < 30:    return -20.0
    if wr < 40:    return -10.0
    return 0.0


def get_all_stats(limit: int = 20) -> list:
    """מחזיר סטטיסטיקות לכל הסימולים שיש עליהם היסטוריה."""
    records = load(FEEDBACK_KEY, [])
    symbols = list({r.get("symbol") for r in records if r.get("symbol")})
    results = []
    for sym in symbols:
        s = get_symbol_stats(sym)
        if s["n_trades"] > 0:
            results.append(s)
    return sorted(results, key=lambda x: (x["win_rate"] or 0), reverse=True)[:limit]


# ════════════════════════════════════════════════════════════════════════
# UI — לוח RL
# ════════════════════════════════════════════════════════════════════════

def render_rl_dashboard():
    """לוח Reinforcement Learning — מציג מה הסוכנים למדו."""
    import streamlit as st
    import pandas as pd

    st.markdown(
        '<div class="ai-card" style="border-right-color:#7b1fa2;">'
        '<b>🧬 Reinforcement Learning — הסוכן לומד מהעבר</b><br>'
        'Win Rate לכל נכס · חסימה אוטומטית אחרי 2 SL ברצף · '
        'Adaptive Confidence.'
        '</div>',
        unsafe_allow_html=True,
    )

    records = load(FEEDBACK_KEY, [])
    if not records:
        st.info("אין היסטוריית עסקאות עדיין. הסוכנים ילמדו אחרי העסקאות הראשונות.")
        return

    # מדדים כלליים
    total  = len(records)
    wins   = sum(1 for r in records if r.get("win"))
    losses = total - wins
    avg_pnl = round(sum(r.get("pnl_pct", 0) for r in records) / total, 2) if total else 0
    best   = max(records, key=lambda r: r.get("pnl_pct", 0))
    worst  = min(records, key=lambda r: r.get("pnl_pct", 0))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📊 סה\"כ עסקאות", total)
    c2.metric("✅ ניצחונות",     wins)
    c3.metric("❌ הפסדים",       losses)
    c4.metric("📈 Win Rate",     f"{wins/total*100:.0f}%")
    c5.metric("💰 PnL ממוצע",   f"{avg_pnl:+.1f}%")

    col_b, col_w = st.columns(2)
    col_b.success(f"🏆 הטוב ביותר: **{best.get('symbol')}** +{best.get('pnl_pct', 0):.1f}%")
    col_w.error(  f"💀 הגרוע ביותר: **{worst.get('symbol')}** {worst.get('pnl_pct', 0):.1f}%")

    st.divider()

    # סטטיסטיקות לכל נכס
    st.markdown("#### 📌 Win Rate לכל נכס")
    all_stats = get_all_stats()
    if all_stats:
        rows = []
        for s in all_stats:
            wr = s.get("win_rate") or 0
            verdict = should_buy(s["symbol"])
            rows.append({
                "📌 סימול":      s["symbol"],
                "📊 עסקאות":    s["n_trades"],
                "✅ Win Rate":  f"{wr:.0f}%",
                "💰 Avg PnL":  f"{s['avg_pnl']:+.1f}%",
                "📈 מגמה":      "📈 Bar " + "█" * max(1, int(wr / 10)) + "░" * (10 - max(1, int(wr / 10))),
                "🤖 RL":        "✅ מותר" if verdict["allowed"] else "🚫 חסום",
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True)

    st.divider()

    # היסטוריית עסקאות
    st.markdown("#### 📋 50 עסקאות אחרונות")
    show = []
    for r in records[:50]:
        show.append({
            "⏰ תאריך":     r.get("ts", "")[:16],
            "📌 סימול":    r.get("symbol"),
            "↔️ תוצאה":   r.get("outcome"),
            "💰 P&L%":     f"{r.get('pnl_pct', 0):+.1f}%",
            "🤖 סוכן":     r.get("agent"),
            "📊 סיווג":   "🟢 ניצחון" if r.get("win") else "🔴 הפסד",
        })
    st.dataframe(pd.DataFrame(show), hide_index=True)

    if st.button("🗑️ נקה היסטוריית RL", key="rl_clear"):
        save(FEEDBACK_KEY, [])
        st.success("✅ היסטוריה נוקתה")
        st.rerun()
