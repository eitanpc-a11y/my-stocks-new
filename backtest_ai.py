# backtest_ai.py — בק-טסט 2 שנים
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go


@st.cache_data(ttl=3600)
def _backtest(symbol, capital):
    try:
        hist = yf.Ticker(symbol).history(period="2y")
        if hist.empty:
            return None, None
        s = hist["Close"].iloc[0]
        e = hist["Close"].iloc[-1]
        final = (capital / s) * e
        return hist, {"final": final, "pct": ((final / capital) - 1) * 100}
    except Exception:
        return None, None


def render_backtester(df_all):
    st.markdown(
        '<div class="ai-card" style="border-right-color: #4caf50;">'
        '<b>⏪ בק-טסט (2 שנים):</b></div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        sel = st.selectbox("בחר מניה:", df_all["Symbol"].unique(), key="backtest_sym")
    with c2:
        capital = st.number_input("סכום ($):", min_value=1000, value=10000, step=1000, key="backtest_capital")

    if st.button("⏪ הרץ", type="primary", key="backtest_run"):
        with st.spinner("מחשב..."):
            hist, res = _backtest(sel, capital)
        if hist is not None:
            c1, c2, c3 = st.columns(3)
            c1.metric("השקעה", f"${capital:,.0f}")
            c2.metric("שווי היום", f"${res['final']:,.0f}")
            c3.metric("תשואה", f"{res['pct']:.1f}%")
            fig = go.Figure(go.Scatter(x=hist.index, y=hist["Close"],
                                        line=dict(color="#1a73e8"),
                                        fill="tozeroy", fillcolor="rgba(26,115,232,0.1)"))
            fig.update_layout(title=f"{sel} — 2 שנים", height=300, template="plotly_white",
                              margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig)
            st.info("💡 Buy & Hold בחברות PDF > מסחר יומי בטווח ארוך.")
        else:
            st.error("לא ניתן להריץ — חסרים נתוני עבר.")
