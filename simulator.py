# simulator.py — Value Agent + Day Trade Agent with real storage, live prices & ML signals
import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
from storage import load, save
from shared_signals import get_consensus, get_top_buys, write_signal, render_shared_signals


# ─── Portfolio key normalizer (handles legacy keys from old scheduler) ─────────
def _norm(positions: list) -> list:
    """Convert any portfolio format to canonical {Symbol, BuyPrice, Qty, ...}."""
    out = []
    for p in positions:
        if not isinstance(p, dict):
            continue
        sym = p.get("Symbol") or p.get("Stock") or p.get("📌") or ""
        if not sym:
            continue
        out.append({
            "Symbol":   sym,
            "BuyPrice": float(p.get("BuyPrice") or p.get("Price") or 0),
            "Qty":      float(p.get("Qty") or p.get("Quantity") or p.get("Shares") or 0),
            "BuyDate":  p.get("BuyDate", ""),
            "Score":    p.get("Score", 0),
            "Type":     p.get("Type", _asset_label(sym)),
        })
    return out

# ─── Live price helper ────────────────────────────────────────────────────────
@st.cache_data(ttl=300)  # 5 דקות — מחיר חי לא צריך להתעדכן יותר מכך
def _live(symbol: str, fallback: float = 0.0) -> float:
    try:
        h = yf.Ticker(symbol).history(period="1d", interval="1m")
        if not h.empty:
            return float(h["Close"].iloc[-1])
        h = yf.Ticker(symbol).history(period="2d")
        if not h.empty:
            return float(h["Close"].iloc[-1])
    except Exception:
        pass
    return fallback


def _port_value(portfolio: list) -> float:
    total = 0.0
    for p in portfolio:
        try:
            lp = _live(p["Symbol"], p.get("BuyPrice", 0))
            total += lp * float(p.get("Qty", 0))
        except Exception:
            pass
    return total


def _asset_label(symbol: str) -> str:
    if symbol.endswith(".TA"):  return "📈 תא\"ב"
    if "-USD" in symbol:        return "₿ קריפטו"
    if symbol in ("XLE","USO","GLD","SLV","UNG"): return "⛽ אנרגיה"
    return "🇺🇸 ארה\"ב"


# ═══════════════════════════════════════════════════════════════════════════════
# VALUE AGENT
# ═══════════════════════════════════════════════════════════════════════════════
def render_value_agent(df_all: pd.DataFrame):
    """Long-term value investing agent — uses Score, CashVsDebt, RSI from df_all."""
    st.markdown(
        '<div class="ai-card" style="border-right-color:#1976d2;">'
        '<b>💎 סוכן ערך — השקעה לטווח ארוך</b><br>'
        'קונה מניות איכותיות (ציון ≥4) ומוכר ב-+20% רווח / -10% סטופ.'
        '</div>',
        unsafe_allow_html=True,
    )

    if df_all is None or df_all.empty:
        st.warning("⏳ אין נתוני מניות — ממתין לסריקה.")
        return

    # ── State ──────────────────────────────────────────────────────────────
    portfolio = _norm(load("val_portfolio", []))
    cash      = float(load("val_cash_ils", 100000.0))
    trades    = load("val_trades_log", [])
    initial   = float(load("val_initial", 100000.0))

    pv    = _port_value(portfolio)
    total = cash + pv
    pnl   = total - initial

    # ── Metrics ────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💵 מזומן",     f"₪{cash:,.0f}")
    c2.metric("📈 שווי תיק",  f"₪{pv:,.0f}")
    c3.metric("🏦 סה\"כ",     f"₪{total:,.0f}")
    c4.metric("📊 רווח/הפסד", f"{'🟢+' if pnl>=0 else '🔴'}₪{abs(pnl):,.0f}",
              delta=f"{(pnl/initial*100):+.1f}%" if initial else "")

    # ── ML Signal Panel ───────────────────────────────────────────────────
    try:
        ml_buys = get_top_buys(timeframe="long", min_confidence=60, hours_back=48, limit=5)
        if ml_buys:
            ml_syms = [x["symbol"] for x in ml_buys]
            st.info(
                f"🧠 **ML ממליץ (ערך, 48ש):** {', '.join(ml_syms)} "
                f"| ביטחון ממוצע: {ml_buys[0]['avg_conf']:.0f}%"
            )
    except Exception:
        ml_buys = []

    # ── Candidates ────────────────────────────────────────────────────────
    needed = [c for c in ["Score","RSI","CashVsDebt","DivYield","Margin"] if c in df_all.columns]
    cands = df_all.copy()
    if "Score" in cands.columns:
        cands = cands[cands["Score"] >= 4]
    if "RSI" in cands.columns:
        cands = cands[(cands["RSI"] > 25) & (cands["RSI"] < 70)]
    if "CashVsDebt" in cands.columns:
        cands = cands[cands["CashVsDebt"] == "✅"]

    # בונוס ציון למניות שה-ML ממליץ עליהן
    try:
        if ml_buys and "Symbol" in cands.columns and "Score" in cands.columns:
            ml_sym_set = {x["symbol"] for x in ml_buys}
            cands = cands.copy()
            cands.loc[cands["Symbol"].isin(ml_sym_set), "Score"] += 1
    except Exception:
        pass

    cands = cands.nlargest(10, "Score") if "Score" in cands.columns else cands.head(10)

    show_cols = [c for c in ["Symbol","Price","Score","RSI","DivYield","Margin","CashVsDebt","Action"] if c in cands.columns]
    if not cands.empty:
        st.markdown("#### 🔍 מניות מומלצות לרכישה (ציון ≥4, מאזן חזק + ML)")
        st.dataframe(cands[show_cols].reset_index(drop=True), hide_index=True)
    else:
        st.info("אין מניות עם ציון ≥4 ומאזן חזק כרגע.")

    # ── Buttons ───────────────────────────────────────────────────────────
    b1, b2, b3 = st.columns(3)

    with b1:
        if st.button("🚀 קנה אוטומטי", key="val_buy", type="primary"):
            if cands.empty:
                st.error("אין מניות מתאימות.")
            elif cash < 100:
                st.warning("אין מזומן מספיק.")
            else:
                existing = {p["Symbol"] for p in portfolio}
                bought = 0
                for _, row in cands.iterrows():
                    sym = row["Symbol"]
                    if sym in existing or len(portfolio) >= 10:
                        continue
                    lp = _live(sym, float(row.get("Price", 0)))
                    if lp <= 0:
                        continue
                    alloc = cash * 0.15
                    qty   = alloc / lp
                    portfolio.append({
                        "Symbol": sym, "BuyPrice": round(lp, 4),
                        "Qty": round(qty, 4), "BuyDate": datetime.now().isoformat(),
                        "Score": int(row.get("Score", 0)),
                        "Type": _asset_label(sym),
                    })
                    cash -= alloc
                    existing.add(sym)
                    trades.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": "קנייה", "💰": f"{lp:.3f}",
                        "📊": f"ציון {int(row.get('Score',0))}/6",
                        "🏷️": _asset_label(sym),
                    })
                    bought += 1
                save("val_portfolio", portfolio)
                save("val_cash_ils", round(cash, 2))
                save("val_trades_log", trades[:200])
                st.success(f"✅ נקנו {bought} נכסים!")
                st.rerun()

    with b2:
        if portfolio and st.button("💸 מכור הכל", key="val_sell"):
            proceeds = 0.0
            for p in portfolio:
                lp = _live(p["Symbol"], p.get("BuyPrice", 0))
                profit = ((lp / p["BuyPrice"]) - 1) * 100 if p["BuyPrice"] else 0
                proceeds += lp * p["Qty"]
                trades.insert(0, {
                    "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "📌": p["Symbol"], "↔️": "מכירה",
                    "💰": f"{lp:.3f}", "📊": f"{profit:+.1f}%",
                    "🏷️": p.get("Type", ""),
                })
            cash += proceeds
            portfolio = []
            save("val_portfolio", portfolio)
            save("val_cash_ils", round(cash, 2))
            save("val_trades_log", trades[:200])
            st.success(f"✅ מכרנו הכל! ₪{proceeds:,.0f} חזרו למזומן.")
            st.rerun()

    with b3:
        if st.button("🔄 איפוס", key="val_reset"):
            save("val_portfolio", [])
            save("val_cash_ils", 100000.0)
            save("val_initial", 100000.0)
            save("val_trades_log", [])
            st.success("✅ אופס!")
            st.rerun()

    # ── Portfolio table ───────────────────────────────────────────────────
    if portfolio:
        st.markdown("#### 💼 תיק פעיל")
        rows = []
        for p in portfolio:
            lp     = _live(p["Symbol"], p["BuyPrice"])
            profit = ((lp / p["BuyPrice"]) - 1) * 100 if p["BuyPrice"] else 0
            rows.append({
                "📌 סימול": p["Symbol"],
                "🏷️ סוג":  p.get("Type", ""),
                "💵 כניסה": f"{p['BuyPrice']:.3f}",
                "💰 עכשיו": f"{lp:.3f}",
                "📊 רווח%": f"{'🟢+' if profit>=0 else '🔴'}{abs(profit):.1f}%",
                "📦 כמות":  f"{p['Qty']:.4f}",
                "💎 ציון":  p.get("Score", "—"),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True)

    # ── Trade log ─────────────────────────────────────────────────────────
    if trades:
        st.markdown("#### 📋 יומן עסקאות")
        df_trades = pd.DataFrame(trades[:20])
        st.dataframe(df_trades, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# DAY TRADE AGENT
# ═══════════════════════════════════════════════════════════════════════════════
def render_day_trade_agent(df_all: pd.DataFrame):
    """Intraday agent — RSI dip buying, closes at ±2%."""
    st.markdown(
        '<div class="ai-card" style="border-right-color:#e65100;">'
        '<b>⚡ סוכן יומי — מסחר תוך-יומי</b><br>'
        'קונה בדיפ (RSI&lt;40) וסוגר ב-±2%. מכסה מניות, קריפטו, אנרגיה ותא"ב.'
        '</div>',
        unsafe_allow_html=True,
    )

    if df_all is None or df_all.empty:
        st.warning("⏳ אין נתוני מניות — ממתין לסריקה.")
        return

    # ── State ──────────────────────────────────────────────────────────────
    portfolio = _norm(load("day_portfolio", []))
    cash      = float(load("day_cash_ils", 100000.0))
    trades    = load("day_trades_log", [])
    initial   = float(load("day_initial", 100000.0))

    pv    = _port_value(portfolio)
    total = cash + pv
    pnl   = total - initial

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💵 מזומן",     f"₪{cash:,.0f}")
    c2.metric("📈 שווי תיק",  f"₪{pv:,.0f}")
    c3.metric("🏦 סה\"כ",     f"₪{total:,.0f}")
    c4.metric("📊 רווח/הפסד", f"{'🟢+' if pnl>=0 else '🔴'}₪{abs(pnl):,.0f}",
              delta=f"{(pnl/initial*100):+.1f}%" if initial else "")

    # ── ML Signal Panel (יומי) ─────────────────────────────────────────────
    try:
        ml_day_buys = get_top_buys(timeframe="short", min_confidence=55, hours_back=24, limit=5)
        if ml_day_buys:
            ml_d_syms = [x["symbol"] for x in ml_day_buys]
            st.success(
                f"🧠 **ML יומי ממליץ (24ש):** {', '.join(ml_d_syms)} "
                f"| ביטחון: {ml_day_buys[0]['avg_conf']:.0f}%"
            )
        else:
            ml_day_buys = []
    except Exception:
        ml_day_buys = []

    # ── Signals ───────────────────────────────────────────────────────────
    day_cands = df_all.copy()
    if "RSI" in day_cands.columns:
        day_cands = day_cands[day_cands["RSI"] < 42]
    if "Score" in day_cands.columns:
        day_cands = day_cands[day_cands["Score"] >= 2]

    # בונוס ציון למניות שה-ML יומי ממליץ עליהן
    try:
        if ml_day_buys and "Symbol" in day_cands.columns and "Score" in day_cands.columns:
            ml_d_set = {x["symbol"] for x in ml_day_buys}
            day_cands = day_cands.copy()
            day_cands.loc[day_cands["Symbol"].isin(ml_d_set), "Score"] += 2
    except Exception:
        pass

    day_cands = day_cands.nlargest(10, "Score") if "Score" in day_cands.columns else day_cands.head(10)

    show_cols = [c for c in ["Symbol","Price","RSI","Score","ret_5d","Change","Action"] if c in day_cands.columns]
    if not day_cands.empty:
        st.markdown("#### 📡 סיגנלים יומיים (RSI<42, ציון≥2, ML יומי)")
        st.dataframe(day_cands[show_cols].reset_index(drop=True), hide_index=True)
    else:
        st.info("אין סיגנלי קנייה יומיים כרגע — RSI גבוה מדי.")

    # ── Buttons ───────────────────────────────────────────────────────────
    b1, b2, b3, b4 = st.columns(4)

    with b1:
        if st.button("🚀 קנה יומי", key="day_buy", type="primary"):
            if day_cands.empty:
                st.error("אין סיגנלים.")
            elif cash < 100:
                st.warning("אין מזומן.")
            else:
                existing = {p["Symbol"] for p in portfolio}
                bought = 0
                for _, row in day_cands.iterrows():
                    sym = row["Symbol"]
                    if sym in existing or len(portfolio) >= 5:
                        continue
                    lp = _live(sym, float(row.get("Price", 0)))
                    if lp <= 0:
                        continue
                    alloc = min(cash * 0.25, cash)
                    qty   = alloc / lp
                    portfolio.append({
                        "Symbol": sym, "BuyPrice": round(lp, 4),
                        "Qty": round(qty, 4), "BuyDate": datetime.now().isoformat(),
                        "Type": _asset_label(sym),
                    })
                    cash -= alloc
                    existing.add(sym)
                    trades.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": "קנייה-יומי",
                        "💰": f"{lp:.3f}", "📊": f"RSI {row.get('RSI',0):.0f}",
                        "🏷️": _asset_label(sym),
                    })
                    bought += 1
                save("day_portfolio", portfolio)
                save("day_cash_ils", round(cash, 2))
                save("day_trades_log", trades[:300])
                st.success(f"✅ נקנו {bought} פוזיציות יומיות!")
                st.rerun()

    with b2:
        if portfolio and st.button("💸 סגור הכל", key="day_close"):
            proceeds = 0.0
            for p in portfolio:
                lp = _live(p["Symbol"], p.get("BuyPrice", 0))
                profit = ((lp / p["BuyPrice"]) - 1) * 100 if p["BuyPrice"] else 0
                proceeds += lp * p["Qty"]
                trades.insert(0, {
                    "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "📌": p["Symbol"], "↔️": "סגירה-יומי",
                    "💰": f"{lp:.3f}", "📊": f"{profit:+.1f}%",
                    "🏷️": p.get("Type", ""),
                })
            cash += proceeds
            portfolio = []
            save("day_portfolio", portfolio)
            save("day_cash_ils", round(cash, 2))
            save("day_trades_log", trades[:300])
            st.success(f"✅ סגורו הכל! ₪{proceeds:,.0f}")
            st.rerun()

    with b3:
        if st.button("⚡ סגור רווחים", key="day_tp"):
            new_port, released = [], 0.0
            for p in portfolio:
                lp = _live(p["Symbol"], p.get("BuyPrice", 0))
                profit = ((lp / p["BuyPrice"]) - 1) * 100 if p["BuyPrice"] else 0
                if profit >= 2:
                    released += lp * p["Qty"]
                    trades.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": p["Symbol"], "↔️": "Take-Profit",
                        "💰": f"{lp:.3f}", "📊": f"+{profit:.1f}%",
                        "🏷️": p.get("Type", ""),
                    })
                elif profit <= -2:
                    released += lp * p["Qty"]
                    trades.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": p["Symbol"], "↔️": "Stop-Loss",
                        "💰": f"{lp:.3f}", "📊": f"{profit:.1f}%",
                        "🏷️": p.get("Type", ""),
                    })
                else:
                    new_port.append(p)
            cash += released
            portfolio = new_port
            save("day_portfolio", portfolio)
            save("day_cash_ils", round(cash, 2))
            save("day_trades_log", trades[:300])
            st.success(f"✅ סגורו פוזיציות ב-±2%. שוחרר: ₪{released:,.0f}")
            st.rerun()

    with b4:
        if st.button("🔄 איפוס", key="day_reset"):
            save("day_portfolio", [])
            save("day_cash_ils", 100000.0)
            save("day_initial", 100000.0)
            save("day_trades_log", [])
            st.success("✅ אופס!")
            st.rerun()

    # ── Portfolio ─────────────────────────────────────────────────────────
    if portfolio:
        st.markdown("#### ⚡ פוזיציות פתוחות")
        rows = []
        for p in portfolio:
            lp     = _live(p["Symbol"], p["BuyPrice"])
            profit = ((lp / p["BuyPrice"]) - 1) * 100 if p["BuyPrice"] else 0
            rows.append({
                "📌 סימול": p["Symbol"],
                "🏷️ סוג":  p.get("Type", ""),
                "💵 כניסה": f"{p['BuyPrice']:.3f}",
                "💰 עכשיו": f"{lp:.3f}",
                "📊 P&L%":  f"{'🟢+' if profit>=0 else '🔴'}{abs(profit):.1f}%",
                "📦 כמות":  f"{p['Qty']:.4f}",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True)

    # ── Trades ────────────────────────────────────────────────────────────
    if trades:
        st.markdown("#### 📋 עסקאות יומיות")
        st.dataframe(pd.DataFrame(trades[:30]), hide_index=True)


def run_simulator():
    st.markdown("## Trading Simulator")
    st.info("השתמש בלשוניות 'סוכן ערך' ו'סוכן יומי' למסחר אינטראקטיבי.")
