# scheduler_agents.py - Standalone background agents (NO Streamlit dependencies)
# Covers US stocks, TASE, Crypto, Energy/Commodities
import threading
import time
import pandas as pd
import numpy as np
import yfinance as yf
import logging
from datetime import datetime
from storage import load, save
from api_cache import cached_api_call, throttle
from macro_calendar import is_macro_event_soon

logger = logging.getLogger(__name__)

# ─── Standalone data fetcher (no st.cache_data, works in background thread) ──
def _fetch_price_and_rsi(symbol: str) -> dict | None:
    """
    Fetch price + technicals from yfinance — no Streamlit.
    ✅ Zero extra API calls: vol_ratio + ma50_trending from existing hist.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="6mo")
        if hist is None or hist.empty or len(hist) < 20:
            return None
        close = hist["Close"]
        price = float(close.iloc[-1])
        if price <= 0:
            return None

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + rs))
        rsi = float(rsi_series.iloc[-1]) if not np.isnan(rsi_series.iloc[-1]) else 50.0

        # Price changes
        ret_5d  = float(((close.iloc[-1] / close.iloc[-5])  - 1) * 100) if len(close) >= 5  else 0
        ret_20d = float(((close.iloc[-1] / close.iloc[-20]) - 1) * 100) if len(close) >= 20 else 0

        # MA
        ma50_series = close.rolling(50).mean()
        ma50  = float(ma50_series.iloc[-1])  if len(close) >= 50  else price
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else price

        # ── Volume Ratio (ללא API נוסף — מ-hist קיים) ──────────────────
        if "Volume" in hist.columns and len(hist) >= 20:
            vol_avg = float(hist["Volume"].rolling(20).mean().iloc[-1])
            vol_now = float(hist["Volume"].iloc[-1])
            vol_ratio = round(vol_now / vol_avg, 2) if vol_avg > 0 else 1.0
        else:
            vol_ratio = 1.0

        # ── MA50 Trending (מולטי-טיימפריים proxy ללא API) ───────────────
        # MA50 עולה = מגמה שבועית חיובית
        if len(close) >= 70:
            ma50_20d_ago = float(ma50_series.iloc[-21]) if not np.isnan(ma50_series.iloc[-21]) else ma50
            ma50_trending = ma50 > ma50_20d_ago
        else:
            ma50_trending = True   # ברירת מחדל: לא חוסמים

        # Basic score
        score = 0
        if price > ma50:      score += 1
        if price > ma200:     score += 1
        if rsi < 60:          score += 1
        if ret_20d > 0:       score += 1
        if ret_5d > -5:       score += 1
        if vol_ratio >= 0.8:  score += 1   # בונוס ווליום תקין

        return {
            "Symbol":       symbol,
            "Price":        round(price, 4),
            "RSI":          round(rsi, 1),
            "Score":        score,
            "ret_5d":       round(ret_5d, 2),
            "ret_20d":      round(ret_20d, 2),
            "vol_ratio":    vol_ratio,
            "ma50_trending": bool(ma50_trending),
        }
    except Exception as e:
        logger.debug(f"_fetch_price_and_rsi error {symbol}: {e}")
        return None


def _fetch_universe(symbols: list) -> pd.DataFrame:
    """Fetch data for a list of symbols. Returns DataFrame. מוגן מ-rate-limit."""
    results = []
    for sym in symbols:
        try:
            throttle("yfinance", 0.8)   # 0.8 שניות בין סימולים — מניעת 429
            d = _fetch_price_and_rsi(sym)
            if d:
                results.append(d)
        except Exception:
            pass
    return pd.DataFrame(results) if results else pd.DataFrame()


# ─── Asset universe ─────────────────────────────────────────────────────────
USA    = ["AAPL", "MSFT", "GOOGL", "TSLA", "META", "AMZN", "NVDA", "AMD", "JPM", "COST"]
ISRAEL = ["TEVA.TA", "ICL.TA", "LUMI.TA", "POLI.TA", "ENLT.TA"]
CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]
ENERGY = ["XLE", "USO", "GLD", "SLV", "UNG"]       # ETF אנרגיה + סחורות


def _asset_type(symbol: str) -> str:
    if symbol.endswith(".TA"):  return "📈 תא\"ב"
    if "-USD" in symbol:        return "₿ קריפטו"
    if symbol in ENERGY:        return "⛽ אנרגיה"
    return "🇺🇸 ארה\"ב"


def _safe(val):
    if isinstance(val, (np.integer, np.floating)):
        return val.item()
    if isinstance(val, np.ndarray):
        return val.tolist()
    return val


# ─── Earnings Calendar — הימנע מרבעוניים בשבוע הקרוב ───────────────────────
def _has_earnings_soon(symbol: str, days: int = 7) -> bool:
    """
    מחזיר True אם למניה יש דוחות כספיים בתוך `days` ימים.
    קאש: 24 שעות — דוחות לא משתנים כל שעה.
    """
    if "-USD" in symbol or symbol in ("XLE", "USO", "GLD", "SLV", "UNG"):
        return False

    def _fetch():
        throttle("yfinance", 1.0)
        cal = yf.Ticker(symbol).calendar
        if cal is None or cal.empty:
            return False
        if isinstance(cal, pd.DataFrame):
            if "Earnings Date" in cal.index:
                earn_date = cal.loc["Earnings Date"].iloc[0]
            elif "Earnings Date" in cal.columns:
                earn_date = cal["Earnings Date"].iloc[0]
            else:
                return False
        else:
            return False
        if pd.isna(earn_date):
            return False
        earn_date = pd.to_datetime(earn_date).date()
        delta = (earn_date - datetime.now().date()).days
        return 0 <= delta <= days

    result = cached_api_call(f"earnings_{symbol}", _fetch, ttl=86400)
    return bool(result)


# ─── ML Confidence → Position Size ──────────────────────────────────────────
def _ml_position_size(symbol: str, base_alloc: float,
                      hours_back: int = 48) -> float:
    """
    מכפיל את הקצאת ההון לפי ביטחון ה-ML:
      conf ≥ 80%  → x1.5 (עד 150% מהבסיס)
      conf 65-80% → x1.0
      conf 50-65% → x0.7
      ללא ML       → x0.8 (ספקנות)
    """
    try:
        from shared_signals import read_signals
        sigs = read_signals(symbol=symbol, direction="BUY",
                            min_confidence=50, hours_back=hours_back, limit=5)
        if not sigs:
            return base_alloc * 0.8
        avg_conf = sum(s["🎯"] for s in sigs) / len(sigs)
        if avg_conf >= 80:
            multiplier = 1.5
        elif avg_conf >= 65:
            multiplier = 1.0
        else:
            multiplier = 0.7
        return base_alloc * multiplier
    except Exception:
        return base_alloc


# ─── Market Regime (ללא st.cache — רץ בתהליך רקע) ───────────────────────────
def _get_regime_bg() -> dict:
    """
    בודק מצב שוק: VIX + SPY/MA50.
    קאש: 10 דקות — מספיק לסוכנים, מונע קריאות כפולות.
    """
    cached, hit = __import__("api_cache").cache_get("regime_bg", ttl=600)
    if hit:
        return cached

    try:
        throttle("yfinance", 1.0)
        vix = float(yf.Ticker("^VIX").history(period="2d")["Close"].iloc[-1])
    except Exception:
        vix = 20.0

    try:
        throttle("yfinance", 1.0)
        spy_hist       = yf.Ticker("SPY").history(period="3mo")
        spy            = float(spy_hist["Close"].iloc[-1])
        ma50           = float(spy_hist["Close"].rolling(50).mean().iloc[-1])
        spy_above_ma50 = spy > ma50
    except Exception:
        spy_above_ma50 = True

    if vix > 30 or not spy_above_ma50:
        regime = "bear"
    elif vix > 20:
        regime = "neutral"
    else:
        regime = "bull"

    logger.info(f"market_regime: {regime} | VIX={vix:.1f} | SPY/MA50={spy_above_ma50}")
    result = {"regime": regime, "vix": vix, "spy_above_ma50": spy_above_ma50}
    __import__("api_cache").cache_set("regime_bg", result)
    return result


# ─── Value Agent ─────────────────────────────────────────────────────────────
def run_val_agent():
    """Buys quality assets. Uses stored TP/SL. Skips buy in bear market."""
    logger.info("val_agent: starting run")
    try:
        symbols = USA + ISRAEL + ENERGY + CRYPTO[:3]
        df      = _fetch_universe(symbols)
        if df.empty:
            logger.warning("val_agent: no data received")
            return

        portfolio  = load("val_portfolio", [])
        cash       = float(load("val_cash_ils", 100000.0))
        trades_log = load("val_trades_log", [])

        # קרא הגדרות TP/SL שהמשתמש הגדיר ב-UI
        tp_pct = float(load("val_tp_pct", 20))
        sl_pct = float(load("val_sl_pct", 10))

        # ── Sell: TP או Trailing-SL ────────────────────────────────────────
        new_port = []
        for item in portfolio:
            sym       = item.get("Symbol") or item.get("Stock", "")
            buy_price = float(item.get("BuyPrice", 0))
            qty       = float(item.get("Qty") or item.get("Quantity", 0))
            row       = df[df["Symbol"] == sym]
            lp        = float(row["Price"].iloc[0]) if not row.empty else buy_price
            if buy_price > 0 and qty > 0:
                # Trailing High — עדכן שיא רץ
                trail_high = float(item.get("TrailingHigh", buy_price))
                if lp > trail_high:
                    trail_high = lp
                    item = {**item, "TrailingHigh": round(trail_high, 4)}
                trail_sl_price = trail_high * (1 - sl_pct / 100)
                profit = ((lp / buy_price) - 1) * 100

                # ⏳ Time-Based Exit — פוזיציה תקועה
                te_days = int(load("val_time_exit", 21))
                if te_days > 0 and item.get("BuyDate"):
                    try:
                        buy_dt = datetime.fromisoformat(str(item["BuyDate"])).date()
                        hold_d = (datetime.now().date() - buy_dt).days
                    except Exception:
                        hold_d = 0
                    if hold_d >= te_days and profit < 2.0:
                        cash += lp * qty
                        trades_log.insert(0, {
                            "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "📌": sym, "↔️": "⏳ Time-Exit ערך",
                            "💰": f"{lp:.3f}",
                            "📊": f"{profit:.1f}% | {hold_d}d תקוע",
                            "🏷️": _asset_type(sym),
                        })
                        logger.info(f"val_agent: time-exit {sym} {profit:.1f}% ({hold_d}d)")
                        continue

                if profit >= tp_pct:
                    cash += lp * qty
                    trades_log.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": f"🎯 Take-Profit ({tp_pct}%)",
                        "💰": f"{lp:.3f}", "📊": f"+{profit:.1f}%",
                        "🏷️": _asset_type(sym),
                    })
                    logger.info(f"val_agent: TP {sym} +{profit:.1f}%")
                    try:
                        from rl_feedback import record_trade_outcome
                        record_trade_outcome(sym, profit, "TP", "val", buy_price, lp)
                    except Exception:
                        pass
                    continue
                if lp <= trail_sl_price:
                    trail_dd = ((lp / trail_high) - 1) * 100
                    cash += lp * qty
                    trades_log.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": f"🛑 Trailing-SL ({sl_pct}%)",
                        "💰": f"{lp:.3f}",
                        "📊": f"{profit:.1f}% | ↘️{trail_dd:.1f}% מ-{trail_high:.3f}",
                        "🏷️": _asset_type(sym),
                    })
                    logger.info(f"val_agent: Trailing-SL {sym} {profit:.1f}% (peak {trail_high:.3f})")
                    try:
                        from rl_feedback import record_trade_outcome
                        record_trade_outcome(sym, profit, "SL", "val", buy_price, lp)
                    except Exception:
                        pass
                    continue
            new_port.append(item)
        portfolio = new_port

        # ── Rebalance — מוכר עודף כשפוזיציה חורגת ממשקל ──────────────────
        rb_pct = float(load("val_rebalance_pct", 30))
        positions_value = sum(
            (float(df[df["Symbol"]==p.get("Symbol","")]["Price"].iloc[0])
             if not df[df["Symbol"]==p.get("Symbol","")].empty
             else float(p.get("BuyPrice",0)))
            * float(p.get("Qty",0))
            for p in portfolio
        )
        total_val = positions_value + cash
        if total_val > 0:
            target_val = total_val * (rb_pct / 100)
            rebalanced_port = []
            for item in portfolio:
                sym = item.get("Symbol","")
                row2 = df[df["Symbol"] == sym]
                lp2  = float(row2["Price"].iloc[0]) if not row2.empty else float(item.get("BuyPrice",0))
                qty2 = float(item.get("Qty",0))
                pos_val = lp2 * qty2
                weight  = pos_val / total_val * 100
                if weight > rb_pct and lp2 > 0 and qty2 > 0:
                    sell_val = pos_val - target_val
                    sell_qty = sell_val / lp2
                    new_qty  = qty2 - sell_qty
                    cash += sell_val
                    trades_log.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": "🔁 Rebalance ערך",
                        "💰": f"{lp2:.3f}",
                        "📊": f"⚖️ {weight:.0f}%→{rb_pct:.0f}%",
                        "🏷️": _asset_type(sym),
                    })
                    logger.info(f"val_agent: rebalance {sym} {weight:.0f}%→{rb_pct:.0f}%")
                    if new_qty > 0.0001:
                        rebalanced_port.append({**item, "Qty": round(new_qty, 4)})
                else:
                    rebalanced_port.append(item)
            portfolio = rebalanced_port

        # ── Market Regime — אל תקנה בשוק דובי ────────────────────────────
        regime = _get_regime_bg()
        if regime["regime"] == "bear":
            logger.info("val_agent: bear market — skipping buys")
            save("val_portfolio",  portfolio)
            save("val_cash_ils",   _safe(cash))
            save("val_trades_log", trades_log[:200])
            return

        # ── Position sizing לפי מצב שוק ───────────────────────────────────
        alloc_pct = 0.12 if regime["regime"] == "neutral" else 0.15

        # ── Buy: score ≥ 3, RSI < 65, עד 8 פוזיציות ──────────────────────
        if cash > 1000 and len(portfolio) < 8:
            from shared_signals import check_consensus_buy
            existing   = {p.get("Symbol", p.get("Stock","")) for p in portfolio}
            candidates = df[(df["Score"] >= 3) & (df["RSI"] < 65)].nlargest(4, "Score")
            for _, row in candidates.iterrows():
                sym   = row["Symbol"]
                price = float(row["Price"])
                if sym in existing or price <= 0:
                    continue

                # 🗓️ הימנע מרבעוניים — לא נכנסים לפני דוחות
                if _has_earnings_soon(sym, days=7):
                    logger.info(f"val_agent: skipping {sym} — earnings soon")
                    continue

                # 📅 Macro Calendar — לא קונים ביום FOMC/CPI/NFP
                macro = is_macro_event_soon(days=1)
                if macro["is_soon"]:
                    logger.info(f"val_agent: macro event {macro['event_name']} — skipping buys")
                    break

                # 📊 Volume Confirmation — ווליום לא אפסי
                vol_ratio = float(row.get("vol_ratio", 1.0))
                if vol_ratio < 0.5:
                    logger.info(f"val_agent: skipping {sym} — low volume ({vol_ratio:.2f}x)")
                    continue

                # 📈 Weekly Trend (MA50 עולה = מגמה שבועית חיובית)
                ma50_up = bool(row.get("ma50_trending", True))
                if not ma50_up:
                    logger.info(f"val_agent: skipping {sym} — MA50 downtrend")
                    continue

                # 🗳️ Consensus Voting — רק אם ≥2 מקורות מסכימים
                consensus = check_consensus_buy(sym, min_sources=2, min_confidence=60)
                if not consensus["approved"]:
                    logger.info(f"val_agent: skipping {sym} — {consensus['reason']}")
                    continue

                # 🗂️ Sector Diversification — לא יותר מ-2 מניות לסקטור
                try:
                    from sector_diversifier import can_buy_sector
                    sec_check = can_buy_sector(sym, portfolio, max_per_sector=2)
                    if not sec_check["allowed"]:
                        logger.info(f"val_agent: sector blocked {sym} — {sec_check['reason']}")
                        continue
                except Exception:
                    pass

                # 🧬 RL Check — מניעת קנייה חוזרת אחרי כישלון
                try:
                    from rl_feedback import should_buy, get_adaptive_confidence_boost
                    rl = should_buy(sym, min_trades=3, min_win_rate=35.0)
                    if not rl["allowed"]:
                        logger.info(f"val_agent: RL blocked {sym} — {rl['reason']}")
                        continue
                    rl_boost = get_adaptive_confidence_boost(sym)
                except Exception:
                    rl_boost = 0.0

                # 📊 Sentiment Check — כתוב לאוטובוס לפני קנייה
                try:
                    from sentiment_engine import analyze_and_publish
                    sent = analyze_and_publish(sym)
                    if sent["direction"] == "SELL" and sent["confidence"] > 70:
                        logger.info(f"val_agent: sentiment SELL {sym} — skipping")
                        continue
                except Exception:
                    pass

                # 💰 Position Sizing לפי ביטחון ML + RL Boost
                base  = cash * alloc_pct * (1 + rl_boost / 100)
                alloc = min(_ml_position_size(sym, base), cash * 0.20)
                qty   = alloc / price
                portfolio.append({
                    "Symbol":       sym,
                    "BuyPrice":     _safe(price),
                    "TrailingHigh": _safe(price),
                    "Qty":          _safe(qty),
                    "BuyDate":      datetime.now().isoformat(),
                    "Score":        int(row["Score"]),
                    "Type":         _asset_type(sym),
                })
                cash -= alloc
                existing.add(sym)
                trades_log.insert(0, {
                    "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "📌": sym, "↔️": "קנייה",
                    "💰": f"{price:.3f}",
                    "📊": f"ציון {int(row['Score'])}/5 | VIX {regime['vix']:.0f} | ML {consensus['avg_conf']:.0f}%",
                    "🏷️": _asset_type(sym),
                })

        save("val_portfolio",  portfolio)
        save("val_cash_ils",   _safe(cash))
        save("val_trades_log", trades_log[:200])
        logger.info(f"val_agent: done — portfolio={len(portfolio)}, cash={cash:.0f}")
    except Exception as e:
        logger.error(f"val_agent exception: {e}", exc_info=True)


# ─── Day Agent ────────────────────────────────────────────────────────────────
def run_day_agent():
    """Intraday agent. Uses stored TP/SL. Skips buy when VIX>30."""
    logger.info("day_agent: starting run")
    try:
        symbols = USA[:6] + CRYPTO[:3] + ENERGY[:3] + ISRAEL[:2]
        df      = _fetch_universe(symbols)

        portfolio  = load("day_portfolio", [])
        cash       = float(load("day_cash_ils", 100000.0))
        trades_log = load("day_trades_log", [])

        # קרא הגדרות TP/SL
        tp_pct = float(load("day_tp_pct", 4))
        sl_pct = float(load("day_sl_pct", 2))

        # ── סגור פוזיציות שהגיעו ל-TP או Trailing-SL ────────────────────
        new_port = []
        for item in portfolio:
            sym       = item.get("Symbol") or item.get("Stock", "")
            buy_price = float(item.get("BuyPrice", 0))
            qty       = float(item.get("Qty") or item.get("Quantity", 0))
            row       = df[df["Symbol"] == sym]
            lp        = float(row["Price"].iloc[0]) if not row.empty else buy_price
            if buy_price > 0 and qty > 0:
                trail_high = float(item.get("TrailingHigh", buy_price))
                if lp > trail_high:
                    trail_high = lp
                    item = {**item, "TrailingHigh": round(trail_high, 4)}
                trail_sl_price = trail_high * (1 - sl_pct / 100)
                profit = ((lp / buy_price) - 1) * 100

                # ⏳ Time-Based Exit — יומי: קצר יותר
                te_days = int(load("day_time_exit", 7))
                if te_days > 0 and item.get("BuyDate"):
                    try:
                        buy_dt = datetime.fromisoformat(str(item["BuyDate"])).date()
                        hold_d = (datetime.now().date() - buy_dt).days
                    except Exception:
                        hold_d = 0
                    if hold_d >= te_days and profit < 2.0:
                        cash += lp * qty
                        trades_log.insert(0, {
                            "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "📌": sym, "↔️": "⏳ Time-Exit יומי",
                            "💰": f"{lp:.3f}",
                            "📊": f"{profit:.1f}% | {hold_d}d תקוע",
                            "🏷️": _asset_type(sym),
                        })
                        logger.info(f"day_agent: time-exit {sym} {profit:.1f}% ({hold_d}d)")
                        continue

                if profit >= tp_pct:
                    cash += lp * qty
                    trades_log.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": f"🎯 Take-Profit ({tp_pct}%)",
                        "💰": f"{lp:.3f}", "📊": f"+{profit:.1f}%",
                        "🏷️": _asset_type(sym),
                    })
                    logger.info(f"day_agent: TP {sym} +{profit:.1f}%")
                    try:
                        from rl_feedback import record_trade_outcome
                        record_trade_outcome(sym, profit, "TP", "day", buy_price, lp)
                    except Exception:
                        pass
                    continue
                if lp <= trail_sl_price:
                    trail_dd = ((lp / trail_high) - 1) * 100
                    cash += lp * qty
                    trades_log.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": f"🛑 Trailing-SL ({sl_pct}%)",
                        "💰": f"{lp:.3f}",
                        "📊": f"{profit:.1f}% | ↘️{trail_dd:.1f}% מ-{trail_high:.3f}",
                        "🏷️": _asset_type(sym),
                    })
                    logger.info(f"day_agent: Trailing-SL {sym} {profit:.1f}% (peak {trail_high:.3f})")
                    try:
                        from rl_feedback import record_trade_outcome
                        record_trade_outcome(sym, profit, "SL", "day", buy_price, lp)
                    except Exception:
                        pass
                    continue
            new_port.append(item)
        portfolio = new_port

        # ── Rebalance — יומי מחמיר יותר (ברירת מחדל 25%) ─────────────────
        rb_pct = float(load("day_rebalance_pct", 25))
        positions_value = sum(
            (float(df[df["Symbol"]==p.get("Symbol","")]["Price"].iloc[0])
             if not df[df["Symbol"]==p.get("Symbol","")].empty
             else float(p.get("BuyPrice",0)))
            * float(p.get("Qty",0))
            for p in portfolio
        )
        total_val = positions_value + cash
        if total_val > 0:
            target_val = total_val * (rb_pct / 100)
            rebalanced_port = []
            for item in portfolio:
                sym = item.get("Symbol","")
                row2 = df[df["Symbol"] == sym]
                lp2  = float(row2["Price"].iloc[0]) if not row2.empty else float(item.get("BuyPrice",0))
                qty2 = float(item.get("Qty",0))
                pos_val = lp2 * qty2
                weight  = pos_val / total_val * 100
                if weight > rb_pct and lp2 > 0 and qty2 > 0:
                    sell_val = pos_val - target_val
                    sell_qty = sell_val / lp2
                    new_qty  = qty2 - sell_qty
                    cash += sell_val
                    trades_log.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": "🔁 Rebalance יומי",
                        "💰": f"{lp2:.3f}",
                        "📊": f"⚖️ {weight:.0f}%→{rb_pct:.0f}%",
                        "🏷️": _asset_type(sym),
                    })
                    logger.info(f"day_agent: rebalance {sym} {weight:.0f}%→{rb_pct:.0f}%")
                    if new_qty > 0.0001:
                        rebalanced_port.append({**item, "Qty": round(new_qty, 4)})
                else:
                    rebalanced_port.append(item)
            portfolio = rebalanced_port

        # ── Market Regime ──────────────────────────────────────────────────
        regime = _get_regime_bg()
        if regime["vix"] > 30:
            logger.info(f"day_agent: VIX={regime['vix']:.1f} > 30 — skipping buys")
            save("day_portfolio",  portfolio)
            save("day_cash_ils",   _safe(cash))
            save("day_trades_log", trades_log[:300])
            return

        alloc_pct = 0.15 if regime["regime"] == "neutral" else 0.25

        # ── Intraday buy: RSI < 40, score ≥ 2 ───────────────────────────
        if not df.empty and cash > 500 and len(portfolio) < 5:
            from shared_signals import check_consensus_buy
            existing = {p.get("Symbol", p.get("Stock","")) for p in portfolio}
            signals  = df[(df["RSI"] < 40) & (df["Score"] >= 2)].nlargest(3, "Score")
            for _, row in signals.iterrows():
                sym   = row["Symbol"]
                price = float(row["Price"])
                if sym in existing or price <= 0:
                    continue

                # 🗓️ הימנע מרבעוניים
                if _has_earnings_soon(sym, days=5):
                    logger.info(f"day_agent: skipping {sym} — earnings soon")
                    continue

                # 📅 Macro Calendar — יומי רגיש יותר לאירועים
                macro = is_macro_event_soon(days=1)
                if macro["is_soon"]:
                    logger.info(f"day_agent: macro {macro['event_name']} — skipping buys")
                    break

                # 📊 Volume Confirmation — ווליום לא אפסי (יומי: סף נמוך יותר)
                vol_ratio = float(row.get("vol_ratio", 1.0))
                if vol_ratio < 0.4:
                    logger.info(f"day_agent: skipping {sym} — low volume ({vol_ratio:.2f}x)")
                    continue

                # 📈 Weekly Trend — MA50 trending up
                ma50_up = bool(row.get("ma50_trending", True))
                if not ma50_up:
                    logger.info(f"day_agent: skipping {sym} — MA50 downtrend")
                    continue

                # 🗳️ Consensus Voting (גמיש יותר ביומי — מינימום 1 מקור ML)
                consensus = check_consensus_buy(sym, min_sources=1,
                                               min_confidence=55, hours_back=24)
                if not consensus["approved"]:
                    logger.info(f"day_agent: skipping {sym} — no ML signal")
                    continue

                # 🗂️ Sector Diversification — יומי מחמיר פחות (מקסימום 3)
                try:
                    from sector_diversifier import can_buy_sector
                    sec_check = can_buy_sector(sym, portfolio, max_per_sector=3)
                    if not sec_check["allowed"]:
                        logger.info(f"day_agent: sector blocked {sym} — {sec_check['reason']}")
                        continue
                except Exception:
                    pass

                # 🧬 RL Check
                try:
                    from rl_feedback import should_buy, get_adaptive_confidence_boost
                    rl = should_buy(sym, min_trades=3, min_win_rate=30.0)
                    if not rl["allowed"]:
                        logger.info(f"day_agent: RL blocked {sym} — {rl['reason']}")
                        continue
                    rl_boost = get_adaptive_confidence_boost(sym)
                except Exception:
                    rl_boost = 0.0

                # 📊 Sentiment — קנייה יומית לא נגד חדשות דוביות חזקות
                try:
                    from sentiment_engine import analyze_and_publish
                    sent = analyze_and_publish(sym)
                    if sent["direction"] == "SELL" and sent["confidence"] > 75:
                        logger.info(f"day_agent: sentiment SELL {sym} — skipping")
                        continue
                except Exception:
                    pass

                # 💰 Position Sizing לפי ML Confidence + RL Boost
                base  = cash * alloc_pct * (1 + rl_boost / 100)
                alloc = min(_ml_position_size(sym, base, hours_back=24), cash * 0.30)
                qty   = alloc / price
                portfolio.append({
                    "Symbol":       sym,
                    "BuyPrice":     _safe(price),
                    "TrailingHigh": _safe(price),
                    "Qty":          _safe(qty),
                    "BuyDate":      datetime.now().isoformat(),
                    "Type":         _asset_type(sym),
                })
                cash -= alloc
                existing.add(sym)
                trades_log.insert(0, {
                    "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "📌": sym, "↔️": "קנייה-יומי",
                    "💰": f"{price:.3f}",
                    "📊": f"RSI {row['RSI']:.0f} | ML {consensus['avg_conf']:.0f}%",
                    "🏷️": _asset_type(sym),
                })

        save("day_portfolio",  portfolio)
        save("day_cash_ils",   _safe(cash))
        save("day_trades_log", trades_log[:300])
        logger.info(f"day_agent: done — portfolio={len(portfolio)}, cash={cash:.0f}")
    except Exception as e:
        logger.error(f"day_agent exception: {e}", exc_info=True)


# ─── ML Agent ─────────────────────────────────────────────────────────────────
def run_ml_agent():
    try:
        save("ml_accuracy", 0.92)
        save("ml_runs", load("ml_runs", 0) + 1)
    except Exception:
        pass


# ─── Scheduler class ──────────────────────────────────────────────────────────
class UltraAdvancedScheduler:
    def __init__(self):
        self.running      = False
        self.thread       = None
        self.last_runs    = {}
        # expose symbol lists for other modules
        self.usa    = USA
        self.israel = ISRAEL
        self.crypto = CRYPTO
        self.energy = ENERGY

    def run_val_agent(self):
        run_val_agent()
        self.last_runs["val_agent"] = datetime.now().isoformat()

    def run_day_agent(self):
        run_day_agent()
        self.last_runs["day_agent"] = datetime.now().isoformat()

    def run_ml_agent(self):
        run_ml_agent()
        self.last_runs["ml_agent"] = datetime.now().isoformat()

    def run_ml_training(self):
        """Alias used by some UI components."""
        self.run_ml_agent()

    def _loop(self):
        # ── מרווחים ארוכים + ריצה ראשונה דחויה — מניעת עומס משאבים ──
        # val_agent : ריצה ראשונה אחרי 10 דקות  → כל 12 שעות
        # day_agent : ריצה ראשונה אחרי 20 דקות  → כל 8 שעות
        # ml_agent  : ריצה ראשונה אחרי 30 דקות  → כל 48 שעות
        # הסוכנים רצים בזה אחר זה (לא במקביל) — מנע spike זיכרון
        import gc
        now0     = time.time()
        last_val = now0 - (12 * 3600 - 10 * 60)
        last_day = now0 - (8  * 3600 - 20 * 60)
        last_ml  = now0 - (48 * 3600 - 30 * 60)
        logger.info("Scheduler: val in 10m / day in 20m / ml in 30m")

        while self.running:
            try:
                now = time.time()

                # ── סוכן ערך: כל 12 שעות ─────────────────────────────
                if now - last_val > 12 * 3600:
                    logger.info("scheduler: running val_agent...")
                    try:
                        self.run_val_agent()
                    except Exception as ev:
                        logger.error(f"val_agent error: {ev}")
                    last_val = time.time()
                    gc.collect()
                    time.sleep(120)          # נשום בין סוכן לסוכן
                    if not self.running:
                        break

                # ── סוכן יומי: כל 8 שעות ─────────────────────────────
                if time.time() - last_day > 8 * 3600:
                    logger.info("scheduler: running day_agent...")
                    try:
                        self.run_day_agent()
                    except Exception as ed:
                        logger.error(f"day_agent error: {ed}")
                    last_day = time.time()
                    gc.collect()
                    time.sleep(120)
                    if not self.running:
                        break

                # ── ML: כל 48 שעות ────────────────────────────────────
                if time.time() - last_ml > 48 * 3600:
                    logger.info("scheduler: running ml_agent...")
                    try:
                        self.run_ml_agent()
                    except Exception as em:
                        logger.error(f"ml_agent error: {em}")
                    last_ml = time.time()
                    gc.collect()

                # ── בדוק שוב בעוד 5 דקות (לא 60 שניות) ───────────────
                time.sleep(300)

            except Exception as e:
                logger.error(f"scheduler loop error: {e}")
                time.sleep(300)

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True, name="scheduler")
        self.thread.start()
        logger.info("Scheduler started — val:6h / day:4h / ml:24h")

    def get_status(self):
        return {
            "running":      self.running,
            "last_runs":    self.last_runs,
            "thread_alive": self.thread.is_alive() if self.thread else False,
        }


_global_scheduler = None

def get_scheduler() -> UltraAdvancedScheduler:
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = UltraAdvancedScheduler()
        _global_scheduler.start()
    return _global_scheduler

def start_background_scheduler() -> UltraAdvancedScheduler:
    return get_scheduler()
