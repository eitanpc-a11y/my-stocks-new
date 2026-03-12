# analytics_ai.py — אנליטיקה מתקדמת: מפת חום, ביצועי תיק, סקטורים, יומן
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from storage import save, load


@st.cache_data(ttl=300)
def _fetch_sector_perf():
    sectors = {
        "טכנולוגיה":  "XLK", "פיננסים":   "XLF",
        "אנרגיה":     "XLE", "בריאות":    "XLV",
        "צריכה שיקול":"XLY", "תעשיה":     "XLI",
        "חומרי גלם":  "XLB", "נדל\"ן":    "XLRE",
        "תשתיות":     "XLU", "תקשורת":   "XLC",
    }
    rows = []
    for name, ticker in sectors.items():
        try:
            h = yf.Ticker(ticker).history(period="1mo")
            if h.empty or len(h) < 2: continue
            d1  = (h["Close"].iloc[-1]/h["Close"].iloc[-2]-1)*100 if len(h) >= 2 else 0
            w1  = (h["Close"].iloc[-1]/h["Close"].iloc[max(-5,-len(h))-1]-1)*100 if len(h)>=5 else 0
            mo1 = (h["Close"].iloc[-1]/h["Close"].iloc[0]-1)*100 if len(h) >= 1 else 0
            rows.append({"סקטור":name,"יומי %":round(d1,2),
                         "שבועי %":round(w1,2),"חודשי %":round(mo1,2),
                         "מגמה":"🟢" if d1>0 else "🔴"})
        except Exception:
            pass
    return pd.DataFrame(rows)


def render_analytics_dashboard():
    st.markdown(
        '<div class="ai-card" style="border-right-color:#ff5722;">'
        '<b>📊 אנליטיקה מתקדמת</b> — מפת חום ענפית · ביצועי סקטורים · יומן עסקאות</div>',
        unsafe_allow_html=True,
    )

    t1, t2, t3 = st.tabs(["🗺️ מפת חום ענפית", "📈 השוואת מדדים", "📓 יומן פעילות"])

    # ── מפת חום ─────────────────────────────────────────────────────────────
    with t1:
        with st.spinner("טוען ביצועי סקטורים..."):
            df_sec = _fetch_sector_perf()

        if not df_sec.empty:
            # גרף בר מצבע
            fig = go.Figure()
            colors = ["#2e7d32" if v > 0 else "#c62828" for v in df_sec["יומי %"]]
            fig.add_trace(go.Bar(
                x=df_sec["סקטור"], y=df_sec["יומי %"],
                marker_color=colors, name="ביצוע יומי %",
                text=df_sec["יומי %"].apply(lambda x: f"{x:+.2f}%"),
                textposition="outside",
            ))
            fig.update_layout(
                title="ביצועי סקטורים — יומי", xaxis_tickangle=-25,
                yaxis_title="%", height=350, template="plotly_white",
                showlegend=False
            )
            st.plotly_chart(fig)

            # טבלה מפורטת
            st.dataframe(
                df_sec.sort_values("יומי %", ascending=False), hide_index=True,
                column_config={
                    "יומי %":   st.column_config.NumberColumn("יומי %",   format="%.2f%%"),
                    "שבועי %":  st.column_config.NumberColumn("שבועי %",  format="%.2f%%"),
                    "חודשי %":  st.column_config.NumberColumn("חודשי %",  format="%.2f%%"),
                }
            )

            # המלצת AI על הסקטור המוביל
            best = df_sec.loc[df_sec["חודשי %"].idxmax()]
            worst= df_sec.loc[df_sec["חודשי %"].idxmin()]
            col1, col2 = st.columns(2)
            col1.success(f"🏆 סקטור מוביל (חודש): **{best['סקטור']}** +{best['חודשי %']:.1f}%")
            col2.error( f"📉 סקטור חלש (חודש): **{worst['סקטור']}** {worst['חודשי %']:.1f}%")

    # ── השוואת מדדים ─────────────────────────────────────────────────────────
    with t2:
        st.markdown("### 📈 השוואת מדדים מרכזיים")
        indices = {
            "S&P 500": "^GSPC", "NASDAQ": "^IXIC",
            "Dow Jones": "^DJI", "TA-35": "^TA35.TA",
            "זהב": "GC=F",  "ביטקוין": "BTC-USD",
        }
        period_map = {"חודש":"1mo","3 חודשים":"3mo","שנה":"1y","3 שנים":"3y"}
        per_label = st.selectbox("תקופה:", list(period_map.keys()), index=1, key="anal_period")
        per       = period_map[per_label]

        with st.spinner("טוען..."):
            fig2 = go.Figure()
            for name, ticker in indices.items():
                try:
                    h = yf.Ticker(ticker).history(period=per)["Close"]
                    if len(h) > 5:
                        norm = (h / h.iloc[0] - 1) * 100  # נורמליזציה
                        fig2.add_trace(go.Scatter(
                            x=norm.index, y=norm,
                            mode="lines", name=name, line=dict(width=2)
                        ))
                except Exception:
                    pass
        fig2.update_layout(
            title=f"ביצועים מנורמלים — {per_label}",
            yaxis_title="תשואה %", height=400,
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02)
        )
        st.plotly_chart(fig2)
        st.caption("כל המדדים מנורמלים ל-0% בתחילת התקופה לצורך השוואה הוגנת.")

    # ── יומן פעילות ──────────────────────────────────────────────────────────
    with t3:
        st.markdown("### 📓 יומן פעילות ועסקאות")
        log = load("activity_log", [])

        # הוספה ידנית
        with st.expander("➕ הוסף רישום ידני"):
            c1,c2,c3 = st.columns([2,1,2])
            note_sym  = c1.text_input("סימול", key="log_sym")
            note_type = c2.selectbox("סוג", ["קנייה","מכירה","הערה","התראה"], key="log_type")
            note_txt  = c3.text_input("הערה", key="log_txt")
            if st.button("➕ הוסף", key="log_add"):
                log.insert(0, {
                    "זמן":    datetime.now().strftime("%d/%m %H:%M"),
                    "סימול":  note_sym,
                    "סוג":    note_type,
                    "הערה":   note_txt,
                })
                save("activity_log", log[:200])
                st.success("✅ נוסף!")
                st.rerun()

        if log:
            st.dataframe(pd.DataFrame(log[:50]), hide_index=True)
        else:
            st.info("היומן ריק. פעולות הסוכן ייכנסו כאן אוטומטית.")
