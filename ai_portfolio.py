# ai_portfolio.py — תיק מנוהל AI v3
# ════════════════════════════════════════════════════════════════════════════
# תיק שהסוכנים מנהלים אוטומטית לפי ML + AI
# כל החלטה נשמרת ל-DB כדי שהמודל ילמד ממנה
# ════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from storage import save, load

def _try_telegram(title, body):
    try:
        import telegram_ai
        telegram_ai.send_alert_notification(title, body)
    except Exception:
        pass

# ─── מפתחות אחסון ────────────────────────────────────────────────────────────
KEY_CAPITAL    = "aip_capital"
KEY_CASH       = "aip_cash"
KEY_POSITIONS  = "aip_positions"       # [{symbol, qty, buy_price, buy_time, reason, agent}]
KEY_TRADES     = "aip_trades"          # היסטוריית עסקאות מלאה
KEY_DECISIONS  = "aip_decisions"       # החלטות AI לצורך למידה
KEY_PERF       = "aip_performance"     # snapshot ביצועים יומי
KEY_SETTINGS   = "aip_settings"
KEY_ENABLED    = "aip_enabled"

USD_RATE_DEFAULT = 3.75

# ─── אתחול ───────────────────────────────────────────────────────────────────
def _init():
    defaults = {
        KEY_CAPITAL:   load(KEY_CAPITAL,  10000.0),
        KEY_CASH:      load(KEY_CASH,     10000.0),
        KEY_POSITIONS: load(KEY_POSITIONS, []),
        KEY_TRADES:    load(KEY_TRADES,    []),
        KEY_DECISIONS: load(KEY_DECISIONS, []),
        KEY_PERF:      load(KEY_PERF,      []),
        KEY_SETTINGS:  load(KEY_SETTINGS,  {
            "max_position_pct": 20.0,
            "stop_loss_pct":    8.0,
            "take_profit_pct":  20.0,
            "min_score":        4,
            "use_ml":           True,
            "risk_level":       "medium",
            "auto_rebalance":   False,
        }),
        KEY_ENABLED: load(KEY_ENABLED, False),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _save_all():
    for k in [KEY_CAPITAL, KEY_CASH, KEY_POSITIONS, KEY_TRADES,
              KEY_DECISIONS, KEY_PERF, KEY_SETTINGS, KEY_ENABLED]:
        save(k, st.session_state[k])


@st.cache_data(ttl=300)
def _usd_rate():
    try:
        h = yf.Ticker("USDILS=X").history(period="1d")
        return float(h["Close"].iloc[-1]) if not h.empty else USD_RATE_DEFAULT
    except Exception:
        return USD_RATE_DEFAULT


@st.cache_data(ttl=300)
def _live_price(symbol: str) -> float | None:
    try:
        h = yf.Ticker(symbol).history(period="1d", interval="5m")
        return float(h["Close"].iloc[-1]) if not h.empty else None
    except Exception:
        return None


def _to_ils(price: float, symbol: str, usd_rate: float) -> float:
    """המרה למחיר שקלי"""
    if symbol.endswith(".TA"):
        return price / 100          # אגורות → שקלים
    if symbol.endswith("-USD") or "=F" in symbol:
        return price * usd_rate     # דולר → שקל
    return price * usd_rate         # ברירת מחדל: דולר → שקל


def _portfolio_value_ils(usd_rate: float) -> float:
    total = 0.0
    for pos in st.session_state.get(KEY_POSITIONS, []):
        lp = _live_price(pos["symbol"]) or pos["buy_price"]
        total += _to_ils(lp, pos["symbol"], usd_rate) * pos["qty"]
    return total


# ─── לוגיקת החלטה של ה-AI ────────────────────────────────────────────────────
def _ai_score_asset(row: dict, settings: dict, ml_model=None, ml_scaler=None) -> dict:
    """
    מחשב ציון כניסה 0-100 לנכס לפי כלל האגודל + ML.
    מחזיר: {"score": int, "action": str, "reasons": list}
    """
    reasons  = []
    score    = 0
    atype    = row.get("AssetType", "stock")
    rsi      = row.get("RSI", 50)
    pdf_score = row.get("Score", 0)
    margin   = row.get("Margin", 0)
    upside   = row.get("TargetUpside", 0)
    change   = row.get("Change", 0)

    risk     = settings.get("risk_level", "medium")
    min_score = settings.get("min_score", 4)

    # ── ניקוד RSI ────────────────────────────────────────────────────
    if rsi < 30:
        score += 30
        reasons.append(f"RSI {rsi:.0f} — מכירת יתר קיצונית 🟢")
    elif rsi < 40:
        score += 20
        reasons.append(f"RSI {rsi:.0f} — מכירת יתר 🟡")
    elif rsi > 70:
        score -= 20
        reasons.append(f"RSI {rsi:.0f} — קנייה יתר ⚠️")
    elif rsi > 60:
        score -= 5

    # ── ניקוד ציון PDF (מניות בלבד) ──────────────────────────────────
    if atype == "stock":
        if pdf_score >= 5:
            score += 35
            reasons.append(f"ציון PDF {pdf_score}/6 — מניית זהב 💎")
        elif pdf_score >= 4:
            score += 20
            reasons.append(f"ציון PDF {pdf_score}/6 — איכות גבוהה")
        elif pdf_score < min_score:
            score -= 20
            reasons.append(f"ציון PDF {pdf_score}/6 — מתחת לסף 🔴")

    # ── ניקוד Upside אנליסטים ─────────────────────────────────────────
    if upside > 20:
        score += 15
        reasons.append(f"פוטנציאל +{upside:.0f}% לפי אנליסטים 📊")
    elif upside > 10:
        score += 7

    # ── ניקוד מגמה ────────────────────────────────────────────────────
    if change < -3:
        score += 10
        reasons.append(f"ירידה של {change:.1f}% היום — כניסה בדיפ 📉")
    elif change > 5:
        score -= 10
        reasons.append(f"עלייה חדה {change:.1f}% — מאוחר לכנס")

    # ── רמת סיכון ────────────────────────────────────────────────────
    if risk == "low":
        if atype == "crypto": score -= 30
        if pdf_score < 4:     score -= 15
    elif risk == "high":
        if atype == "crypto": score += 15

    # ── ML (אם מודל זמין) ────────────────────────────────────────────
    ml_pred = None
    if settings.get("use_ml") and ml_model is not None and ml_scaler is not None:
        try:
            import pickle, base64, io
            model  = pickle.loads(base64.b64decode(ml_model))
            scaler = pickle.loads(base64.b64decode(ml_scaler))
            feat   = np.array([[
                rsi, change, pdf_score, margin, upside, 0, 0, 0, 0, 0, 0, 0
            ]])
            feat_scaled = scaler.transform(feat)
            ml_pred     = int(model.predict(feat_scaled)[0])
            ml_conf     = float(model.predict_proba(feat_scaled)[0][ml_pred] * 100)
            if ml_pred == 1:
                score += 20
                reasons.append(f"🤖 ML: עלייה צפויה ({ml_conf:.0f}% ביטחון)")
            else:
                score -= 10
                reasons.append(f"🤖 ML: לא צופה עלייה ({ml_conf:.0f}% ביטחון)")
        except Exception:
            pass

    score = max(0, min(100, score))

    if score >= 70:   action = "קנייה חזקה 💎"
    elif score >= 50: action = "קנייה 🟢"
    elif score >= 35: action = "המתן ⚖️"
    else:             action = "לא לקנות 🔴"

    return {"score": score, "action": action, "reasons": reasons, "ml_pred": ml_pred}


def _record_decision(symbol: str, action: str, score: int, reasons: list,
                     price: float, executed: bool):
    """שומר כל החלטת AI — לצורך למידה עתידית."""
    decision = {
        "timestamp":  datetime.now().isoformat(),
        "symbol":     symbol,
        "action":     action,
        "ai_score":   score,
        "reasons":    reasons,
        "price_at_decision": price,
        "executed":   executed,
        "outcome":    None,         # יתמלא בסגירה
        "outcome_pct": None,
    }
    decisions = st.session_state.get(KEY_DECISIONS, [])
    decisions.insert(0, decision)
    st.session_state[KEY_DECISIONS] = decisions[:500]  # שמור 500 אחרונות
    save(KEY_DECISIONS, st.session_state[KEY_DECISIONS])


def _update_decision_outcomes():
    """מעדכן תוצאות עסקאות שנסגרו — הלמידה קורית כאן."""
    decisions = st.session_state.get(KEY_DECISIONS, [])
    trades    = st.session_state.get(KEY_TRADES,    [])
    updated   = False
    for d in decisions:
        if d.get("outcome") is not None: continue
        if not d.get("executed"):        continue
        # חפש עסקת סגירה מתאימה
        for t in trades:
            if t.get("symbol") == d["symbol"] and t.get("action") == "מכירה":
                try:
                    buy_p  = d["price_at_decision"]
                    sell_p = t["price"]
                    d["outcome"]     = "רווח" if sell_p > buy_p else "הפסד"
                    d["outcome_pct"] = round((sell_p / buy_p - 1) * 100, 2)
                    updated = True
                except Exception:
                    pass
    if updated:
        st.session_state[KEY_DECISIONS] = decisions
        save(KEY_DECISIONS, decisions)


def _snapshot_performance(usd_rate: float):
    """שומר snapshot יומי של ביצועי התיק."""
    port_val = _portfolio_value_ils(usd_rate)
    cash     = st.session_state.get(KEY_CASH, 0)
    total    = port_val + cash
    capital  = st.session_state.get(KEY_CAPITAL, 10000)
    perf     = st.session_state.get(KEY_PERF, [])
    today    = datetime.now().strftime("%Y-%m-%d")
    # לא שמור אם כבר יש snapshot להיום
    if perf and perf[-1].get("date") == today:
        return
    perf.append({
        "date":    today,
        "total":   round(total, 2),
        "cash":    round(cash, 2),
        "portfolio": round(port_val, 2),
        "pnl":     round(total - capital, 2),
        "pnl_pct": round((total / capital - 1) * 100, 2) if capital > 0 else 0,
        "n_positions": len(st.session_state.get(KEY_POSITIONS, [])),
    })
    st.session_state[KEY_PERF] = perf[-365:]  # שנה אחרונה
    save(KEY_PERF, st.session_state[KEY_PERF])


# ─── פעולות תיק ──────────────────────────────────────────────────────────────
def _execute_buy(symbol: str, ils_amount: float, usd_rate: float,
                 reason: str, ai_score: int, agent_name: str) -> bool:
    """מבצע קנייה בפועל (דמו)."""
    cash = st.session_state.get(KEY_CASH, 0)
    if ils_amount > cash:
        ils_amount = cash
    if ils_amount < 50:
        return False

    live_px = _live_price(symbol)
    if not live_px:
        return False

    px_ils = _to_ils(live_px, symbol, usd_rate)
    qty    = ils_amount / px_ils if px_ils > 0 else 0
    if qty <= 0:
        return False

    pos = {
        "symbol":    symbol,
        "qty":       round(qty, 6),
        "buy_price": live_px,
        "buy_price_ils": px_ils,
        "buy_time":  datetime.now().isoformat(),
        "reason":    reason,
        "ai_score":  ai_score,
        "agent":     agent_name,
        "invested_ils": round(ils_amount, 2),
    }
    positions = st.session_state.get(KEY_POSITIONS, [])
    # אם כבר יש פוזיציה — ממצע
    existing  = [p for p in positions if p["symbol"] == symbol]
    if existing:
        old = existing[0]
        total_qty  = old["qty"] + qty
        avg_price  = (old["buy_price"] * old["qty"] + live_px * qty) / total_qty
        old["qty"]            = round(total_qty, 6)
        old["buy_price"]      = avg_price
        old["buy_price_ils"]  = _to_ils(avg_price, symbol, usd_rate)
        old["invested_ils"]  += round(ils_amount, 2)
    else:
        positions.append(pos)
    st.session_state[KEY_POSITIONS] = positions
    st.session_state[KEY_CASH] -= ils_amount

    # לוג עסקה
    trade = {
        "timestamp": datetime.now().isoformat(),
        "symbol":    symbol,
        "action":    "קנייה",
        "price":     live_px,
        "price_ils": px_ils,
        "qty":       round(qty, 6),
        "amount_ils": round(ils_amount, 2),
        "agent":     agent_name,
        "ai_score":  ai_score,
        "reason":    reason,
    }
    trades = st.session_state.get(KEY_TRADES, [])
    trades.insert(0, trade)
    st.session_state[KEY_TRADES] = trades[:1000]

    _record_decision(symbol, "קנייה", ai_score, [reason], live_px, True)
    _try_telegram(f"🟢 קנייה: {symbol}",
                  f"₪{ils_amount:,.0f} | מחיר: ${live_px:.2f} | {reason[:60]}")
    _save_all()
    return True


def _execute_sell(symbol: str, reason: str, usd_rate: float, agent_name: str) -> float:
    """מוכר פוזיציה שלמה. מחזיר רווח/הפסד."""
    positions = st.session_state.get(KEY_POSITIONS, [])
    pos_list  = [p for p in positions if p["symbol"] == symbol]
    if not pos_list:
        return 0.0

    pos      = pos_list[0]
    live_px  = _live_price(symbol) or pos["buy_price"]
    px_ils   = _to_ils(live_px, symbol, usd_rate)
    sell_ils = px_ils * pos["qty"]
    buy_ils  = pos["buy_price_ils"] * pos["qty"]
    pnl      = sell_ils - buy_ils
    pnl_pct  = (sell_ils / buy_ils - 1) * 100 if buy_ils > 0 else 0

    st.session_state[KEY_POSITIONS] = [p for p in positions if p["symbol"] != symbol]
    st.session_state[KEY_CASH]     += sell_ils

    trade = {
        "timestamp": datetime.now().isoformat(),
        "symbol":    symbol,
        "action":    "מכירה",
        "price":     live_px,
        "price_ils": px_ils,
        "qty":       pos["qty"],
        "amount_ils": round(sell_ils, 2),
        "pnl_ils":   round(pnl, 2),
        "pnl_pct":   round(pnl_pct, 2),
        "agent":     agent_name,
        "reason":    reason,
    }
    trades = st.session_state.get(KEY_TRADES, [])
    trades.insert(0, trade)
    st.session_state[KEY_TRADES] = trades[:1000]
    _update_decision_outcomes()
    sign = "🟢 רווח" if pnl > 0 else "🔴 הפסד"
    _try_telegram(f"🔴 מכירה: {symbol}",
                  f"{sign} ₪{abs(pnl):,.0f} ({pnl_pct:+.1f}%) | {reason[:60]}")
    _save_all()
    return pnl


# ─── Stop-Loss / Take-Profit אוטומטי ─────────────────────────────────────────
def _check_stop_take(usd_rate: float, settings: dict) -> list:
    """בודק Stop-Loss ו-Take-Profit על כל הפוזיציות. מחזיר רשימת פעולות."""
    actions  = []
    sl_pct   = settings.get("stop_loss_pct",   8.0)
    tp_pct   = settings.get("take_profit_pct", 20.0)
    for pos in list(st.session_state.get(KEY_POSITIONS, [])):
        lp      = _live_price(pos["symbol"])
        if not lp: continue
        lp_ils  = _to_ils(lp, pos["symbol"], usd_rate)
        buy_ils = pos["buy_price_ils"]
        pnl_pct = (lp_ils / buy_ils - 1) * 100 if buy_ils > 0 else 0
        if pnl_pct <= -sl_pct:
            pnl = _execute_sell(pos["symbol"], f"Stop-Loss {pnl_pct:.1f}%", usd_rate, "🛡️ הגנה")
            actions.append({"type": "stop_loss", "symbol": pos["symbol"], "pnl": pnl, "pct": pnl_pct})
        elif pnl_pct >= tp_pct:
            pnl = _execute_sell(pos["symbol"], f"Take-Profit {pnl_pct:.1f}%", usd_rate, "🎯 יעד")
            actions.append({"type": "take_profit", "symbol": pos["symbol"], "pnl": pnl, "pct": pnl_pct})
    return actions


# ─── סוכן AI ראשי ─────────────────────────────────────────────────────────────
def run_ai_agent(df_all: pd.DataFrame, usd_rate: float, agent_name: str = "🤖 AI Manager") -> dict:
    """
    מריץ מחזור השקעה שלם:
    1. בדוק SL/TP קיים
    2. נתח הזדמנויות חדשות
    3. קנה הכי טוב
    4. שמור snapshot
    """
    if df_all.empty:
        return {"bought": [], "sold": [], "skipped": []}

    settings   = st.session_state.get(KEY_SETTINGS, {})
    ml_model   = st.session_state.get("ml_model_b64")
    ml_scaler  = st.session_state.get("ml_scaler_b64")
    cash       = st.session_state.get(KEY_CASH, 0)
    capital    = st.session_state.get(KEY_CAPITAL, 10000)
    max_pos_pct = settings.get("max_position_pct", 20.0) / 100
    max_pos_ils = capital * max_pos_pct

    # שלב 1: SL/TP
    sl_actions = _check_stop_take(usd_rate, settings)

    # שלב 2: ניתוח הזדמנויות
    scored = []
    for _, row in df_all.iterrows():
        sym = row["Symbol"]
        # דלג על אם כבר מחזיק
        if any(p["symbol"] == sym for p in st.session_state.get(KEY_POSITIONS, [])):
            continue
        result = _ai_score_asset(row.to_dict(), settings, ml_model, ml_scaler)
        if result["score"] >= 50:
            scored.append({"symbol": sym, **result, "row": row.to_dict()})

    scored.sort(key=lambda x: x["score"], reverse=True)

    # שלב 3: קנה את ה-Top 3 (לפי תקציב)
    bought  = []
    skipped = []
    cash_now = st.session_state.get(KEY_CASH, 0)

    for item in scored[:5]:
        sym    = item["symbol"]
        invest = min(max_pos_ils, cash_now * 0.3)  # עד 30% מזומן זמין לכל קנייה
        if invest < 100:
            skipped.append(sym)
            continue
        reason = " | ".join(item["reasons"][:2])
        ok = _execute_buy(sym, invest, usd_rate, reason, item["score"], agent_name)
        if ok:
            bought.append({"symbol": sym, "score": item["score"], "amount": invest, "action": item["action"]})
            cash_now = st.session_state.get(KEY_CASH, 0)
            if len(bought) >= 3:
                break
        else:
            skipped.append(sym)

    # שלב 4: snapshot
    _snapshot_performance(usd_rate)

    return {"bought": bought, "sold": [a["symbol"] for a in sl_actions], "skipped": skipped}


# ─── ממשק Streamlit ──────────────────────────────────────────────────────────
def render_ai_portfolio(df_all: pd.DataFrame):
    _init()
    usd_rate = _usd_rate()

    st.markdown("""
    <div class="ai-card" style="border-right-color:#5c6bc0;background:linear-gradient(135deg,#e8eaf6,#fff);">
        <b style="font-size:18px;">🤖 תיק מנוהל AI</b><br>
        <small>הסוכנים מנהלים את התיק אוטומטית לפי ML + כללי AI.
        כל החלטה נשמרת כדי שהמערכת תלמד ותשתפר.</small>
    </div>
    """, unsafe_allow_html=True)

    # ── מדדים עליונים ────────────────────────────────────────────────────────
    capital   = st.session_state[KEY_CAPITAL]
    cash      = st.session_state[KEY_CASH]
    port_val  = _portfolio_value_ils(usd_rate)
    total     = cash + port_val
    pnl       = total - capital
    pnl_pct   = (pnl / capital * 100) if capital > 0 else 0
    n_pos     = len(st.session_state.get(KEY_POSITIONS, []))
    n_trades  = len(st.session_state.get(KEY_TRADES, []))

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("💰 מזומן",       f"₪{cash:,.0f}")
    c2.metric("💼 מניות",       f"₪{port_val:,.0f}")
    c3.metric("📊 שווי כולל",   f"₪{total:,.0f}")
    c4.metric("📈 רווח/הפסד",
              f"{'🟢 +' if pnl>=0 else '🔴 '}₪{abs(pnl):,.0f}",
              delta=f"{pnl_pct:+.1f}%")
    c5.metric("🔢 פוזיציות",    f"{n_pos} | {n_trades} עסקאות")

    enabled = st.session_state.get(KEY_ENABLED, False)
    color   = "#2e7d32" if enabled else "#666"
    st.markdown(
        f'<div style="background:{"#e8f5e9" if enabled else "#fafafa"};'
        f'border:2px solid {color};border-radius:8px;padding:8px 14px;'
        f'margin-bottom:10px;font-weight:700;color:{color};">'
        f'{"🟢 התיק המנוהל פעיל — הסוכנים עובדים" if enabled else "⚪ התיק המנוהל כבוי"}</div>',
        unsafe_allow_html=True,
    )

    # ── טאבים ────────────────────────────────────────────────────────────────
    t1,t2,t3,t4,t5,t6 = st.tabs([
        "🚀 הפעלה","📋 פוזיציות","📜 היסטוריה","🧠 למידה","⚙️ הגדרות","📊 ביצועים"
    ])

    # ══ TAB 1: הפעלה ══
    with t1:
        col_a, col_b = st.columns([1,1])
        with col_a:
            if not enabled:
                if st.button("🟢 הפעל תיק מנוהל", type="primary", key="aip_enable"):
                    st.session_state[KEY_ENABLED] = True
                    save(KEY_ENABLED, True)
                    st.success("✅ התיק המנוהל הופעל!")
                    st.rerun()
            else:
                if st.button("⏸️ השהה תיק מנוהל", key="aip_disable"):
                    st.session_state[KEY_ENABLED] = False
                    save(KEY_ENABLED, False)
                    st.rerun()

        with col_b:
            if st.button("▶️ הרץ מחזור AI עכשיו", type="primary" if enabled else "secondary", key="aip_run"):
                if df_all.empty:
                    st.warning("אין נתוני שוק.")
                else:
                    with st.spinner("🤖 הסוכן מנתח..."):
                        result = run_ai_agent(df_all, usd_rate)
                    if result["bought"]:
                        for b in result["bought"]:
                            st.success(f"✅ קנה {b['symbol']} | ציון AI: {b['score']} | {b['action']} | ₪{b['amount']:,.0f}")
                    if result["sold"]:
                        st.warning(f"🛡️ SL/TP הפעיל: {', '.join(result['sold'])}")
                    if not result["bought"] and not result["sold"]:
                        st.info("🔍 הסוכן לא מצא הזדמנויות כרגע.")
                    st.rerun()

        st.divider()
        st.markdown("#### 🔍 ניתוח הזדמנויות נוכחיות")
        if not df_all.empty:
            settings = st.session_state[KEY_SETTINGS]
            ml_model  = st.session_state.get("ml_model_b64")
            ml_scaler = st.session_state.get("ml_scaler_b64")
            rows = []
            for _, row in df_all.iterrows():
                result = _ai_score_asset(row.to_dict(), settings, ml_model, ml_scaler)
                rows.append({
                    "📌 נכס":      f"{row.get('Emoji','')} {row['Symbol']}",
                    "🎯 ציון AI":  result["score"],
                    "📊 RSI":      f"{row.get('RSI',50):.0f}",
                    "⭐ PDF":      row.get("Score", "—"),
                    "💡 המלצה":   result["action"],
                    "🤖 סיבות":   " | ".join(result["reasons"][:2]),
                })
            df_opp = pd.DataFrame(rows).sort_values("🎯 ציון AI", ascending=False)
            st.dataframe(df_opp, hide_index=True)

    # ══ TAB 2: פוזיציות ══
    with t2:
        positions = st.session_state.get(KEY_POSITIONS, [])
        if not positions:
            st.info("אין פוזיציות פתוחות.")
        else:
            rows = []
            for pos in positions:
                lp     = _live_price(pos["symbol"]) or pos["buy_price"]
                lp_ils = _to_ils(lp, pos["symbol"], usd_rate)
                bp_ils = pos.get("buy_price_ils", lp_ils)
                pnl_   = (lp_ils - bp_ils) * pos["qty"]
                pct_   = (lp_ils / bp_ils - 1) * 100 if bp_ils > 0 else 0
                rows.append({
                    "📌 נכס":       pos["symbol"],
                    "כמות":         round(pos["qty"], 4),
                    "מחיר כניסה ₪": f"₪{bp_ils:,.2f}",
                    "מחיר חי ₪":    f"₪{lp_ils:,.2f}",
                    "שווי כולל ₪":  f"₪{lp_ils * pos['qty']:,.0f}",
                    "רווח/הפסד":    f"{'🟢 +' if pnl_>=0 else '🔴 '}₪{abs(pnl_):,.0f}",
                    "תשואה %":      f"{'🟢 +' if pct_>=0 else '🔴 '}{pct_:.1f}%",
                    "סוכן":         pos.get("agent","—"),
                    "ציון AI":      pos.get("ai_score","—"),
                    "סיבה":         pos.get("reason","—")[:40],
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True)

            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                sell_sym = st.selectbox("מכור פוזיציה:", [p["symbol"] for p in positions], key="aip_sell_sym")
            with col2:
                if st.button("💸 מכור ידנית", key="aip_sell_manual"):
                    pnl_ = _execute_sell(sell_sym, "מכירה ידנית", usd_rate, "👤 משתמש")
                    sign = "🟢 רווח" if pnl_ >= 0 else "🔴 הפסד"
                    st.success(f"{sign}: ₪{abs(pnl_):,.0f}")
                    st.rerun()

    # ══ TAB 3: היסטוריה ══
    with t3:
        trades = st.session_state.get(KEY_TRADES, [])
        if not trades:
            st.info("אין היסטוריית עסקאות.")
        else:
            df_trades = pd.DataFrame([{
                "⏰ זמן":     t["timestamp"][:16].replace("T"," "),
                "📌 נכס":    t["symbol"],
                "↔️ פעולה":  t["action"],
                "💰 מחיר ₪": f"₪{t.get('price_ils',0):,.2f}",
                "כמות":       round(t.get("qty",0),4),
                "סכום ₪":    f"₪{t.get('amount_ils',0):,.0f}",
                "רווח/הפסד": f"{'🟢 +' if t.get('pnl_ils',0)>=0 else '🔴 '}₪{abs(t.get('pnl_ils',0)):,.0f}" if "pnl_ils" in t else "—",
                "סוכן":       t.get("agent","—"),
            } for t in trades[:100]])
            st.dataframe(df_trades, hide_index=True)

            # סיכום
            sells = [t for t in trades if t.get("action")=="מכירה" and "pnl_ils" in t]
            if sells:
                total_pnl = sum(t["pnl_ils"] for t in sells)
                wins      = sum(1 for t in sells if t["pnl_ils"]>0)
                st.divider()
                m1,m2,m3,m4 = st.columns(4)
                m1.metric("💰 רווח מצטבר", f"{'🟢 ' if total_pnl>=0 else '🔴 '}₪{abs(total_pnl):,.0f}")
                m2.metric("✅ זכיות",       f"{wins}/{len(sells)}")
                m3.metric("📊 אחוז הצלחה", f"{wins/len(sells)*100:.0f}%")
                m4.metric("📈 ממוצע/עסקה", f"₪{total_pnl/len(sells):,.0f}")

    # ══ TAB 4: למידה ══
    with t4:
        st.markdown("### 🧠 מה המערכת למדה")
        decisions = st.session_state.get(KEY_DECISIONS, [])
        with_outcome = [d for d in decisions if d.get("outcome")]

        if not with_outcome:
            st.info("📊 אין עדיין החלטות עם תוצאות. הרץ כמה מחזורים ואז מכור כדי לצבור נתוני למידה.")
        else:
            total = len(with_outcome)
            wins  = [d for d in with_outcome if d["outcome"]=="רווח"]
            losses= [d for d in with_outcome if d["outcome"]=="הפסד"]
            avg_score_win  = np.mean([d["ai_score"] for d in wins])  if wins   else 0
            avg_score_loss = np.mean([d["ai_score"] for d in losses]) if losses else 0

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("📊 החלטות עם תוצאה", total)
            c2.metric("✅ אחוז הצלחה",       f"{len(wins)/total*100:.0f}%")
            c3.metric("🎯 ציון ממוצע — רווח", f"{avg_score_win:.0f}")
            c4.metric("⚠️ ציון ממוצע — הפסד", f"{avg_score_loss:.0f}")

            st.markdown("#### 💡 תובנות אוטומטיות מהנתונים:")
            if avg_score_win > avg_score_loss + 10:
                st.success(f"✅ ציון AI גבוה ({avg_score_win:.0f}+) מתאם עם הצלחה — המודל עובד!")
            elif avg_score_win < avg_score_loss:
                st.warning("⚠️ ציון AI לא מתאם עם הצלחה — המודל צריך אימון מחדש.")

            # טבלת למידה
            rows = [{
                "⏰ תאריך":  d["timestamp"][:10],
                "📌 נכס":    d["symbol"],
                "🎯 ציון AI": d["ai_score"],
                "💡 פעולה":  d["action"],
                "📈 תוצאה":  f"{'🟢' if d['outcome']=='רווח' else '🔴'} {d['outcome']}",
                "% שינוי":   f"{d.get('outcome_pct',0):+.1f}%",
            } for d in with_outcome[:50]]
            st.dataframe(pd.DataFrame(rows), hide_index=True)

    # ══ TAB 5: הגדרות ══
    with t5:
        settings = st.session_state[KEY_SETTINGS]
        c1,c2 = st.columns(2)
        with c1:
            st.markdown("#### הגדרות סיכון")
            new_sl  = st.slider("Stop-Loss %",   3.0, 20.0, float(settings.get("stop_loss_pct", 8)), 0.5, key="aip_sl")
            new_tp  = st.slider("Take-Profit %", 5.0, 50.0, float(settings.get("take_profit_pct",20)), 1.0, key="aip_tp")
            new_pos = st.slider("מקסימום % לנכס",5.0, 50.0, float(settings.get("max_position_pct",20)), 5.0, key="aip_pos")
        with c2:
            st.markdown("#### הגדרות AI")
            new_risk  = st.selectbox("רמת סיכון", ["low","medium","high"],
                                     index=["low","medium","high"].index(settings.get("risk_level","medium")),
                                     key="aip_risk")
            new_score = st.slider("ציון PDF מינימלי", 0, 6, int(settings.get("min_score",4)), key="aip_minscore")
            new_ml    = st.checkbox("השתמש ב-ML", value=settings.get("use_ml", True), key="aip_useml")

        if st.button("💾 שמור הגדרות", key="aip_save_settings"):
            st.session_state[KEY_SETTINGS] = {
                "stop_loss_pct":    new_sl,
                "take_profit_pct":  new_tp,
                "max_position_pct": new_pos,
                "risk_level":       new_risk,
                "min_score":        new_score,
                "use_ml":           new_ml,
            }
            save(KEY_SETTINGS, st.session_state[KEY_SETTINGS])
            st.success("✅ נשמר!")

        st.divider()
        new_cap = st.number_input("הון התחלתי לתיק AI (₪)", 1000, 1000000,
                                   int(st.session_state[KEY_CAPITAL]), 500, key="aip_capital")
        if st.button("🔄 איפוס תיק מנוהל", key="aip_reset"):
            for k in [KEY_CASH, KEY_POSITIONS, KEY_TRADES, KEY_DECISIONS, KEY_PERF]:
                st.session_state[k] = [] if k != KEY_CASH else new_cap
            st.session_state[KEY_CAPITAL] = new_cap
            st.session_state[KEY_CASH]    = new_cap
            _save_all()
            st.success("✅ תיק אופס")
            st.rerun()

    # ══ TAB 6: ביצועים ══
    with t6:
        perf = st.session_state.get(KEY_PERF, [])
        if len(perf) < 2:
            st.info("📊 יש צורך ב-2 ימים לפחות כדי להציג גרף ביצועים.")
        else:
            df_perf = pd.DataFrame(perf)
            st.markdown("#### 📈 התפתחות שווי התיק")
            import plotly.graph_objects as go
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_perf["date"], y=df_perf["total"],
                                     mode="lines+markers", name="שווי כולל",
                                     line=dict(color="#1a73e8", width=3)))
            fig.add_trace(go.Scatter(x=df_perf["date"], y=df_perf["cash"],
                                     mode="lines", name="מזומן",
                                     line=dict(color="#ff9800", width=2, dash="dash")))
            fig.add_hline(y=st.session_state[KEY_CAPITAL], line_dash="dot",
                          line_color="gray", annotation_text="הון התחלתי")
            fig.update_layout(title="ביצועי תיק AI", xaxis_title="תאריך",
                              yaxis_title="₪", height=400, template="plotly_white")
            st.plotly_chart(fig)

            # מדדי ביצוע
            first_val = df_perf["total"].iloc[0]
            last_val  = df_perf["total"].iloc[-1]
            max_val   = df_perf["total"].max()
            max_dd    = ((df_perf["total"].cummax() - df_perf["total"]) / df_perf["total"].cummax() * 100).max()

            m1,m2,m3,m4 = st.columns(4)
            m1.metric("📈 תשואה כוללת",    f"{(last_val/first_val-1)*100:+.1f}%")
            m2.metric("🏆 שיא שווי",        f"₪{max_val:,.0f}")
            m3.metric("📉 Max Drawdown",    f"-{max_dd:.1f}%")
            m4.metric("📅 ימי מסחר",       len(df_perf))

            with st.expander("📋 טבלת ביצועים יומית"):
                st.dataframe(df_perf.sort_values("date", ascending=False), hide_index=True)
