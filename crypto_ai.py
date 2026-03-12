# crypto_ai.py — קריפטו בזמן אמת
import streamlit as st
import yfinance as yf
import pandas as pd


@st.cache_data(ttl=300)  # 5 דקות במקום 60 שניות
def _fetch_crypto(sym):
    try:
        hist = yf.Ticker(sym).history(period="7d")
        return hist if not hist.empty else None
    except Exception:
        return None


def render_crypto_arena():
    st.markdown(
        '<div class="ai-card" style="border-right-color: #f7931a;">'
        '<b>₿ זירת קריפטו:</b> נתונים חיים + גרף 7 ימים.</div>',
        unsafe_allow_html=True,
    )

    cryptos = {
        "BTC-USD": "ביטקוין (BTC)",
        "ETH-USD": "אתריום (ETH)",
        "SOL-USD": "סולאנה (SOL)",
        "XRP-USD": "ריפל (XRP)",
        "DOGE-USD": "דוג'קוין (DOGE)",
    }

    rows = []
    with st.spinner("שואב נתוני קריפטו..."):
        for sym, name in cryptos.items():
            try:
                hist = _fetch_crypto(sym)
                if hist is not None and not hist.empty and len(hist) >= 2:
                    px = hist["Close"].iloc[-1]
                    chg = ((px / hist["Close"].iloc[-2]) - 1) * 100
                    vol = hist["Volume"].iloc[-1] / 1e9
                    trend = hist["Close"].tolist()
                    status = ("מומנטום פריצה 🟢" if chg > 3
                              else "תיקון אגרסיבי 🔴" if chg < -3 else "דשדוש ⚪")
                    rows.append({
                        "מטבע": name,
                        "מחיר ($)": px,
                        "שינוי 24H": chg,
                        "נפח (B$)": vol,
                        "גרף 7 ימים": trend,
                        "סטטוס AI": status,
                    })
            except Exception:
                pass

    if rows:
        st.dataframe(
            pd.DataFrame(rows),
            column_config={
                "מחיר ($)": st.column_config.NumberColumn("מחיר", format="$%.2f"),
                "שינוי 24H": st.column_config.NumberColumn("שינוי 24H", format="%.2f%%"),
                "נפח (B$)": st.column_config.NumberColumn("נפח (B$)", format="$%.2fB"),
                "גרף 7 ימים": st.column_config.LineChartColumn("מגמה 7 ימים 📈", y_min=0),
            },
            hide_index=True,
        )
        st.info("💡 **AI:** BTC מוביל > 60% = שוק שור. ETH/SOL/XRP מובילים = עונת altcoins.")
    else:
        st.warning("לא ניתן לשאוב נתוני קריפטו כרגע.")
