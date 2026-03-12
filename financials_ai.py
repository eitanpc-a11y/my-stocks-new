# financials_ai.py — ניתוח דוחות כספיים (גרסה חסינת קריסות)
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

def render_financial_reports(df_all):
    st.markdown(
        '<div class="ai-card" style="border-right-color: #009688;">'
        '<b>📚 ניתוח דוחות היסטוריים:</b> הכנסות, רווחים ומאזן לאורך שנים.</div>',
        unsafe_allow_html=True,
    )

    # בדיקת תקינות: אם הנתונים ריקים או חסרים עמודות
    if df_all is None or df_all.empty or "Symbol" not in df_all.columns:
        st.warning("⚠️ לא נמצאו נתוני מניות במערכת. נסה לרענן את הנתונים או להוסיף מניות ל-Watchlist.")
        return

    # יצירת תיבת הבחירה
    symbols = df_all["Symbol"].unique()
    sel = st.selectbox("בחר מניה לניתוח דוחות:", symbols, key="fin_sym")

    if st.button("📊 נתח דוחות כספיים", type="primary", key="fin_run"):
        with st.spinner(f"שואב ומנתח נתונים עבור {sel}..."):
            try:
                s = yf.Ticker(sel)
                # שימוש ב-financials וב-balance_sheet
                financials = s.financials
                
                if financials is not None and not financials.empty:
                    # ניסיון לשלוף הכנסות ורווח נקי
                    rev = None
                    net = None
                    
                    if "Total Revenue" in financials.index:
                        rev = financials.loc["Total Revenue"]
                    if "Net Income" in financials.index:
                        net = financials.loc["Net Income"]

                    if rev is not None and net is not None:
                        # עיבוד הנתונים לגרף
                        df_p = pd.DataFrame({"Revenue": rev / 1e9, "Net Income": net / 1e9}).dropna()
                        df_p.index = pd.to_datetime(df_p.index).year.astype(str)
                        df_p = df_p.sort_index()

                        fig = go.Figure()
                        fig.add_trace(go.Bar(x=df_p.index, y=df_p["Revenue"],
                                             name="הכנסות ($B)", marker_color="#1a73e8"))
                        fig.add_trace(go.Bar(x=df_p.index, y=df_p["Net Income"],
                                             name='רווח נקי ($B)', marker_color="#34a853"))
                        
                        fig.update_layout(barmode="group", title=f"הכנסות ורווח נקי שנתי - {sel} ($B)",
                                          template="plotly_white", height=400)
                        st.plotly_chart(fig)
                        st.info("💡 **טיפ AI:** חפש צמיחה עקבית בהכנסות של מעל 10% בכל שנה.")
                    else:
                        st.error(f"לא נמצאו נתוני רווח והפסד מפורטים עבור {sel}.")
                else:
                    st.error(f"לא הצלחנו למשוך את הדוחות הכספיים של {sel} מ-Yahoo Finance.")
            except Exception as e:
                st.error(f"שגיאה בניתוח הדוחות: {str(e)}")
