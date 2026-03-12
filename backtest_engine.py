# backtest_engine.py — Strategy Backtester + Walk-Forward Validation
# ════════════════════════════════════════════════════════════════════
# עיקרון rate-limit:
#   yf.download(כל הסימבולים ביחד) = קריאה אחת לכל הנתונים
#   @st.cache_data(ttl=6h) — לא מוריד שוב עד שהקאש פג
#   benchmark (SPY) — נכלל באותה הורדה, לא קריאה נפרדת
# ════════════════════════════════════════════════════════════════════
import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

# ── רשימת הסימבולים לבאקטסט — מאוזנת, ללא סימבולים עם נקודה (TASE) ──
try:
    from config import SCAN_LIST as _SCAN
    _extra = [s for s in (_SCAN or []) if "." not in s and len(s) <= 5][:15]
except Exception:
    _extra = []

BACKTEST_UNIVERSE: list = list(set([
    "AAPL","MSFT","NVDA","GOOGL","META","AMZN","TSLA",
    "JPM","V","UNH","JNJ","XOM","WMT","PG","HD",
    "BRK-B","LLY","AVGO","MA","MRK","AMD","NFLX","PYPL",
    "BAC","GS","COST","ABBV","PFE","CVX","TMO",
] + _extra))

COMMISSION = 0.001          # 0.1% עמלה לכל כיוון
SLIPPAGE   = 0.001          # 0.1% slippage ממחיר הסגירה
DEFAULT_TP  = 12.0          # Take-Profit %
DEFAULT_SL  = 7.0           # Stop-Loss %
DEFAULT_TE  = 21            # Time Exit ימים
MAX_POS     = 8             # פוזיציות מקסימום
ALLOC_PCT   = 0.12          # 12% מהתיק לכל פוזיציה


# ────────────────────────────────────────────────────────────────────
# 1. הורדת נתונים — קריאה אחת לכל הסימבולים + SPY ביחד
# ────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=21600, show_spinner=False)   # קאש 6 שעות
def _bulk_download(symbols: tuple, start: str, end: str) -> dict:
    """
    מוריד OHLCV היסטורי לכל הסימבולים בקריאת yf.download אחת.
    מחזיר dict: {symbol: DataFrame(OHLCV)}
    """
    syms = list(symbols) + ["SPY"]
    syms = list(set(syms))
    try:
        raw = yf.download(
            syms, start=start, end=end,
            auto_adjust=True, group_by="ticker",
            progress=False, threads=True,
        )
    except Exception as e:
        logger.error(f"bulk_download error: {e}")
        return {}

    result = {}
    for sym in syms:
        try:
            if len(syms) == 1:
                df = raw.copy()
            else:
                df = raw[sym].copy() if sym in raw.columns.get_level_values(0) else pd.DataFrame()
            df = df.dropna(subset=["Close"])
            if len(df) >= 60:
                result[sym] = df
        except Exception:
            pass
    return result


# ────────────────────────────────────────────────────────────────────
# 2. אינדיקטורים — מחושבים על כל הסדרה מראש, ללא API נוסף
# ────────────────────────────────────────────────────────────────────

def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs    = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """מחזיר DataFrame עם כל האינדיקטורים לכל יום."""
    close  = df["Close"]
    volume = df["Volume"] if "Volume" in df.columns else pd.Series(1, index=df.index)

    out = pd.DataFrame(index=df.index)
    out["close"]       = close
    out["rsi"]         = _rsi(close)
    out["ma50"]        = close.rolling(50).mean()
    out["ma200"]       = close.rolling(200).mean()
    out["ma50_20d_ago"]= close.rolling(50).mean().shift(20)
    out["vol_avg20"]   = volume.rolling(20).mean()
    out["vol_ratio"]   = volume / (out["vol_avg20"] + 1e-9)
    out["ret_5d"]      = close.pct_change(5) * 100
    out["ret_20d"]     = close.pct_change(20) * 100
    out["atr"]         = (df["High"] - df["Low"]).rolling(14).mean() if "High" in df.columns else 0
    return out.dropna()


# ────────────────────────────────────────────────────────────────────
# 3. סיגנל קנייה — אותם חוקים כמו ה-val_agent האמיתי
# ────────────────────────────────────────────────────────────────────

def _buy_signal(row: pd.Series) -> int:
    """
    מחזיר ציון 0-4. קנייה רק אם ציון >= 2.
    חוקים: RSI, MA50 trend, Volume, Momentum
    """
    score = 0
    if 25 < row["rsi"] < 48:                          score += 1
    if row["close"] > row["ma50"]:                     score += 1
    if row["ma50"] > row["ma50_20d_ago"]:              score += 1
    if row["vol_ratio"] >= 0.7:                        score += 1
    return score


# ────────────────────────────────────────────────────────────────────
# 4. לולאת Backtest — מדמה את ה-val_agent על נתונים היסטוריים
# ────────────────────────────────────────────────────────────────────

def run_backtest(
    data: dict,
    symbols: list,
    start: str,
    end: str,
    tp: float    = DEFAULT_TP,
    sl: float    = DEFAULT_SL,
    te: int      = DEFAULT_TE,
    capital: float = 100_000.0,
    label: str   = "",
) -> dict:
    """
    מריץ את אסטרטגיית ה-val_agent על נתונים היסטוריים.
    מחזיר dict עם: equity_curve, trades, metrics.
    """
    # חשב אינדיקטורים לכל סימבול
    indicators = {}
    for sym in symbols:
        if sym in data and not data[sym].empty:
            try:
                indicators[sym] = _compute_indicators(data[sym])
            except Exception:
                pass

    # benchmark SPY
    spy_ind = _compute_indicators(data["SPY"]) if "SPY" in data else None

    # מצא ימי מסחר משותפים
    all_dates = None
    for ind in indicators.values():
        dates = ind.loc[start:end].index
        all_dates = dates if all_dates is None else all_dates.intersection(dates)
    if all_dates is None or len(all_dates) < 20:
        return {}
    all_dates = sorted(all_dates)

    # ── סימולציה ────────────────────────────────────────────────
    cash      = capital
    portfolio = {}   # {sym: {qty, buy_price, buy_date, trail_high}}
    trades    = []
    equity_curve = []

    for day in all_dates:
        day_str = str(day.date())

        # ── בדוק יציאות קודם ─────────────────────────────────
        to_sell = []
        for sym, pos in portfolio.items():
            if sym not in indicators:
                continue
            ind = indicators[sym]
            if day not in ind.index:
                continue
            price = float(ind.loc[day, "close"])
            if price <= 0:
                continue

            # עדכן trailing high
            if price > pos["trail_high"]:
                pos["trail_high"] = price

            pnl_pct    = (price / pos["buy_price"] - 1) * 100
            trail_sl   = pos["trail_high"] * (1 - sl / 100)
            hold_days  = (day.date() - pos["buy_date"]).days

            reason = None
            if pnl_pct >= tp:
                reason = f"TP +{pnl_pct:.1f}%"
            elif price <= trail_sl:
                reason = f"SL {pnl_pct:.1f}%"
            elif hold_days >= te and pnl_pct < 2.0:
                reason = f"TE {hold_days}d {pnl_pct:.1f}%"

            if reason:
                sell_price = price * (1 - SLIPPAGE)
                cash += sell_price * pos["qty"] * (1 - COMMISSION)
                trades.append({
                    "date": day_str, "sym": sym,
                    "type": "SELL", "price": round(sell_price, 3),
                    "pnl_pct": round(pnl_pct, 2), "reason": reason,
                    "hold_days": hold_days,
                })
                to_sell.append(sym)

        for sym in to_sell:
            del portfolio[sym]

        # ── בדוק קניות ────────────────────────────────────────
        if len(portfolio) < MAX_POS:
            candidates = []
            for sym in symbols:
                if sym in portfolio or sym not in indicators:
                    continue
                ind = indicators[sym]
                if day not in ind.index:
                    continue
                row   = ind.loc[day]
                score = _buy_signal(row)
                if score >= 2:
                    candidates.append((score, sym, float(row["close"])))

            candidates.sort(reverse=True)
            for score, sym, price in candidates:
                if len(portfolio) >= MAX_POS:
                    break
                if price <= 0:
                    continue
                alloc      = min(cash * ALLOC_PCT, cash / max(1, MAX_POS - len(portfolio)))
                buy_price  = price * (1 + SLIPPAGE)
                qty        = alloc / buy_price
                cost       = buy_price * qty * (1 + COMMISSION)
                if cost > cash:
                    continue
                cash -= cost
                portfolio[sym] = {
                    "qty":       qty,
                    "buy_price": buy_price,
                    "buy_date":  day.date(),
                    "trail_high": buy_price,
                }
                trades.append({
                    "date": day_str, "sym": sym,
                    "type": "BUY", "price": round(buy_price, 3),
                    "score": score, "pnl_pct": 0,
                })

        # ── equity ביום זה ───────────────────────────────────
        pos_value = 0.0
        for sym, pos in portfolio.items():
            if sym in indicators and day in indicators[sym].index:
                pos_value += float(indicators[sym].loc[day, "close"]) * pos["qty"]
        total = cash + pos_value
        equity_curve.append({"date": day_str, "equity": round(total, 2)})

    # ── SPY Benchmark ─────────────────────────────────────────
    spy_curve = []
    if spy_ind is not None:
        spy_window = spy_ind.loc[start:end]
        if not spy_window.empty:
            spy_start = float(spy_window["close"].iloc[0])
            spy_qty   = capital / spy_start
            for day in all_dates:
                if day in spy_window.index:
                    spy_val = float(spy_window.loc[day, "close"]) * spy_qty
                    spy_curve.append({"date": str(day.date()), "equity": round(spy_val, 2)})

    # ── Metrics ───────────────────────────────────────────────
    eq   = pd.DataFrame(equity_curve).set_index("date")["equity"]
    rets = eq.pct_change().dropna()

    final_equity   = float(eq.iloc[-1]) if len(eq) else capital
    total_return   = (final_equity / capital - 1) * 100
    sharpe         = float(rets.mean() / (rets.std() + 1e-9) * np.sqrt(252)) if len(rets) > 5 else 0
    peak           = eq.cummax()
    drawdown       = ((eq - peak) / peak * 100)
    max_dd         = float(drawdown.min())

    sell_trades    = [t for t in trades if t["type"] == "SELL"]
    wins           = [t for t in sell_trades if t["pnl_pct"] > 0]
    losses         = [t for t in sell_trades if t["pnl_pct"] <= 0]
    win_rate       = len(wins) / len(sell_trades) * 100 if sell_trades else 0
    avg_win        = float(np.mean([t["pnl_pct"] for t in wins]))   if wins   else 0
    avg_loss       = float(np.mean([t["pnl_pct"] for t in losses])) if losses else 0
    profit_factor  = abs(sum(t["pnl_pct"] for t in wins) /
                         sum(t["pnl_pct"] for t in losses)) if losses else 999

    spy_return = 0.0
    if spy_curve:
        spy_eq     = pd.DataFrame(spy_curve).set_index("date")["equity"]
        spy_return = (float(spy_eq.iloc[-1]) / capital - 1) * 100

    return {
        "label":         label or f"{start[:4]}–{end[:4]}",
        "start":         start,
        "end":           end,
        "capital":       capital,
        "final":         round(final_equity, 2),
        "total_return":  round(total_return, 2),
        "sharpe":        round(sharpe, 3),
        "max_dd":        round(max_dd, 2),
        "win_rate":      round(win_rate, 1),
        "avg_win":       round(avg_win, 2),
        "avg_loss":      round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor < 999 else 999,
        "total_trades":  len(sell_trades),
        "spy_return":    round(spy_return, 2),
        "alpha":         round(total_return - spy_return, 2),
        "equity_curve":  equity_curve,
        "spy_curve":     spy_curve,
        "trades":        trades,
    }


# ────────────────────────────────────────────────────────────────────
# 5. Walk-Forward — 4 חלונות זמן, כל אחד על נתונים שהמכונה לא ראתה
# ────────────────────────────────────────────────────────────────────

def run_walk_forward(data: dict, symbols: list, capital: float = 100_000.0,
                     tp: float = DEFAULT_TP, sl: float = DEFAULT_SL,
                     te: int = DEFAULT_TE) -> list:
    """
    מריץ את האסטרטגיה על 4 חלונות זמן עצמאיים.
    כל חלון = 12 חודשי בדיקה על נתונים שלא שימשו לכיול.
    """
    windows = [
        ("2020-01-01", "2020-12-31", "2020 (קורונה)"),
        ("2021-01-01", "2021-12-31", "2021 (שוק שורי)"),
        ("2022-01-01", "2022-12-31", "2022 (שוק דובי)"),
        ("2023-01-01", "2023-12-31", "2023 (התאוששות)"),
        ("2024-01-01", "2024-12-31", "2024 (AI בום)"),
    ]
    results = []
    for start, end, label in windows:
        r = run_backtest(data, symbols, start, end,
                         tp=tp, sl=sl, te=te, capital=capital, label=label)
        if r:
            results.append(r)
    return results
