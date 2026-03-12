# logic.py - COMPLETE - All 28 columns needed by traders
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import time
import logging
from datetime import datetime, timedelta

# Setup logging
logger = logging.getLogger(__name__)

try:
    from realtime_data import get_live_price_smart, get_time_series_twelve_data
    HAS_REALTIME = True
except:
    HAS_REALTIME = False
    get_time_series_twelve_data = None

# Cache for 1 hour — reduces API calls dramatically on Streamlit Cloud
@st.cache_data(ttl=3600)
def _fetch_single_symbol_cached(ticker: str) -> dict | None:
    """Fetch ALL 28 columns that traders need"""
    try:
        time.sleep(0.05)  # Reduced from 0.2 seconds for faster UI response
        
        if HAS_REALTIME:
            price = get_live_price_smart(ticker)
        else:
            ticker_obj = yf.Ticker(ticker)
            hist = ticker_obj.history(period="1y")
            if hist.empty:
                return None
            price = float(hist["Close"].iloc[-1])
        
        if not price or price <= 0:
            return None
        
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info or {}

        # Try Twelve Data for history first, fall back to yfinance
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
        
        close = hist["Close"]
        volume = int(hist["Volume"].iloc[-1]) if len(hist) > 0 else 0
        
        # Technical indicators
        rsi = _calc_rsi(close)
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        
        # Price changes
        change = ((close.iloc[-1] / close.iloc[-2]) - 1) * 100 if len(close) > 1 else 0
        ret_5d = ((close.iloc[-1] / close.iloc[-5]) - 1) * 100 if len(close) >= 5 else 0
        ret_20d = ((close.iloc[-1] / close.iloc[-20]) - 1) * 100 if len(close) >= 20 else 0
        
        # Moving average crosses
        above_ma50 = 1 if close.iloc[-1] > ma50 else 0
        above_ma200 = 1 if close.iloc[-1] > ma200 else 0
        
        # Bollinger Bands
        bb_width = _calc_bb_width(close)
        
        # MACD
        macd = _calc_macd(close)
        
        # Momentum
        momentum = _calc_momentum(close)
        
        # Volatility
        volatility = float(close.pct_change().std() * np.sqrt(252)) * 100
        
        # Volume ratio
        vol_ratio = volume / hist["Volume"].mean() if hist["Volume"].mean() > 0 else 0
        
        # Candle body
        candle_body = close.iloc[-1] - hist["Open"].iloc[-1] if len(hist) > 0 else 0
        
        # Gap
        gap = hist["Open"].iloc[-1] - close.iloc[-2] if len(close) > 1 else 0
        
        # Financial metrics
        currency = "ILS" if str(ticker).endswith(".TA") else "USD"
        price_str = f"{currency}{price:,.2f}"
        
        insider = float(info.get("heldPercentInsiders", 0)) * 100
        target_price = float(info.get("targetMeanPrice", price))
        target_upside = ((target_price / price) - 1) * 100 if price > 0 else 0
        
        div_yield = float(info.get("dividendYield", 0)) * 100 if info.get("dividendYield") else 0
        margin = float(info.get("profitMargins", 0)) * 100 if info.get("profitMargins") else 0
        roe = float(info.get("returnOnEquity", 0)) * 100 if info.get("returnOnEquity") else 0
        earn_growth = float(info.get("earningsGrowth", 0)) * 100 if info.get("earningsGrowth") else 0
        rev_growth = float(info.get("revenueGrowth", 0)) * 100 if info.get("revenueGrowth") else 0
        payout = float(info.get("payoutRatio", 0)) * 100 if info.get("payoutRatio") else 0
        
        cash = float(info.get("totalCash", 0)) if info.get("totalCash") else 0
        debt = float(info.get("totalDebt", 0)) if info.get("totalDebt") else 0
        cash_vs_debt = "✅" if cash > debt else "❌"
        zero_debt = 1 if debt == 0 else 0
        
        # Fair Value (intrinsic value estimate)
        eps = info.get("trailingEps", 0) or 0
        pe_ratio = price / eps if eps > 0 else 0
        fair_value = eps * 20 if eps > 0 else price  # Simple: EPS * 20x
        
        # Safety score
        safety = 0
        if cash > debt: safety += 2
        if debt == 0: safety += 2
        if div_yield > 2: safety += 1
        if payout < 60: safety += 1
        
        # DaysToEarnings
        earnings_date = info.get("earningsDate")
        if earnings_date:
            try:
                days_to_earnings = (earnings_date - datetime.now()).days
                if days_to_earnings < 0:
                    days_to_earnings = 180
            except:
                days_to_earnings = 180
        else:
            days_to_earnings = 180
        
        # Score
        score = 0
        if rev_growth >= 10: score += 1
        if earn_growth >= 10: score += 1
        if margin >= 10: score += 1
        if roe >= 15: score += 1
        if cash > debt: score += 1
        
        # Target for long
        target = target_upside if target_upside > 0 else 15
        
        # AI Action Recommendation
        if score >= 5:
            action = "קנייה חזקה 💎"
            ai_logic = f"ציון {score}/5: גדילה חזקה, רווחיות, איזון נקי"
        elif score >= 3:
            action = "קנייה 📈"
            ai_logic = f"ציון {score}/5: בעל כמה מהתכונות החיוביות"
        elif score >= 1:
            action = "החזק ⚖️"
            ai_logic = f"ציון {score}/5: נייטרלי או ממתין לשיפור"
        else:
            action = "בבדיקה 🔍"
            ai_logic = "ציון 0/5: יש לבדוק את הנתונים"
        
        return {
            # Basic
            "Symbol": ticker,
            "Price": float(price),
            "PriceStr": price_str,
            "Currency": currency,
            "Change": round(float(change), 2),
            
            # Technical
            "RSI": round(float(rsi), 1),
            "rsi": round(float(rsi), 1),  # Duplicate for compatibility
            "MA50": round(float(ma50), 2),
            "MA200": round(float(ma200), 2),
            "above_ma50": above_ma50,
            "above_ma200": above_ma200,
            
            # Price returns
            "ret_5d": round(float(ret_5d), 2),
            "ret_20d": round(float(ret_20d), 2),
            
            # Advanced technical
            "bb_width": round(float(bb_width), 2),
            "macd": round(float(macd), 2),
            "momentum": round(float(momentum), 2),
            "volatility": round(float(volatility), 2),
            "vol_ratio": round(float(vol_ratio), 2),
            "candle_body": round(float(candle_body), 2),
            "gap": round(float(gap), 2),
            
            # Fundamentals
            "DivYield": round(float(div_yield), 2),
            "Margin": round(float(margin), 2),
            "ROE": round(float(roe), 2),
            "EarnGrowth": round(float(earn_growth), 2),
            "RevGrowth": round(float(rev_growth), 2),
            "InsiderHeld": round(float(insider), 2),
            "PayoutRatio": round(float(payout), 2),
            "CashVsDebt": cash_vs_debt,
            "ZeroDebt": zero_debt,
            "Safety": safety,
            
            # Valuation
            "FairValue": round(float(fair_value), 2),
            "TargetUpside": round(float(target), 2),
            
            # Other
            "Score": score,
            "DaysToEarnings": int(days_to_earnings),
            "Action": action,
            "AI_Logic": ai_logic,
        }
    except Exception as e:
        return None

def _calc_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.iloc[-1] is np.nan else 50.0

def _calc_bb_width(prices, period=20):
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = sma + (std * 2)
    lower = sma - (std * 2)
    width = upper - lower
    return float(width.iloc[-1]) if len(width) > 0 else 0

def _calc_macd(prices, fast=12, slow=26):
    ema_fast = prices.ewm(span=fast).mean()
    ema_slow = prices.ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    return float(macd.iloc[-1]) if len(macd) > 0 else 0

def _calc_momentum(prices, period=10):
    momentum = prices.iloc[-1] - prices.iloc[-period] if len(prices) > period else 0
    return float(momentum)

def fetch_master_data(tickers=None, max_workers: int = 3) -> pd.DataFrame:
    """Fetch master data with ALL 28 columns - with caching for performance"""
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
            logger.error(f"Error fetching {ticker}: {str(e)}")
            pass
    
    if not results:
        return pd.DataFrame()
    
    return pd.DataFrame(results)
