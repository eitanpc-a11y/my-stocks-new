# logic.py - COMPLETE - All 28 columns needed by traders
# Cache strategy:
#   • Fundamentals (margins, ROE, debt, dividends…) → 24 hours  (change only quarterly)
#   • Technical    (price, RSI, MACD, MA…)          → 10 minutes (need to be fresh)
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import time
import logging
from datetime import datetime, timedelta
try:
    from api_cache import throttle as _throttle
except Exception:
    def _throttle(service, gap=0.4): time.sleep(gap)

logger = logging.getLogger(__name__)

try:
    from realtime_data import get_live_price_smart, get_time_series_twelve_data
    HAS_REALTIME = True
except Exception:
    HAS_REALTIME = False
    get_time_series_twelve_data = None


# ═══════════════════════════════════════════════════════════
# LAYER 1 — Fundamentals: cached 24 hours
#   Fetches only ticker.info (the heavy JSON request).
#   Company financials change quarterly — no need to re-fetch daily.
# ═══════════════════════════════════════════════════════════
@st.cache_data(ttl=86400)
def _fetch_fundamentals(ticker: str) -> dict:
    """Returns raw fundamental dict from yfinance .info  (cached 24 h).
    throttle משותף עם api_cache — מונע 429 כשhit קאש פג לכל 50+ סימבולים."""
    _throttle("yfinance", 0.35)
    try:
        info = yf.Ticker(ticker).info or {}
        return {
            "div_yield":   float(info.get("dividendYield", 0) or 0) * 100,
            "margin":      float(info.get("profitMargins", 0) or 0) * 100,
            "roe":         float(info.get("returnOnEquity", 0) or 0) * 100,
            "earn_growth": float(info.get("earningsGrowth", 0) or 0) * 100,
            "rev_growth":  float(info.get("revenueGrowth", 0) or 0) * 100,
            "payout":      float(info.get("payoutRatio", 0) or 0) * 100,
            "cash":        float(info.get("totalCash", 0) or 0),
            "debt":        float(info.get("totalDebt", 0) or 0),
            "insider":     float(info.get("heldPercentInsiders", 0) or 0) * 100,
            "target_px":   float(info.get("targetMeanPrice", 0) or 0),
            "eps":         float(info.get("trailingEps", 0) or 0),
            "earnings_date": info.get("earningsDate"),
        }
    except Exception:
        return {
            "div_yield": 0, "margin": 0, "roe": 0, "earn_growth": 0,
            "rev_growth": 0, "payout": 0, "cash": 0, "debt": 0,
            "insider": 0, "target_px": 0, "eps": 0, "earnings_date": None,
        }


# ═══════════════════════════════════════════════════════════
# LAYER 2 — Price & Technicals: cached 10 minutes
#   Fetches OHLCV history and calculates RSI, MACD, MA, etc.
#   10 minutes is fast enough for both value and day agents.
# ═══════════════════════════════════════════════════════════
@st.cache_data(ttl=600)
def _fetch_technical(ticker: str) -> dict | None:
    """Returns price + all technical indicators (cached 10 min).
    throttle משותף — גם טעינת האפליקציה וגם הסוכן האוטומטי חולקים את אותו מגבלת קצב."""
    try:
        _throttle("yfinance", 0.35)

        # Live price
        if HAS_REALTIME:
            price = get_live_price_smart(ticker)
        else:
            h0 = yf.Ticker(ticker).history(period="2d")
            price = float(h0["Close"].iloc[-1]) if not h0.empty else None

        if not price or price <= 0:
            return None

        # History
        ticker_obj = yf.Ticker(ticker)
        hist = None
        if HAS_REALTIME and get_time_series_twelve_data:
            try:
                hist = get_time_series_twelve_data(ticker, outputsize=300)
            except Exception:
                hist = None
        if hist is None or hist.empty:
            hist = ticker_obj.history(period="1y")

        if hist is None or hist.empty or len(hist) < 50:
            return None

        close  = hist["Close"]
        volume = int(hist["Volume"].iloc[-1]) if len(hist) > 0 else 0

        rsi      = _calc_rsi(close)
        ma50     = float(close.rolling(50).mean().iloc[-1])
        ma200    = float(close.rolling(200).mean().iloc[-1])
        change   = ((close.iloc[-1] / close.iloc[-2]) - 1) * 100 if len(close) > 1  else 0
        ret_5d   = ((close.iloc[-1] / close.iloc[-5]) - 1) * 100 if len(close) >= 5  else 0
        ret_20d  = ((close.iloc[-1] / close.iloc[-20]) - 1) * 100 if len(close) >= 20 else 0
        bb_width   = _calc_bb_width(close)
        macd       = _calc_macd(close)
        momentum   = _calc_momentum(close)
        volatility = float(close.pct_change().std() * np.sqrt(252)) * 100
        vol_ratio  = volume / hist["Volume"].mean() if hist["Volume"].mean() > 0 else 0
        candle_body = close.iloc[-1] - hist["Open"].iloc[-1] if len(hist) > 0 else 0
        gap        = hist["Open"].iloc[-1] - close.iloc[-2] if len(close) > 1 else 0

        return {
            "price":       float(price),
            "change":      round(float(change), 2),
            "rsi":         round(float(rsi), 1),
            "ma50":        round(float(ma50), 2),
            "ma200":       round(float(ma200), 2),
            "above_ma50":  1 if close.iloc[-1] > ma50  else 0,
            "above_ma200": 1 if close.iloc[-1] > ma200 else 0,
            "ret_5d":      round(float(ret_5d), 2),
            "ret_20d":     round(float(ret_20d), 2),
            "bb_width":    round(float(bb_width), 2),
            "macd":        round(float(macd), 2),
            "momentum":    round(float(momentum), 2),
            "volatility":  round(float(volatility), 2),
            "vol_ratio":   round(float(vol_ratio), 2),
            "candle_body": round(float(candle_body), 2),
            "gap":         round(float(gap), 2),
            "volume":      volume,
        }
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
# COMBINER — merges both layers into the full 28-column row
#   No separate cache here — each layer is already cached.
# ═══════════════════════════════════════════════════════════
def _fetch_single_symbol_cached(ticker: str) -> dict | None:
    """Combines fundamentals (24 h cache) + technicals (10 min cache)."""
    tech = _fetch_technical(ticker)
    if tech is None:
        return None

    fund = _fetch_fundamentals(ticker)
    price = tech["price"]

    currency    = "ILS" if str(ticker).endswith(".TA") else "USD"
    price_str   = f"{currency}{price:,.2f}"
    cash        = fund["cash"]
    debt        = fund["debt"]
    cash_vs_debt = "✅" if cash > debt else "❌"
    zero_debt   = 1 if debt == 0 else 0

    eps         = fund["eps"]
    fair_value  = eps * 20 if eps > 0 else price
    target_px   = fund["target_px"]
    target_upside = ((target_px / price) - 1) * 100 if price > 0 and target_px > 0 else 0

    # Safety score
    safety = 0
    if cash > debt:             safety += 2
    if debt == 0:               safety += 2
    if fund["div_yield"] > 2:   safety += 1
    if fund["payout"] < 60:     safety += 1

    # DaysToEarnings
    ed = fund["earnings_date"]
    try:
        days_to_earnings = (ed - datetime.now()).days if ed else 180
        if days_to_earnings < 0:
            days_to_earnings = 180
    except Exception:
        days_to_earnings = 180

    # Score (fundamental quality)
    score = 0
    if fund["rev_growth"]  >= 10: score += 1
    if fund["earn_growth"] >= 10: score += 1
    if fund["margin"]      >= 10: score += 1
    if fund["roe"]         >= 15: score += 1
    if cash > debt:               score += 1

    if score >= 5:
        action   = "קנייה חזקה 💎"
        ai_logic = f"ציון {score}/5: גדילה חזקה, רווחיות, איזון נקי"
    elif score >= 3:
        action   = "קנייה 📈"
        ai_logic = f"ציון {score}/5: בעל כמה מהתכונות החיוביות"
    elif score >= 1:
        action   = "החזק ⚖️"
        ai_logic = f"ציון {score}/5: נייטרלי או ממתין לשיפור"
    else:
        action   = "בבדיקה 🔍"
        ai_logic = "ציון 0/5: יש לבדוק את הנתונים"

    return {
        # Basic
        "Symbol":    ticker,
        "Price":     price,
        "PriceStr":  price_str,
        "Currency":  currency,
        "Change":    tech["change"],

        # Technical
        "RSI":         tech["rsi"],
        "rsi":         tech["rsi"],
        "MA50":        tech["ma50"],
        "MA200":       tech["ma200"],
        "above_ma50":  tech["above_ma50"],
        "above_ma200": tech["above_ma200"],

        # Price returns
        "ret_5d":  tech["ret_5d"],
        "ret_20d": tech["ret_20d"],

        # Advanced technical
        "bb_width":    tech["bb_width"],
        "macd":        tech["macd"],
        "momentum":    tech["momentum"],
        "volatility":  tech["volatility"],
        "vol_ratio":   tech["vol_ratio"],
        "candle_body": tech["candle_body"],
        "gap":         tech["gap"],

        # Fundamentals
        "DivYield":    round(fund["div_yield"], 2),
        "Margin":      round(fund["margin"], 2),
        "ROE":         round(fund["roe"], 2),
        "EarnGrowth":  round(fund["earn_growth"], 2),
        "RevGrowth":   round(fund["rev_growth"], 2),
        "InsiderHeld": round(fund["insider"], 2),
        "PayoutRatio": round(fund["payout"], 2),
        "CashVsDebt":  cash_vs_debt,
        "ZeroDebt":    zero_debt,
        "Safety":      safety,

        # Valuation
        "FairValue":    round(fair_value, 2),
        "TargetUpside": round(target_upside if target_upside > 0 else 15, 2),

        # Other
        "Score":          score,
        "DaysToEarnings": int(days_to_earnings),
        "Action":         action,
        "AI_Logic":       ai_logic,
    }


# ─── Technical helpers ────────────────────────────────────────────────────────
def _calc_rsi(prices, period=14):
    delta = prices.diff()
    gain  = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs    = gain / loss
    rsi   = 100 - (100 / (1 + rs))
    v = rsi.iloc[-1]
    return float(v) if not (v is np.nan or np.isnan(v)) else 50.0

def _calc_bb_width(prices, period=20):
    sma   = prices.rolling(window=period).mean()
    std   = prices.rolling(window=period).std()
    width = (sma + std * 2) - (sma - std * 2)
    return float(width.iloc[-1]) if len(width) > 0 else 0

def _calc_macd(prices, fast=12, slow=26):
    macd = prices.ewm(span=fast).mean() - prices.ewm(span=slow).mean()
    return float(macd.iloc[-1]) if len(macd) > 0 else 0

def _calc_momentum(prices, period=10):
    return float(prices.iloc[-1] - prices.iloc[-period]) if len(prices) > period else 0


# ─── Public API ───────────────────────────────────────────────────────────────
def fetch_master_data(tickers=None, max_workers: int = 3) -> pd.DataFrame:
    """Fetch master data with ALL 28 columns — fundamentals cached 24 h, technicals 10 min."""
    if not tickers:
        return pd.DataFrame()
    if isinstance(tickers, str):
        tickers = [tickers]
    tickers = list(set(tickers))

    results = []
    for ticker in tickers:
        try:
            result = _fetch_single_symbol_cached(ticker)
            if result:
                results.append(result)
        except Exception as e:
            logger.error(f"Error fetching {ticker}: {e}")

    return pd.DataFrame(results) if results else pd.DataFrame()
