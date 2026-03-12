# simulator.py — Value Agent + Day Trade Agent
# ✅ Stop-Loss / Take-Profit אוטומטי
# ✅ Market Regime Filter (VIX + SPY MA50)
# ✅ ML signals integration
import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
from storage import load, save
from shared_signals import get_top_buys
from rl_feedback import record_trade_outcome, should_buy, get_adaptive_confidence_boost
from sector_diversifier import can_buy_sector, render_sector_breakdown


# ════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════

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


@st.cache_data(ttl=300)
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
    return sum(_live(p["Symbol"], p.get("BuyPrice", 0)) * float(p.get("Qty", 0))
               for p in portfolio)


def _asset_label(symbol: str) -> str:
    if symbol.endswith(".TA"):            return "📈 תא\"ב"
    if "-USD" in symbol:                  return "₿ קריפטו"
    if symbol in ("XLE","USO","GLD","SLV","UNG"): return "⛽ אנרגיה"
    return "🇺🇸 ארה\"ב"


# ════════════════════════════════════════════════════════════════════════
# 🌡️ MARKET REGIME DETECTOR
# ════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600)
def get_market_regime() -> dict:
    """
    מחזיר מצב שוק נוכחי לפי VIX + SPY ביחס ל-MA50.
    regime: "bull" | "neutral" | "bear"
    """
    try:
        vix = float(yf.Ticker("^VIX").history(period="2d")["Close"].iloc[-1])
    except Exception:
        vix = 20.0

    try:
        spy_hist = yf.Ticker("SPY").history(period="3mo")
        spy      = float(spy_hist["Close"].iloc[-1])
        ma50     = float(spy_hist["Close"].rolling(50).mean().iloc[-1])
        spy_above_ma50 = spy > ma50
    except Exception:
        spy_above_ma50 = True

    if vix > 30 or not spy_above_ma50:
        regime = "bear"
        emoji  = "🔴"
        label  = "שוק דובי — הגנתי"
        color  = "#b71c1c"
    elif vix > 20:
        regime = "neutral"
        emoji  = "🟡"
        label  = "שוק ניטרלי — זהירות"
        color  = "#f57f17"
    else:
        regime = "bull"
        emoji  = "🟢"
        label  = "שוק שורי — קנייה"
        color  = "#1b5e20"

    return {
        "regime": regime, "emoji": emoji, "label": label,
        "color": color, "vix": round(vix, 1),
        "spy_above_ma50": spy_above_ma50,
    }


def _regime_banner():
    """מציג באנר מצב שוק בראש הסוכן."""
    r = get_market_regime()
    st.markdown(
        f'<div style="background:{r["color"]}22;border-right:4px solid {r["color"]};'
        f'border-radius:8px;padding:8px 14px;margin-bottom:10px;">'
        f'<b>{r["emoji"]} מצב שוק: {r["label"]}</b> &nbsp;|&nbsp; '
        f'VIX: <b>{r["vix"]}</b> &nbsp;|&nbsp; '
        f'SPY/MA50: <b>{"✅ מעל" if r["spy_above_ma50"] else "❌ מתחת"}</b>'
        f'</div>',
        unsafe_allow_html=True,
    )
    return r


# ════════════════════════════════════════════════════════════════════════
# 🛡️ AUTO EXIT — Stop-Loss & Take-Profit
# ════════════════════════════════════════════════════════════════════════

def _run_auto_exit(portfolio: list, cash: float, trades: list,
                   tp_pct: float, sl_pct: float, label_suffix: str = "") -> tuple:
    """
    עובר על כל הפוזיציות ומוכר אוטומטית אם הגיעו ל-TP או Trailing-SL.
    Trailing SL: SL מחושב מהשיא ההיסטורי (TrailingHigh) — לא מהקנייה.
    מחזיר (portfolio_new, cash_new, trades_new, sold_count, report)
    """
    new_port = []
    sold     = 0
    report   = []

    for p in portfolio:
        lp = _live(p["Symbol"], p.get("BuyPrice", 0))
        bp = float(p.get("BuyPrice", lp))
        if bp <= 0:
            new_port.append(p); continue

        # ── Trailing High — מעדכן שיא רץ ──────────────────────────────
        trail_high = float(p.get("TrailingHigh", bp))
        if lp > trail_high:
            trail_high = lp
            p = {**p, "TrailingHigh": round(trail_high, 4)}

        pnl_pct        = ((lp / bp) - 1) * 100
        trail_sl_price = trail_high * (1 - sl_pct / 100)   # SL מהשיא
        trail_drawdown = ((lp / trail_high) - 1) * 100     # ירידה מהשיא

        if pnl_pct >= tp_pct:
            qty = float(p.get("Qty", 0))
            cash += lp * qty
            trades.insert(0, {
                "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "📌": p["Symbol"], "↔️": f"🎯 Take-Profit {label_suffix}",
                "💰": f"{lp:.3f}", "📊": f"+{pnl_pct:.1f}%",
                "🏷️": p.get("Type", ""),
            })
            report.append(f"✅ {p['Symbol']} +{pnl_pct:.1f}% (TP)")
            record_trade_outcome(
                symbol=p["Symbol"], pnl_pct=pnl_pct, outcome="TP",
                agent=label_suffix.strip(), entry_price=bp, exit_price=lp,
            )
            sold += 1

        elif lp <= trail_sl_price:
            # Trailing SL — ירד יותר מ-sl_pct% מהשיא
            qty = float(p.get("Qty", 0))
            cash += lp * qty
            trades.insert(0, {
                "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "📌": p["Symbol"],
                "↔️": f"🛑 Trailing-SL {label_suffix}",
                "💰": f"{lp:.3f}",
                "📊": f"{pnl_pct:.1f}% | ↘️{trail_drawdown:.1f}% מהשיא {trail_high:.3f}",
                "🏷️": p.get("Type", ""),
            })
            report.append(f"🛑 {p['Symbol']} {pnl_pct:.1f}% (Trailing-SL מ-{trail_high:.2f})")
            record_trade_outcome(
                symbol=p["Symbol"], pnl_pct=pnl_pct, outcome="SL",
                agent=label_suffix.strip(), entry_price=bp, exit_price=lp,
            )
            sold += 1

        else:
            new_port.append(p)

    return new_port, cash, trades, sold, report


# ════════════════════════════════════════════════════════════════════════
# 🔁 PORTFOLIO REBALANCER — מוכר חלק כשפוזיציה חורגת ממשקל מקסימלי
# ════════════════════════════════════════════════════════════════════════
def _run_rebalance(portfolio: list, cash: float, trades: list,
                   max_weight_pct: float, label_suffix: str = "") -> tuple:
    """
    בודק כל פוזיציה: אם ערכה > max_weight_pct% מסך התיק — מוכר עודף.
    מחזיר (portfolio_new, cash_new, trades_new, rebalanced_count, report)
    """
    if not portfolio:
        return portfolio, cash, trades, 0, []

    positions_value = sum(_live(p["Symbol"], p.get("BuyPrice", 0)) * float(p.get("Qty", 0))
                          for p in portfolio)
    total_value = positions_value + cash
    if total_value <= 0:
        return portfolio, cash, trades, 0, []

    target_value = total_value * (max_weight_pct / 100)
    new_port     = []
    rebalanced   = 0
    report       = []

    for p in portfolio:
        lp  = _live(p["Symbol"], p.get("BuyPrice", 0))
        qty = float(p.get("Qty", 0))
        pos_value = lp * qty
        weight    = pos_value / total_value * 100

        if weight > max_weight_pct and lp > 0 and qty > 0:
            # מוכר רק את העודף — נשאר עם target_value בפוזיציה
            sell_value = pos_value - target_value
            sell_qty   = sell_value / lp
            new_qty    = qty - sell_qty
            pnl_pct    = ((lp / float(p.get("BuyPrice", lp))) - 1) * 100

            cash += sell_value
            trades.insert(0, {
                "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "📌": p["Symbol"],
                "↔️": f"🔁 Rebalance {label_suffix}",
                "💰": f"{lp:.3f}",
                "📊": f"⚖️ {weight:.0f}%→{max_weight_pct:.0f}% | מכירת {sell_qty:.3f} יח'",
                "🏷️": p.get("Type", ""),
            })
            report.append(f"🔁 {p['Symbol']} {weight:.0f}%→{max_weight_pct:.0f}%")
            rebalanced += 1

            if new_qty > 0.0001:
                new_p = {**p, "Qty": round(new_qty, 4)}
                new_port.append(new_p)
        else:
            new_port.append(p)

    return new_port, cash, trades, rebalanced, report


# ════════════════════════════════════════════════════════════════════════
# 💎 VALUE AGENT
# ════════════════════════════════════════════════════════════════════════

def render_value_agent(df_all: pd.DataFrame):
    st.markdown(
        '<div class="ai-card" style="border-right-color:#1976d2;">'
        '<b>💎 סוכן ערך — השקעה לטווח ארוך</b><br>'
        'קונה מניות איכותיות (ציון ≥4). יוצא אוטומטית לפי TP/SL שהגדרת. '
        'מושבת בשוק דובי.'
        '</div>',
        unsafe_allow_html=True,
    )

    if df_all is None or df_all.empty:
        st.warning("⏳ אין נתוני מניות — ממתין לסריקה.")
        return

    # ── מצב שוק ────────────────────────────────────────────────────────
    regime = _regime_banner()

    # ── State ────────────────────────────────────────────────────────────
    portfolio = _norm(load("val_portfolio", []))
    cash      = float(load("val_cash_ils", 100000.0))
    trades    = load("val_trades_log", [])
    initial   = float(load("val_initial", 100000.0))

    # ── הגדרות Stop-Loss / Take-Profit ──────────────────────────────────
    with st.expander("⚙️ הגדרות Stop-Loss / Take-Profit / Rebalance", expanded=False):
        col_tp, col_sl, col_rb = st.columns(3)
        val_tp = col_tp.slider("🎯 Take-Profit %",     5, 50, 20, 1, key="val_tp_pct",
                               help="מוכר כשהרווח מגיע לאחוז זה")
        val_sl = col_sl.slider("🛑 Trailing Stop %",   3, 25, 10, 1, key="val_sl_pct",
                               help="מוכר כשירידה מהשיא מגיעה לאחוז זה")
        val_rb = col_rb.slider("🔁 Rebalance מקס %",  15, 50, 30, 5, key="val_rebalance_pct",
                               help="מוכר עודף כשפוזיציה חורגת ממשקל זה בתיק")
        save("val_tp_pct", val_tp)
        save("val_sl_pct", val_sl)
        save("val_rebalance_pct", val_rb)

    # ── Auto Exit — רץ בכל טעינת עמוד ──────────────────────────────────
    if portfolio:
        portfolio, cash, trades, auto_sold, auto_report = _run_auto_exit(
            portfolio, cash, trades, val_tp, val_sl, "ערך"
        )
        portfolio, cash, trades, rb_count, rb_report = _run_rebalance(
            portfolio, cash, trades, val_rb, "ערך"
        )
        all_actions = auto_report + rb_report
        if auto_sold > 0 or rb_count > 0:
            save("val_portfolio", portfolio)
            save("val_cash_ils", round(cash, 2))
            save("val_trades_log", trades[:200])
            if all_actions:
                st.toast(f"🤖 {', '.join(all_actions)}", icon="🔔")

    pv    = _port_value(portfolio)
    total = cash + pv
    pnl   = total - initial

    # ── Metrics ──────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("💵 מזומן",       f"₪{cash:,.0f}")
    c2.metric("📈 שווי תיק",    f"₪{pv:,.0f}")
    c3.metric("🏦 סה\"כ",       f"₪{total:,.0f}")
    c4.metric("📊 רווח/הפסד",   f"{'🟢+' if pnl>=0 else '🔴'}₪{abs(pnl):,.0f}",
              delta=f"{(pnl/initial*100):+.1f}%" if initial else "")
    c5.metric("🎯 TP/SL",       f"+{val_tp}% / -{val_sl}%")

    # ── ML Signals ───────────────────────────────────────────────────────
    try:
        ml_buys = get_top_buys(timeframe="long", min_confidence=60, hours_back=48, limit=5)
        if ml_buys:
            ml_syms = [x["symbol"] for x in ml_buys]
            st.info(f"🧠 **ML ממליץ (ערך):** {', '.join(ml_syms)}")
    except Exception:
        ml_buys = []

    # ── Candidates ───────────────────────────────────────────────────────
    cands = df_all.copy()
    if "Score" in cands.columns:      cands = cands[cands["Score"] >= 4]
    if "RSI" in cands.columns:        cands = cands[(cands["RSI"] > 25) & (cands["RSI"] < 70)]
    if "CashVsDebt" in cands.columns: cands = cands[cands["CashVsDebt"] == "✅"]

    try:
        if ml_buys and "Symbol" in cands.columns:
            ml_set = {x["symbol"] for x in ml_buys}
            cands  = cands.copy()
            cands.loc[cands["Symbol"].isin(ml_set), "Score"] += 1
    except Exception:
        pass

    cands = cands.nlargest(10, "Score") if "Score" in cands.columns else cands.head(10)

    show_cols = [c for c in ["Symbol","Price","Score","RSI","DivYield","Margin","CashVsDebt","Action"]
                 if c in cands.columns]
    if not cands.empty:
        st.markdown("#### 🔍 מניות מומלצות (ציון ≥4, מאזן חזק + ML)")
        st.dataframe(cands[show_cols].reset_index(drop=True), hide_index=True)
    else:
        st.info("אין מניות עם ציון ≥4 ומאזן חזק כרגע.")

    # ── Buttons ──────────────────────────────────────────────────────────
    b1, b2, b3, b4 = st.columns(4)

    with b1:
        buy_disabled = (regime["regime"] == "bear")
        if st.button("🚀 קנה אוטומטי", key="val_buy", type="primary",
                     disabled=buy_disabled,
                     help="מושבת בשוק דובי (VIX>30 או SPY מתחת MA50)"):
            if cands.empty:
                st.error("אין מניות מתאימות.")
            elif cash < 100:
                st.warning("אין מזומן מספיק.")
            else:
                existing = {p["Symbol"] for p in portfolio}
                alloc_pct = 0.12 if regime["regime"] == "neutral" else 0.15
                bought  = 0
                skipped = []
                for _, row in cands.iterrows():
                    sym = row["Symbol"]
                    if sym in existing or len(portfolio) >= 10: continue
                    lp  = _live(sym, float(row.get("Price", 0)))
                    if lp <= 0: continue

                    # 🗂️ Sector Diversification — לא יותר מ-2 מאותו סקטור
                    sec_chk = can_buy_sector(sym, portfolio, max_per_sector=2)
                    if not sec_chk["allowed"]:
                        skipped.append(f"{sym} ({sec_chk['reason']})")
                        continue

                    # 🧬 RL Check — מניעת קנייה חוזרת אחרי 2 SL ברצף
                    rl = should_buy(sym, min_trades=3, min_win_rate=35.0)
                    if not rl["allowed"]:
                        skipped.append(f"{sym} ({rl['reason']})")
                        continue

                    # Adaptive confidence boost מניסיון עבר
                    boost    = get_adaptive_confidence_boost(sym)
                    alloc    = cash * alloc_pct * (1 + boost / 100)
                    alloc    = min(alloc, cash * 0.20)
                    qty      = alloc / lp
                    portfolio.append({
                        "Symbol": sym, "BuyPrice": round(lp, 4),
                        "TrailingHigh": round(lp, 4),
                        "Qty": round(qty, 4), "BuyDate": datetime.now().isoformat(),
                        "Score": int(row.get("Score", 0)), "Type": _asset_label(sym),
                    })
                    cash -= alloc
                    existing.add(sym)
                    trades.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": "קנייה",
                        "💰": f"{lp:.3f}",
                        "📊": f"ציון {int(row.get('Score',0))}/6 | {regime['emoji']} | RL+{boost:+.0f}",
                        "🏷️": _asset_label(sym),
                    })
                    bought += 1
                save("val_portfolio", portfolio)
                save("val_cash_ils", round(cash, 2))
                save("val_trades_log", trades[:200])
                msg = f"✅ נקנו {bought} נכסים! TP +{val_tp}% / SL -{val_sl}%"
                if skipped:
                    msg += f"\n⚠️ RL חסם: {', '.join(skipped[:3])}"
                st.success(msg)
                st.rerun()

        if buy_disabled:
            st.caption("🔴 קנייה מושבתת — שוק דובי")

    with b2:
        if st.button("🔁 בדוק TP/SL עכשיו", key="val_check_exit"):
            portfolio, cash, trades, sold, report = _run_auto_exit(
                portfolio, cash, trades, val_tp, val_sl, "ערך"
            )
            save("val_portfolio", portfolio)
            save("val_cash_ils", round(cash, 2))
            save("val_trades_log", trades[:200])
            if sold:
                st.success(f"✅ {sold} פוזיציות נסגרו:\n" + "\n".join(report))
            else:
                st.info("אין פוזיציות שהגיעו ל-TP/SL כרגע.")
            st.rerun()

    with b3:
        if portfolio and st.button("💸 מכור הכל", key="val_sell"):
            proceeds = 0.0
            for p in portfolio:
                lp     = _live(p["Symbol"], p.get("BuyPrice", 0))
                profit = ((lp / p["BuyPrice"]) - 1) * 100 if p["BuyPrice"] else 0
                proceeds += lp * p["Qty"]
                trades.insert(0, {
                    "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "📌": p["Symbol"], "↔️": "מכירה-ידנית",
                    "💰": f"{lp:.3f}", "📊": f"{profit:+.1f}%",
                    "🏷️": p.get("Type", ""),
                })
            cash += proceeds
            portfolio = []
            save("val_portfolio", portfolio)
            save("val_cash_ils", round(cash, 2))
            save("val_trades_log", trades[:200])
            st.success(f"✅ מכרנו הכל! ₪{proceeds:,.0f}")
            st.rerun()

    with b4:
        if st.button("🔄 איפוס", key="val_reset"):
            save("val_portfolio", [])
            save("val_cash_ils", 100000.0)
            save("val_initial", 100000.0)
            save("val_trades_log", [])
            st.success("✅ אופס!")
            st.rerun()

    # ── Sector Breakdown ─────────────────────────────────────────────────
    if portfolio:
        with st.expander("🗂️ גיוון סקטוריאלי בתיק", expanded=False):
            render_sector_breakdown(portfolio)

    # ── Portfolio table עם TP/SL progress ───────────────────────────────
    if portfolio:
        st.markdown("#### 💼 תיק פעיל")
        rows = []
        for p in portfolio:
            lp      = _live(p["Symbol"], p["BuyPrice"])
            bp      = float(p["BuyPrice"])
            profit  = ((lp / bp) - 1) * 100 if bp else 0
            to_tp   = val_tp  - profit
            to_sl   = profit  + val_sl
            # ProgressBar בתוך הטבלה (emoji based)
            bar_len   = 10
            filled    = max(0, min(bar_len, int((profit + val_sl) / (val_tp + val_sl) * bar_len)))
            bar       = "█" * filled + "░" * (bar_len - filled)
            trail_high = float(p.get("TrailingHigh", bp))
            from_peak  = ((lp / trail_high) - 1) * 100 if trail_high else 0
            rows.append({
                "📌 סימול":   p["Symbol"],
                "🏷️ סוג":    p.get("Type", ""),
                "💵 כניסה":  f"{bp:.3f}",
                "🏔️ שיא":   f"{trail_high:.3f}",
                "💰 עכשיו":  f"{lp:.3f}",
                "📊 רווח%":  f"{'🟢+' if profit>=0 else '🔴'}{abs(profit):.1f}%",
                "↘️ מהשיא":  f"{'🟡' if from_peak>=-3 else '🔴'}{from_peak:.1f}%",
                "🎯 ל-TP":   f"+{to_tp:.1f}%",
                "📈 מסלול":  bar,
                "📦 כמות":   f"{p['Qty']:.4f}",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True)

    if trades:
        st.markdown("#### 📋 יומן עסקאות")
        st.dataframe(pd.DataFrame(trades[:20]), hide_index=True)


# ════════════════════════════════════════════════════════════════════════
# ⚡ DAY TRADE AGENT
# ════════════════════════════════════════════════════════════════════════

def render_day_trade_agent(df_all: pd.DataFrame):
    st.markdown(
        '<div class="ai-card" style="border-right-color:#e65100;">'
        '<b>⚡ סוכן יומי — מסחר קצר-טווח</b><br>'
        'קונה בדיפ (RSI&lt;42). יוצא אוטומטית לפי TP/SL. '
        'מושבת בשוק דובי קיצוני (VIX>30).'
        '</div>',
        unsafe_allow_html=True,
    )

    if df_all is None or df_all.empty:
        st.warning("⏳ אין נתוני מניות — ממתין לסריקה.")
        return

    # ── מצב שוק ────────────────────────────────────────────────────────
    regime = _regime_banner()

    # ── State ────────────────────────────────────────────────────────────
    portfolio = _norm(load("day_portfolio", []))
    cash      = float(load("day_cash_ils", 100000.0))
    trades    = load("day_trades_log", [])
    initial   = float(load("day_initial", 100000.0))

    # ── הגדרות Stop-Loss / Take-Profit / Rebalance ──────────────────────
    with st.expander("⚙️ הגדרות Stop-Loss / Take-Profit / Rebalance", expanded=False):
        col_tp, col_sl, col_rb = st.columns(3)
        day_tp = col_tp.slider("🎯 Take-Profit %",     1, 15, 4, 1, key="day_tp_pct",
                               help="מוכר כשהרווח מגיע לאחוז זה")
        day_sl = col_sl.slider("🛑 Trailing Stop %",   1, 10, 2, 1, key="day_sl_pct",
                               help="מוכר כשירידה מהשיא מגיעה לאחוז זה")
        day_rb = col_rb.slider("🔁 Rebalance מקס %",  10, 50, 25, 5, key="day_rebalance_pct",
                               help="מוכר עודף כשפוזיציה חורגת ממשקל זה")
        save("day_tp_pct", day_tp)
        save("day_sl_pct", day_sl)
        save("day_rebalance_pct", day_rb)

    # ── Auto Exit + Rebalance — רץ בכל טעינת עמוד ──────────────────────
    if portfolio:
        portfolio, cash, trades, auto_sold, auto_report = _run_auto_exit(
            portfolio, cash, trades, day_tp, day_sl, "יומי"
        )
        portfolio, cash, trades, rb_count, rb_report = _run_rebalance(
            portfolio, cash, trades, day_rb, "יומי"
        )
        all_actions = auto_report + rb_report
        if auto_sold > 0 or rb_count > 0:
            save("day_portfolio", portfolio)
            save("day_cash_ils", round(cash, 2))
            save("day_trades_log", trades[:300])
            if all_actions:
                st.toast(f"🤖 יומי: {', '.join(all_actions)}", icon="⚡")

    pv    = _port_value(portfolio)
    total = cash + pv
    pnl   = total - initial

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("💵 מזומן",      f"₪{cash:,.0f}")
    c2.metric("📈 שווי תיק",   f"₪{pv:,.0f}")
    c3.metric("🏦 סה\"כ",      f"₪{total:,.0f}")
    c4.metric("📊 רווח/הפסד",  f"{'🟢+' if pnl>=0 else '🔴'}₪{abs(pnl):,.0f}",
              delta=f"{(pnl/initial*100):+.1f}%" if initial else "")
    c5.metric("🎯 TP/SL",      f"+{day_tp}% / -{day_sl}%")

    # ── ML Signals ───────────────────────────────────────────────────────
    try:
        ml_day_buys = get_top_buys(timeframe="short", min_confidence=55, hours_back=24, limit=5)
        if ml_day_buys:
            ml_d_syms = [x["symbol"] for x in ml_day_buys]
            st.success(f"🧠 **ML יומי ממליץ (24ש):** {', '.join(ml_d_syms)}")
        else:
            ml_day_buys = []
    except Exception:
        ml_day_buys = []

    # ── Signals ──────────────────────────────────────────────────────────
    day_cands = df_all.copy()
    if "RSI" in day_cands.columns:   day_cands = day_cands[day_cands["RSI"] < 42]
    if "Score" in day_cands.columns: day_cands = day_cands[day_cands["Score"] >= 2]

    try:
        if ml_day_buys and "Symbol" in day_cands.columns:
            ml_d_set  = {x["symbol"] for x in ml_day_buys}
            day_cands = day_cands.copy()
            day_cands.loc[day_cands["Symbol"].isin(ml_d_set), "Score"] += 2
    except Exception:
        pass

    day_cands = day_cands.nlargest(10, "Score") if "Score" in day_cands.columns else day_cands.head(10)

    show_cols = [c for c in ["Symbol","Price","RSI","Score","ret_5d","Change","Action"]
                 if c in day_cands.columns]
    if not day_cands.empty:
        st.markdown("#### 📡 סיגנלים (RSI<42, ציון≥2 + ML)")
        st.dataframe(day_cands[show_cols].reset_index(drop=True), hide_index=True)
    else:
        st.info("אין סיגנלי קנייה יומיים כרגע.")

    # ── Buttons ──────────────────────────────────────────────────────────
    b1, b2, b3, b4, b5 = st.columns(5)

    with b1:
        buy_disabled = (regime["regime"] == "bear" and regime["vix"] > 30)
        if st.button("🚀 קנה יומי", key="day_buy", type="primary",
                     disabled=buy_disabled):
            if day_cands.empty:
                st.error("אין סיגנלים.")
            elif cash < 100:
                st.warning("אין מזומן.")
            else:
                existing = {p["Symbol"] for p in portfolio}
                alloc_pct = 0.15 if regime["regime"] == "neutral" else 0.25
                bought  = 0
                skipped = []
                for _, row in day_cands.iterrows():
                    sym = row["Symbol"]
                    if sym in existing or len(portfolio) >= 5: continue
                    lp  = _live(sym, float(row.get("Price", 0)))
                    if lp <= 0: continue

                    # 🗂️ Sector Diversification — יומי מחמיר פחות (מקסימום 3)
                    sec_chk = can_buy_sector(sym, portfolio, max_per_sector=3)
                    if not sec_chk["allowed"]:
                        skipped.append(f"{sym} ({sec_chk['sector_he']})")
                        continue

                    # 🧬 RL Check
                    rl = should_buy(sym, min_trades=3, min_win_rate=30.0)
                    if not rl["allowed"]:
                        skipped.append(sym)
                        continue

                    boost = get_adaptive_confidence_boost(sym)
                    alloc = min(cash * alloc_pct * (1 + boost / 100), cash)
                    qty   = alloc / lp
                    portfolio.append({
                        "Symbol": sym, "BuyPrice": round(lp, 4),
                        "TrailingHigh": round(lp, 4),
                        "Qty": round(qty, 4), "BuyDate": datetime.now().isoformat(),
                        "Type": _asset_label(sym),
                    })
                    cash -= alloc
                    existing.add(sym)
                    trades.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": "קנייה-יומי",
                        "💰": f"{lp:.3f}",
                        "📊": f"RSI {row.get('RSI',0):.0f} | {regime['emoji']} | RL{boost:+.0f}",
                        "🏷️": _asset_label(sym),
                    })
                    bought += 1
                save("day_portfolio", portfolio)
                save("day_cash_ils", round(cash, 2))
                save("day_trades_log", trades[:300])
                msg = f"✅ נקנו {bought} פוזיציות! TP +{day_tp}% / SL -{day_sl}%"
                if skipped:
                    msg += f" | RL חסם: {', '.join(skipped)}"
                st.success(msg)
                st.rerun()

    with b2:
        if st.button("🔁 בדוק TP/SL", key="day_check_exit"):
            portfolio, cash, trades, sold, report = _run_auto_exit(
                portfolio, cash, trades, day_tp, day_sl, "יומי"
            )
            save("day_portfolio", portfolio)
            save("day_cash_ils", round(cash, 2))
            save("day_trades_log", trades[:300])
            if sold:
                st.success(f"✅ {sold} פוזיציות:\n" + "\n".join(report))
            else:
                st.info("אין פוזיציות שהגיעו ל-TP/SL.")
            st.rerun()

    with b3:
        if portfolio and st.button("💸 סגור הכל", key="day_close"):
            proceeds = 0.0
            for p in portfolio:
                lp     = _live(p["Symbol"], p.get("BuyPrice", 0))
                profit = ((lp / p["BuyPrice"]) - 1) * 100 if p["BuyPrice"] else 0
                proceeds += lp * p["Qty"]
                trades.insert(0, {
                    "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "📌": p["Symbol"], "↔️": "סגירה-ידנית",
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

    with b4:
        if st.button("🔄 איפוס", key="day_reset"):
            save("day_portfolio", [])
            save("day_cash_ils", 100000.0)
            save("day_initial", 100000.0)
            save("day_trades_log", [])
            st.success("✅ אופס!")
            st.rerun()

    with b5:
        if st.button("📊 סטטיסטיקות", key="day_stats"):
            if trades:
                wins   = [t for t in trades if "+" in str(t.get("📊","")) and "TP" in str(t.get("↔️",""))]
                losses = [t for t in trades if "SL" in str(t.get("↔️",""))]
                total_t = len([t for t in trades if "קנייה" not in str(t.get("↔️",""))])
                win_rate = round(len(wins) / total_t * 100) if total_t else 0
                st.info(f"🏆 Win Rate: **{win_rate}%** | "
                        f"✅ TP: {len(wins)} | 🛑 SL: {len(losses)} | סה\"כ: {total_t}")

    # ── Sector Breakdown ─────────────────────────────────────────────────
    if portfolio:
        with st.expander("🗂️ גיוון סקטוריאלי", expanded=False):
            render_sector_breakdown(portfolio)

    # ── Portfolio table ───────────────────────────────────────────────────
    if portfolio:
        st.markdown("#### ⚡ פוזיציות פתוחות")
        rows = []
        for p in portfolio:
            lp      = _live(p["Symbol"], p["BuyPrice"])
            bp      = float(p["BuyPrice"])
            profit  = ((lp / bp) - 1) * 100 if bp else 0
            to_tp   = day_tp - profit
            to_sl   = profit + day_sl
            trail_high = float(p.get("TrailingHigh", bp))
            from_peak  = ((lp / trail_high) - 1) * 100 if trail_high else 0
            rows.append({
                "📌 סימול":  p["Symbol"],
                "🏷️ סוג":   p.get("Type", ""),
                "💵 כניסה": f"{bp:.3f}",
                "🏔️ שיא":  f"{trail_high:.3f}",
                "💰 עכשיו": f"{lp:.3f}",
                "📊 P&L%":  f"{'🟢+' if profit>=0 else '🔴'}{abs(profit):.1f}%",
                "↘️ מהשיא": f"{'🟡' if from_peak>=-1.5 else '🔴'}{from_peak:.1f}%",
                "🎯 ל-TP":  f"+{to_tp:.1f}%",
                "📦 כמות":  f"{p['Qty']:.4f}",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True)

    if trades:
        st.markdown("#### 📋 עסקאות")
        st.dataframe(pd.DataFrame(trades[:30]), hide_index=True)


def run_simulator():
    st.markdown("## Trading Simulator")
    st.info("השתמש בלשוניות 'סוכן ערך' ו'סוכן יומי' למסחר אינטראקטיבי.")
