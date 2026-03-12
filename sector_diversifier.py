# sector_diversifier.py — גיוון סקטוריאלי חכם
# ✅ מיפוי סקטור לכל נכס (hardcoded + yfinance fallback)
# ✅ מניעת ריכוזיות — לא יותר מ-MAX_PER_SECTOR מניות לסקטור
# ✅ תמיכה במניות ארה"ב, תא"ב, קריפטו, סחורות, ETF
import logging
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════
# מפת סקטורים — כוללת את הנכסים הנפוצים ביותר
# ════════════════════════════════════════════════════════════════════════

SECTOR_MAP = {
    # ── טכנולוגיה ─────────────────────────────────────────────────────
    "AAPL":  "Tech", "MSFT": "Tech", "GOOGL": "Tech", "GOOG": "Tech",
    "META":  "Tech", "NVDA": "Tech", "AMD":   "Tech", "AVGO": "Tech",
    "ORCL":  "Tech", "CRM":  "Tech", "ADBE":  "Tech", "INTC": "Tech",
    "QCOM":  "Tech", "TXN":  "Tech", "AMAT":  "Tech", "LRCX": "Tech",
    "MU":    "Tech", "KLAC": "Tech", "NOW":   "Tech", "SNOW": "Tech",
    "PLTR":  "Tech", "UBER": "Tech", "LYFT":  "Tech", "NET":  "Tech",
    "DDOG":  "Tech", "ZS":   "Tech", "OKTA":  "Tech", "CRWD": "Tech",
    "NICE.TA": "Tech",

    # ── ריטייל / צרכנות ───────────────────────────────────────────────
    "AMZN":  "Consumer", "COST": "Consumer", "WMT":  "Consumer",
    "TGT":   "Consumer", "HD":   "Consumer", "LOW":  "Consumer",
    "NKE":   "Consumer", "SBUX": "Consumer", "MCD":  "Consumer",
    "CMG":   "Consumer", "LULU": "Consumer", "TSLA": "Consumer",

    # ── פיננסים ────────────────────────────────────────────────────────
    "JPM":   "Finance", "BAC":  "Finance", "WFC":  "Finance",
    "GS":    "Finance", "MS":   "Finance", "C":    "Finance",
    "V":     "Finance", "MA":   "Finance", "AXP":  "Finance",
    "BLK":   "Finance", "SCHW": "Finance", "COF":  "Finance",
    "LUMI.TA": "Finance", "POLI.TA": "Finance",

    # ── בריאות / פארמה ────────────────────────────────────────────────
    "JNJ":   "Healthcare", "PFE":  "Healthcare", "MRK":  "Healthcare",
    "ABBV":  "Healthcare", "BMY":  "Healthcare", "LLY":  "Healthcare",
    "UNH":   "Healthcare", "CVS":  "Healthcare", "AMGN": "Healthcare",
    "GILD":  "Healthcare", "REGN": "Healthcare", "BIIB": "Healthcare",
    "TEVA.TA": "Healthcare",

    # ── תקשורת / מדיה ─────────────────────────────────────────────────
    "NFLX":  "Media", "DIS":  "Media", "CMCSA": "Media",
    "T":     "Media", "VZ":   "Media", "CHTR":  "Media",
    "PARA":  "Media", "WBD":  "Media",

    # ── אנרגיה / נפט גז ───────────────────────────────────────────────
    "XOM":   "Energy", "CVX":  "Energy", "COP":  "Energy",
    "SLB":   "Energy", "EOG":  "Energy", "MPC":  "Energy",
    "PSX":   "Energy", "VLO":  "Energy",
    "XLE":   "EnergyETF", "USO": "EnergyETF", "UNG": "EnergyETF",
    "ENLT.TA": "Energy", "ICL.TA": "Materials",

    # ── סחורות יקרות ──────────────────────────────────────────────────
    "GLD":   "Commodities", "SLV": "Commodities", "GDX": "Commodities",
    "GDXJ":  "Commodities", "IAU": "Commodities",

    # ── תשתיות / נדל"ן ────────────────────────────────────────────────
    "AMT":   "REIT", "PLD":   "REIT", "O":    "REIT",
    "SPG":   "REIT", "DLR":   "REIT", "EQIX": "REIT",

    # ── קריפטו ────────────────────────────────────────────────────────
    "BTC-USD": "Crypto", "ETH-USD": "Crypto", "SOL-USD": "Crypto",
    "BNB-USD": "Crypto", "XRP-USD": "Crypto", "ADA-USD": "Crypto",
    "DOGE-USD": "Crypto", "MATIC-USD": "Crypto",

    # ── ת"א — שונות ───────────────────────────────────────────────────
    "ENLT.TA": "Energy",
}

SECTOR_NAMES_HE = {
    "Tech":       "💻 טכנולוגיה",
    "Consumer":   "🛒 צרכנות",
    "Finance":    "🏦 פיננסים",
    "Healthcare": "🏥 בריאות",
    "Media":      "📺 מדיה",
    "Energy":     "⛽ אנרגיה",
    "EnergyETF":  "⛽ ETF אנרגיה",
    "Commodities":"🪙 סחורות",
    "REIT":       "🏢 נדל\"ן",
    "Crypto":     "₿ קריפטו",
    "Materials":  "⚗️ חומרים",
    "Unknown":    "❓ לא ידוע",
}


def get_sector(symbol: str) -> str:
    """
    מחזיר סקטור לסימול.
    קודם בודק במפה המקומית, אחר כך yfinance (איטי).
    """
    if symbol in SECTOR_MAP:
        return SECTOR_MAP[symbol]

    # yfinance fallback — רק אם אין במפה
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info
        sector = info.get("sector", "")
        if sector:
            SECTOR_MAP[symbol] = sector   # cache
            return sector
    except Exception:
        pass

    return "Unknown"


def get_portfolio_sectors(portfolio: list) -> dict:
    """
    מחזיר מילון {sector: [symbols]} עבור תיק נתון.
    portfolio = [{Symbol: ..., ...}, ...]
    """
    sectors: dict = {}
    for p in portfolio:
        sym = p.get("Symbol") or p.get("Stock", "")
        if not sym:
            continue
        sec = get_sector(sym)
        sectors.setdefault(sec, []).append(sym)
    return sectors


def sector_count(portfolio: list) -> dict:
    """מחזיר {sector: count} עבור תיק נתון."""
    return {sec: len(syms) for sec, syms in get_portfolio_sectors(portfolio).items()}


def can_buy_sector(symbol: str, portfolio: list, max_per_sector: int = 2) -> dict:
    """
    האם מותר לקנות את הסימול מבחינת גיוון סקטוריאלי?
    
    מחזיר:
    {
        allowed: bool
        sector: str
        sector_he: str
        current_count: int
        max_per_sector: int
        existing_in_sector: [symbols]
        reason: str
    }
    """
    sec = get_sector(symbol)
    sectors = get_portfolio_sectors(portfolio)
    existing_in_sector = sectors.get(sec, [])
    count = len(existing_in_sector)

    if count >= max_per_sector:
        return {
            "allowed":            False,
            "sector":             sec,
            "sector_he":          SECTOR_NAMES_HE.get(sec, sec),
            "current_count":      count,
            "max_per_sector":     max_per_sector,
            "existing_in_sector": existing_in_sector,
            "reason": (
                f"ריכוזיות: כבר {count}/{max_per_sector} מניות ב"
                f"{SECTOR_NAMES_HE.get(sec, sec)} "
                f"({', '.join(existing_in_sector)})"
            ),
        }

    return {
        "allowed":            True,
        "sector":             sec,
        "sector_he":          SECTOR_NAMES_HE.get(sec, sec),
        "current_count":      count,
        "max_per_sector":     max_per_sector,
        "existing_in_sector": existing_in_sector,
        "reason": f"{SECTOR_NAMES_HE.get(sec, sec)} — {count+1}/{max_per_sector} (מותר)",
    }


# ════════════════════════════════════════════════════════════════════════
# UI Widget
# ════════════════════════════════════════════════════════════════════════

def render_sector_breakdown(portfolio: list):
    """
    מציג פירוט גיוון סקטוריאלי לתיק — לשימוש ב-UI.
    """
    import streamlit as st
    import pandas as pd

    sectors = get_portfolio_sectors(portfolio)
    if not sectors:
        return

    rows = []
    for sec, syms in sorted(sectors.items(), key=lambda x: -len(x[1])):
        rows.append({
            "🏷️ סקטור":  SECTOR_NAMES_HE.get(sec, sec),
            "📊 מניות":  len(syms),
            "📌 סימולים": ", ".join(syms),
            "🟢 מצב":   "⚠️ מרוכז" if len(syms) > 2 else "✅ מגוון",
        })

    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    concentrated = {sec: syms for sec, syms in sectors.items() if len(syms) > 2}
    if concentrated:
        st.warning(
            "⚠️ **ריכוזיות:** " +
            " | ".join(f"{SECTOR_NAMES_HE.get(s, s)}: {', '.join(v)}"
                       for s, v in concentrated.items())
        )
