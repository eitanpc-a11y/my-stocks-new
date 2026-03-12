# growth_risk_ai.py — סוכן צמיחה + Position Sizing
import streamlit as st


def render_growth_and_risk(df_all):
    st.markdown(
        '<div class="ai-card" style="border-right-color: #e91e63;">'
        '<b>🚀 מעבדת צמיחה וסיכונים:</b> סורק Hyper-Growth + מחשבון Position Sizing.</div>',
        unsafe_allow_html=True,
    )

    t1, t2 = st.tabs(["🚀 סוכן צמיחה", "🧮 מחשבון סיכונים"])

    with t1:
        st.markdown("### 🚀 סורק צמיחה מואצת (מכירות >20%, RSI>55, מחיר>MA50)")
        if st.button("🔍 הפעל סורק", type="primary", key="growth_scan"):
            if df_all.empty:
                st.error("אין נתונים.")
            else:
                growth = df_all[
                    (df_all["RevGrowth"] >= 20) &
                    (df_all["RSI"] > 55) &
                    (df_all["Price"] > df_all["MA50"])
                ].sort_values("RevGrowth", ascending=False)

                if not growth.empty:
                    st.success(f"ה-AI איתר {len(growth)} מניות צמיחה!")
                    st.dataframe(
                        growth[["Symbol", "PriceStr", "RevGrowth", "RSI", "TargetUpside"]],
                        column_config={
                            "Symbol":      "סימול",
                            "PriceStr":    "מחיר",
                            "RevGrowth":   st.column_config.NumberColumn("צמיחה 🚀", format="%.1f%%"),
                            "RSI":         st.column_config.NumberColumn("RSI", format="%.1f"),
                            "TargetUpside": st.column_config.NumberColumn("פוטנציאל", format="+%.1f%%"),
                        }, hide_index=True,
                    )
                    st.info("💡 חובה Stop-Loss של 7%-10% מהכניסה!")
                else:
                    st.warning("לא נמצאו מניות צמיחה כרגע.")

    with t2:
        st.markdown("### 🧮 מחשבון Position Sizing")
        col1, col2 = st.columns(2)
        with col1:
            capital = st.number_input("💵 גודל תיק ($):", min_value=100, value=10000, step=1000)
            risk_pct = st.number_input("🚨 סיכון לעסקה (%):", min_value=0.1, max_value=10.0, value=1.5, step=0.5)
        with col2:
            entry = st.number_input("🎯 מחיר כניסה ($):", min_value=0.01, value=100.0, step=1.0)
            stop = st.number_input("🛑 Stop-Loss ($):", min_value=0.01, value=93.0, step=1.0)

        if st.button("🧮 חשב", type="primary", key="growth_calc"):
            if entry <= stop:
                st.error("Stop-Loss חייב להיות נמוך ממחיר הכניסה!")
            else:
                risk_usd = capital * (risk_pct / 100)
                rps = entry - stop
                shares = int(risk_usd / rps)
                total_inv = shares * entry
                pct = (total_inv / capital) * 100
                c1, c2, c3 = st.columns(3)
                c1.metric("מניות לקנות", f"{shares}")
                c2.metric("סך השקעה", f"${total_inv:,.2f}")
                c3.metric("% מהתיק", f"{pct:.1f}%")
                st.info(f"מסכן **${risk_usd:,.2f}** ({risk_pct}% מהתיק). Stop: ${stop:.2f}")
