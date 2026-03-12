# market_ai.py — מודיעין גלובלי ומדדים חיים
import streamlit as st
import yfinance as yf
import pandas as pd


def render_market_intelligence():
    st.markdown(
        '<div class="ai-card"><b>🌍 מודיעין גלובלי:</b> '
        'מדדים עולמיים בזמן אמת + ניתוח מאקרו.</div>',
        unsafe_allow_html=True,
    )

    st.subheader("📊 מדדי שוק עולמיים (בזמן אמת)")
    indices = {
        "S&P 500":       "^GSPC",
        "נאסד\"ק 100":   "^NDX",
        "דאו ג'ונס":    "^DJI",
        "VIX (מדד פחד)": "^VIX",
        "ת\"א 125":      "^TA125.TA",
        "FTSE 100":      "^FTSE",
        "DAX":           "^GDAXI",
        "ניקיי":         "^N225",
    }

    rows = []
    with st.spinner("שואב נתוני מדדים..."):
        for name, sym in indices.items():
            try:
                h = yf.Ticker(sym).history(period="5d")
                if not h.empty and len(h) >= 2:
                    px = h["Close"].iloc[-1]
                    prev = h["Close"].iloc[-2]
                    chg = ((px / prev) - 1) * 100
                    rows.append({
                        "מדד": name,
                        "ערך": f"{px:,.2f}",
                        "שינוי %": chg,
                        "מגמה": "🟢" if chg > 0 else "🔴",
                    })
            except Exception:
                pass

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            column_config={
                "שינוי %": st.column_config.NumberColumn("שינוי %", format="%.2f%%"),
            },
            hide_index=True,
        )

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🏦 ניתוח מאקרו AI")
        st.info("🏦 **ריבית הפד:** סביבת ריבית גבוהה מועדפת לחברות עם מזומנים ובלי חובות (קריטריונים 5-6).")
        st.success("💻 **AI:** עוברים משלב שבבים לשלב תוכנה. חפש חברות שמשלבות AI בשירותים קיימים.")
        st.warning("⚡ **אנרגיה:** ביקוש חשמל של מרכזי נתונים מזנק. אנרגיה ירוקה מקבלת סובסידיות.")

    with col2:
        st.markdown("### 🕵️ סנטימנט שוק")
        st.error("🔥 **מסחר:** קרנות גידור מגדילות שורטים על קמעונאות קטנה בציפייה למיתון.")
        st.markdown(
            '<div class="ai-card" style="border-right-color:#9c27b0;">'
            '<b>💬 סנטימנט רשתות:</b><br>'
            '• Reddit/WSB: מיקוד ב-AI ו-Robotics<br>'
            '• X: חשש מתמחור יתר ב-SaaS<br>'
            '• מוסדיים: רוכשים מניות ערך עם דיבידנד</div>',
            unsafe_allow_html=True,
        )
