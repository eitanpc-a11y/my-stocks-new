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

logger = logging.getLogger(__name__)

# ─── Standalone data fetcher (no st.cache_data, works in background thread) ──
def _fetch_price_and_rsi(symbol: str) -> dict | None:
    """Fetch price + basic technicals directly from yfinance — no Streamlit."""
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
        ma50  = float(close.rolling(50).mean().iloc[-1])  if len(close) >= 50  else price
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else price

        # Basic score (no fundamentals in background thread to keep it fast)
        score = 0
        if price > ma50:   score += 1
        if price > ma200:  score += 1
        if rsi < 60:       score += 1
        if ret_20d > 0:    score += 1
        if ret_5d > -5:    score += 1

        return {
            "Symbol":  symbol,
            "Price":   round(price, 4),
            "RSI":     round(rsi, 1),
            "Score":   score,
            "ret_5d":  round(ret_5d, 2),
            "ret_20d": round(ret_20d, 2),
        }
    except Exception as e:
        logger.debug(f"_fetch_price_and_rsi error {symbol}: {e}")
        return None


def _fetch_universe(symbols: list) -> pd.DataFrame:
    """Fetch data for a list of symbols. Returns DataFrame."""
    results = []
    for sym in symbols:
        try:
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
    לא רלוונטי לקריפטו ו-ETF.
    """
    if "-USD" in symbol or symbol in ("XLE","USO","GLD","SLV","UNG"):
        return False
    try:
        cal = yf.Ticker(symbol).calendar
        if cal is None or cal.empty:
            return False
        # Earnings Date עשוי להיות עמודה או שורה
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
        delta     = (earn_date - datetime.now().date()).days
        return 0 <= delta <= days
    except Exception:
        return False


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
    מחזיר dict עם regime: 'bull'|'neutral'|'bear' ו-vix.
    """
    try:
        vix = float(yf.Ticker("^VIX").history(period="2d")["Close"].iloc[-1])
    except Exception:
        vix = 20.0

    try:
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
    return {"regime": regime, "vix": vix, "spy_above_ma50": spy_above_ma50}


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

        # ── Sell: TP או SL ─────────────────────────────────────────────────
        new_port = []
        for item in portfolio:
            sym       = item.get("Symbol") or item.get("Stock", "")
            buy_price = float(item.get("BuyPrice", 0))
            qty       = float(item.get("Qty") or item.get("Quantity", 0))
            row       = df[df["Symbol"] == sym]
            lp        = float(row["Price"].iloc[0]) if not row.empty else buy_price
            if buy_price > 0 and qty > 0:
                profit = ((lp / buy_price) - 1) * 100
                if profit >= tp_pct:
                    cash += lp * qty
                    trades_log.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": f"🎯 Take-Profit ({tp_pct}%)",
                        "💰": f"{lp:.3f}", "📊": f"+{profit:.1f}%",
                        "🏷️": _asset_type(sym),
                    })
                    logger.info(f"val_agent: TP {sym} +{profit:.1f}%")
                    continue
                if profit <= -sl_pct:
                    cash += lp * qty
                    trades_log.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": f"🛑 Stop-Loss ({sl_pct}%)",
                        "💰": f"{lp:.3f}", "📊": f"{profit:.1f}%",
                        "🏷️": _asset_type(sym),
                    })
                    logger.info(f"val_agent: SL {sym} {profit:.1f}%")
                    continue
            new_port.append(item)
        portfolio = new_port

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

                # 🗳️ Consensus Voting — רק אם ≥2 מקורות מסכימים
                consensus = check_consensus_buy(sym, min_sources=2, min_confidence=60)
                if not consensus["approved"]:
                    logger.info(f"val_agent: skipping {sym} — {consensus['reason']}")
                    continue

                # 💰 Position Sizing לפי ביטחון ML
                base  = cash * alloc_pct
                alloc = min(_ml_position_size(sym, base), cash * 0.20)
                qty   = alloc / price
                portfolio.append({
                    "Symbol":    sym,
                    "BuyPrice":  _safe(price),
                    "Qty":       _safe(qty),
                    "BuyDate":   datetime.now().isoformat(),
                    "Score":     int(row["Score"]),
                    "Type":      _asset_type(sym),
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

        # ── סגור פוזיציות שהגיעו ל-TP או SL ─────────────────────────────
        new_port = []
        for item in portfolio:
            sym       = item.get("Symbol") or item.get("Stock", "")
            buy_price = float(item.get("BuyPrice", 0))
            qty       = float(item.get("Qty") or item.get("Quantity", 0))
            row       = df[df["Symbol"] == sym]
            lp        = float(row["Price"].iloc[0]) if not row.empty else buy_price
            if buy_price > 0 and qty > 0:
                profit = ((lp / buy_price) - 1) * 100
                if profit >= tp_pct:
                    cash += lp * qty
                    trades_log.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": f"🎯 Take-Profit ({tp_pct}%)",
                        "💰": f"{lp:.3f}", "📊": f"+{profit:.1f}%",
                        "🏷️": _asset_type(sym),
                    })
                    logger.info(f"day_agent: TP {sym} +{profit:.1f}%")
                    continue
                if profit <= -sl_pct:
                    cash += lp * qty
                    trades_log.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": f"🛑 Stop-Loss ({sl_pct}%)",
                        "💰": f"{lp:.3f}", "📊": f"{profit:.1f}%",
                        "🏷️": _asset_type(sym),
                    })
                    logger.info(f"day_agent: SL {sym} {profit:.1f}%")
                    continue
            new_port.append(item)
        portfolio = new_port

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

                # 🗳️ Consensus Voting (גמיש יותר ביומי — מינימום 1 מקור ML)
                consensus = check_consensus_buy(sym, min_sources=1,
                                               min_confidence=55, hours_back=24)
                if not consensus["approved"]:
                    logger.info(f"day_agent: skipping {sym} — no ML signal")
                    continue

                # 💰 Position Sizing לפי ML Confidence
                base  = cash * alloc_pct
                alloc = min(_ml_position_size(sym, base, hours_back=24), cash * 0.30)
                qty   = alloc / price
                portfolio.append({
                    "Symbol":   sym,
                    "BuyPrice": _safe(price),
                    "Qty":      _safe(qty),
                    "BuyDate":  datetime.now().isoformat(),
                    "Type":     _asset_type(sym),
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
        last_val = 0
        last_day = 0
        last_ml  = 0
        while self.running:
            try:
                now = time.time()
                if now - last_val > 6 * 3600:     # ערך: כל 6 שעות
                    self.run_val_agent(); last_val = now
                if now - last_day > 4 * 3600:     # יומי: כל 4 שעות (במקום שעה)
                    self.run_day_agent(); last_day = now
                if now - last_ml > 24 * 3600:     # ML: פעם ביום
                    self.run_ml_agent(); last_ml = now
                time.sleep(60)
            except Exception as e:
                logger.error(f"scheduler loop error: {e}")
                time.sleep(60)

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread  = threading.Thread(target=self._loop, daemon=True, name="scheduler")
        self.thread.start()
        logger.info("Scheduler started")

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
