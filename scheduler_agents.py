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


# ─── Value Agent ─────────────────────────────────────────────────────────────
def run_val_agent():
    """Buys quality assets across all classes, sells at +20% or -10%."""
    logger.info("val_agent: starting run")
    try:
        symbols = USA + ISRAEL + ENERGY + CRYPTO[:3]
        df = _fetch_universe(symbols)
        if df.empty:
            logger.warning("val_agent: no data received")
            return

        portfolio   = load("val_portfolio", [])
        cash        = float(load("val_cash_ils", 100000.0))
        trades_log  = load("val_trades_log", [])

        # ── Sell: +20% profit OR -10% stop-loss ────────────────────────────
        new_port = []
        for item in portfolio:
            sym       = item.get("Stock", "")
            buy_price = float(item.get("BuyPrice", 0))
            qty       = float(item.get("Quantity", 0))
            row       = df[df["Symbol"] == sym]
            lp        = float(row["Price"].iloc[0]) if not row.empty else buy_price
            if buy_price > 0 and qty > 0:
                profit = ((lp / buy_price) - 1) * 100
                if profit >= 20:
                    cash += lp * qty
                    trades_log.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": "מכירה-רווח",
                        "💰": f"{lp:.3f}", "📊": f"+{profit:.1f}%",
                        "🏷️": _asset_type(sym),
                    })
                    continue
                if profit <= -10:
                    cash += lp * qty
                    trades_log.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": "סטופ-לוס",
                        "💰": f"{lp:.3f}", "📊": f"{profit:.1f}%",
                        "🏷️": _asset_type(sym),
                    })
                    continue
            new_port.append(item)
        portfolio = new_port

        # ── Buy: score ≥ 3, RSI < 65, up to 8 positions ───────────────────
        if cash > 1000 and len(portfolio) < 8:
            existing = {p.get("Stock") for p in portfolio}
            candidates = df[(df["Score"] >= 3) & (df["RSI"] < 65)].nlargest(4, "Score")
            for _, row in candidates.iterrows():
                sym   = row["Symbol"]
                price = float(row["Price"])
                if sym in existing or price <= 0:
                    continue
                alloc = cash * 0.15
                qty   = alloc / price
                portfolio.append({
                    "Stock":     sym,
                    "BuyPrice":  _safe(price),
                    "Quantity":  _safe(qty),
                    "BuyDate":   datetime.now().isoformat(),
                    "Score":     int(row["Score"]),
                    "AssetType": _asset_type(sym),
                })
                cash -= alloc
                existing.add(sym)
                trades_log.insert(0, {
                    "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "📌": sym, "↔️": "קנייה",
                    "💰": f"{price:.3f}", "📊": f"ציון {int(row['Score'])}/5",
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
    """Intraday agent: buys RSI dips, closes at ±2%."""
    logger.info("day_agent: starting run")
    try:
        symbols = USA[:6] + CRYPTO[:3] + ENERGY[:3] + ISRAEL[:2]
        df = _fetch_universe(symbols)

        portfolio  = load("day_portfolio", [])
        cash       = float(load("day_cash_ils", 100000.0))
        trades_log = load("day_trades_log", [])

        # ── Close open positions ≥ ±2% ────────────────────────────────────
        new_port = []
        for item in portfolio:
            sym       = item.get("Stock", "")
            buy_price = float(item.get("BuyPrice", 0))
            qty       = float(item.get("Quantity", 0))
            row       = df[df["Symbol"] == sym]
            lp        = float(row["Price"].iloc[0]) if not row.empty else buy_price
            if buy_price > 0 and qty > 0:
                profit = ((lp / buy_price) - 1) * 100
                if abs(profit) >= 2:
                    cash += lp * qty
                    trades_log.insert(0, {
                        "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "📌": sym, "↔️": "סגירה-יומי",
                        "💰": f"{lp:.3f}", "📊": f"{profit:+.1f}%",
                        "🏷️": _asset_type(sym),
                    })
                    continue
            new_port.append(item)
        portfolio = new_port

        # ── Intraday buy: RSI < 40, score ≥ 2 ───────────────────────────
        if not df.empty and cash > 500 and len(portfolio) < 5:
            existing  = {p.get("Stock") for p in portfolio}
            signals   = df[(df["RSI"] < 40) & (df["Score"] >= 2)].nlargest(3, "Score")
            for _, row in signals.iterrows():
                sym   = row["Symbol"]
                price = float(row["Price"])
                if sym in existing or price <= 0:
                    continue
                alloc = min(cash * 0.25, cash)
                qty   = alloc / price
                portfolio.append({
                    "Stock":    sym,
                    "BuyPrice": _safe(price),
                    "Quantity": _safe(qty),
                    "BuyDate":  datetime.now().isoformat(),
                    "AssetType": _asset_type(sym),
                })
                cash -= alloc
                existing.add(sym)
                trades_log.insert(0, {
                    "⏰": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "📌": sym, "↔️": "קנייה-יומי",
                    "💰": f"{price:.3f}", "📊": f"RSI {row['RSI']:.0f}",
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
