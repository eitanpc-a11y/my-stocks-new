# pro_tools_ai.py — כסף חכם + רנטגן תיק
import streamlit as st
import pandas as pd
import plotly.express as px


def _smart_label(upside, insider):
    if insider > 10 and upside > 15:
        return "🔥 שורי מאוד: הנהלה מושקעת + אנליסטים אופטימיים"
    elif insider > 5 and upside > 5:
        return "🟢 חיובי: הלימת אינטרסים טובה"
    elif insider < 1 and upside < 0:
        return "🔴 אזהרה: הנהלה לא מחזיקה + אנליסטים שליליים"
    elif upside > 20:
        return "📈 אופטימיות: בדוק שהמספרים מצדיקים"
    return "⚖️ ניטרלי"


def render_pro_tools(df_all, portfolio_df):
    st.markdown(
        '<div class="ai-card" style="border-right-color: #3f51b5;">'
        '<b>🧰 כלים מקצועיים:</b> כסף חכם + רנטגן תיק.</div>',
        unsafe_allow_html=True,
    )

    t1, t2 = st.tabs(["🕵️ כסף חכם (Insiders + אנליסטים)", "🩻 רנטגן תיק"])

    with t1:
        st.markdown("### 🕵️ סורק כסף חכם")
        if not df_all.empty:
            smart = df_all.copy()
            
            # Check if required columns exist
            missing_cols = []
            if "TargetUpside" not in smart.columns:
                missing_cols.append("TargetUpside")
            if "InsiderHeld" not in smart.columns:
                missing_cols.append("InsiderHeld")
            
            if missing_cols:
                st.error(f"❌ שגיאה: עמודות חסרות: {', '.join(missing_cols)}")
                st.info("💡 זו בעיה בטעינת הנתונים. בדוק ש-logic.py מחזיר את כל העמודות הנדרשות.")
            else:
                smart["AI"] = smart.apply(lambda r: _smart_label(r["TargetUpside"], r["InsiderHeld"]), axis=1)
                smart = smart[(smart["TargetUpside"] > 5) | (smart["InsiderHeld"] > 2)].sort_values(
                    "TargetUpside", ascending=False)
                st.dataframe(
                    smart[["Symbol", "PriceStr", "TargetUpside", "InsiderHeld", "AI"]],
                    column_config={
                        "Symbol":      "סימול",
                        "PriceStr":    "מחיר",
                        "TargetUpside": st.column_config.NumberColumn("אנליסטים %", format="+%.1f%%"),
                        "InsiderHeld":  st.column_config.NumberColumn("הנהלה %", format="%.2f%%"),
                        "AI":           st.column_config.TextColumn("ניתוח AI", width="large"),
                    }, hide_index=True,
                )

    with t2:
        st.markdown("### 🩻 פיזור סיכונים")
        if portfolio_df is not None and not portfolio_df.empty and not df_all.empty:
            merged = pd.merge(portfolio_df, df_all, on="Symbol")
            merged = merged[merged["Qty"] > 0]
            if not merged.empty:
                merged["TotalValue"] = merged["Price"] * merged["Qty"]
                total = merged["TotalValue"].sum()
                dist = merged.groupby("Sector")["TotalValue"].sum().reset_index()
                dist["Percent"] = (dist["TotalValue"] / total) * 100

                cc, ca = st.columns(2)
                with cc:
                    fig = px.pie(dist, values="TotalValue", names="Sector",
                                 title="פיזור לפי סקטורים", hole=0.4)
                    st.plotly_chart(fig)
                with ca:
                    st.markdown("#### 🧠 ניהול סיכונים")
                    mx = dist.loc[dist["Percent"].idxmax()]
                    if mx["Percent"] > 60:
                        st.error(f"⚠️ ריכוזיות חמורה! {mx['Percent']:.1f}% בסקטור {mx['Sector']}.")
                    elif mx["Percent"] > 40:
                        st.warning(f"⚖️ ריכוזיות בינונית: {mx['Sector']} = {mx['Percent']:.1f}%.")
                    else:
                        st.success(f"🛡️ פיזור מעולה! סקטור מקסימלי: {mx['Percent']:.1f}%.")
            else:
                st.info("הזן כמות >0 בתיק לניתוח פיזור.")
        else:
            st.info("אין נתוני תיק.")
