# portfolio_optimizer.py — אופטימיזציית תיק + Beta + Sharpe + Rebalancing
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from storage import save, load
import plotly.graph_objects as go
import plotly.express as px

BENCH_SYMBOL = "^GSPC"   # S&P 500 כ-Benchmark

# ─── נתוני היסטוריה ──────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def _get_prices(symbols: list, period="1y") -> pd.DataFrame:
    data = {}
    for sym in symbols:
        try:
            h = yf.Ticker(sym).history(period=period)["Close"]
            if len(h) > 30:
                data[sym] = h
        except Exception:
            pass
    return pd.DataFrame(data).dropna() if data else pd.DataFrame()


def _calc_metrics(prices_df: pd.DataFrame, weights: np.ndarray,
                  bench_prices: pd.Series = None) -> dict:
    """מחשב Sharpe, Beta, Max Drawdown, Correlation."""
    returns  = prices_df.pct_change().dropna()
    port_ret = returns @ weights
    ann_ret  = float(port_ret.mean() * 252)
    ann_vol  = float(port_ret.std() * np.sqrt(252))
    sharpe   = (ann_ret - 0.045) / ann_vol if ann_vol > 0 else 0

    # Max Drawdown
    cumret  = (1 + port_ret).cumprod()
    peak    = cumret.cummax()
    dd      = (cumret - peak) / peak
    max_dd  = float(dd.min() * 100)

    # Beta vs S&P500
    beta = 0.0
    if bench_prices is not None:
        bench_ret = bench_prices.pct_change().dropna()
        common    = port_ret.index.intersection(bench_ret.index)
        if len(common) > 30:
            cov  = np.cov(port_ret[common], bench_ret[common])
            beta = float(cov[0,1] / cov[1,1]) if cov[1,1] > 0 else 0.0

    return {
        "ann_return":  round(ann_ret * 100, 2),
        "ann_vol":     round(ann_vol * 100, 2),
        "sharpe":      round(sharpe, 2),
        "max_dd":      round(max_dd, 2),
        "beta":        round(beta, 2),
    }


def _monte_carlo(returns: pd.DataFrame, n_sim=8000) -> dict:
    """מחשב 8000 תיקים אקראיים — מחזיר Efficient Frontier."""
    mu   = returns.mean() * 252
    cov  = returns.cov()  * 252
    n    = len(mu)
    results = {"ret":[], "vol":[], "sharpe":[], "weights":[]}
    np.random.seed(42)
    for _ in range(n_sim):
        w = np.random.dirichlet(np.ones(n))
        r = float(np.dot(w, mu))
        v = float(np.sqrt(w @ cov.values @ w))
        s = (r - 0.045) / v if v > 0 else 0
        results["ret"].append(r)
        results["vol"].append(v)
        results["sharpe"].append(s)
        results["weights"].append(w)
    return results, mu, cov


def render_portfolio_optimizer(portfolio_df: pd.DataFrame = None):
    st.markdown(
        '<div class="ai-card" style="border-right-color:#00695c;">'
        '<b>📐 אופטימיזציית תיק מתקדמת</b><br>'
        '<small>Markowitz MPT · Sharpe Ratio · Beta vs S&P500 · '
        'Efficient Frontier · Rebalancing אוטומטי</small></div>',
        unsafe_allow_html=True,
    )

    t1, t2, t3, t4 = st.tabs([
        "🎯 אופטימיזציה", "📊 מדדי ביצוע", "🔗 קורלציות", "⚖️ Rebalancing"
    ])

    # ══ TAB 1: אופטימיזציה ════════════════════════════════════════════════════
    with t1:
        if portfolio_df is not None and not portfolio_df.empty:
            default_syms = portfolio_df["Symbol"].tolist()[:8]
        else:
            default_syms = ["AAPL","NVDA","MSFT","META","AMZN"]

        symbols = st.multiselect(
            "📌 בחר נכסים לאופטימיזציה (3-12):",
            options=default_syms + ["TSLA","GOOGL","V","JPM","GC=F","BTC-USD"],
            default=default_syms[:5], key="opt_symbols"
        )
        period = st.select_slider("📅 תקופת נתונים:", ["6mo","1y","2y","3y"], value="1y", key="opt_period")

        if st.button("🚀 הרץ אופטימיזציה (8,000 סימולציות)", type="primary", key="opt_run"):
            if len(symbols) < 2:
                st.warning("בחר לפחות 2 נכסים")
            else:
                with st.spinner("מחשב Efficient Frontier..."):
                    prices = _get_prices(symbols, period)
                    bench  = _get_prices([BENCH_SYMBOL], period)

                if prices.empty:
                    st.error("לא ניתן לטעון נתונים")
                else:
                    returns  = prices.pct_change().dropna()
                    mc, mu, cov = _monte_carlo(returns)

                    # תיק Sharpe מקסימלי
                    best_i   = np.argmax(mc["sharpe"])
                    best_w   = mc["weights"][best_i]

                    # תיק תנודתיות מינימלית
                    min_i    = np.argmin(mc["vol"])
                    min_w    = mc["weights"][min_i]

                    bench_s  = bench[BENCH_SYMBOL] if not bench.empty else None
                    best_met = _calc_metrics(prices, best_w, bench_s)
                    min_met  = _calc_metrics(prices, min_w, bench_s)

                    # שמור תוצאות
                    save("opt_best_weights", {sym: float(w) for sym, w in zip(prices.columns, best_w)})
                    save("opt_symbols",      list(prices.columns))

                    # ── Efficient Frontier ─────────────────────────────────
                    fig = go.Figure()
                    sharpe_vals = np.array(mc["sharpe"])
                    fig.add_trace(go.Scatter(
                        x=[v*100 for v in mc["vol"]],
                        y=[r*100 for r in mc["ret"]],
                        mode="markers",
                        marker=dict(size=3, color=sharpe_vals,
                                    colorscale="RdYlGn", showscale=True,
                                    colorbar=dict(title="Sharpe")),
                        name="תיקים אקראיים", hovertemplate="תנודתיות: %{x:.1f}%<br>תשואה: %{y:.1f}%"
                    ))
                    # נקודת Sharpe מקסימלי
                    fig.add_trace(go.Scatter(
                        x=[mc["vol"][best_i]*100], y=[mc["ret"][best_i]*100],
                        mode="markers", marker=dict(size=18, color="gold", symbol="star"),
                        name=f"⭐ Sharpe מקסימלי ({mc['sharpe'][best_i]:.2f})"
                    ))
                    fig.add_trace(go.Scatter(
                        x=[mc["vol"][min_i]*100], y=[mc["ret"][min_i]*100],
                        mode="markers", marker=dict(size=14, color="blue", symbol="diamond"),
                        name="💎 תנודתיות מינימלית"
                    ))
                    fig.update_layout(
                        title="Efficient Frontier — 8,000 תיקים",
                        xaxis_title="תנודתיות שנתית %",
                        yaxis_title="תשואה שנתית צפויה %",
                        height=450, template="plotly_white"
                    )
                    st.plotly_chart(fig)

                    # ── השוואת תיקים ────────────────────────────────────────
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("#### ⭐ תיק Sharpe מקסימלי")
                        alloc_df = pd.DataFrame([
                            {"📌 נכס": sym,
                             "💼 %": f"{w*100:.1f}%",
                             "גרף": "█" * max(1, int(w*50))}
                            for sym, w in sorted(zip(prices.columns, best_w),
                                                  key=lambda x: x[1], reverse=True)
                        ])
                        st.dataframe(alloc_df, hide_index=True)
                        m1,m2,m3 = st.columns(3)
                        m1.metric("📈 תשואה", f"{best_met['ann_return']:.1f}%")
                        m2.metric("📊 תנודתיות", f"{best_met['ann_vol']:.1f}%")
                        m3.metric("⚖️ Sharpe", f"{best_met['sharpe']:.2f}")
                        st.metric("📉 Max DD", f"{best_met['max_dd']:.1f}%")
                        st.metric("🔢 Beta", f"{best_met['beta']:.2f}")
                    with c2:
                        st.markdown("#### 💎 תיק תנודתיות מינימלית")
                        alloc_df2 = pd.DataFrame([
                            {"📌 נכס": sym,
                             "💼 %": f"{w*100:.1f}%",
                             "גרף": "█" * max(1, int(w*50))}
                            for sym, w in sorted(zip(prices.columns, min_w),
                                                  key=lambda x: x[1], reverse=True)
                        ])
                        st.dataframe(alloc_df2, hide_index=True)
                        m1,m2,m3 = st.columns(3)
                        m1.metric("📈 תשואה", f"{min_met['ann_return']:.1f}%")
                        m2.metric("📊 תנודתיות", f"{min_met['ann_vol']:.1f}%")
                        m3.metric("⚖️ Sharpe", f"{min_met['sharpe']:.2f}")
                        st.metric("📉 Max DD", f"{min_met['max_dd']:.1f}%")
                        st.metric("🔢 Beta", f"{min_met['beta']:.2f}")

    # ══ TAB 2: מדדי ביצוע ════════════════════════════════════════════════════
    with t2:
        saved_w = load("opt_best_weights", {})
        saved_s = load("opt_symbols", [])
        if not saved_w:
            st.info("הרץ אופטימיזציה תחילה בטאב 'אופטימיזציה'.")
        else:
            prices = _get_prices(saved_s, "1y")
            bench  = _get_prices([BENCH_SYMBOL], "1y")
            if not prices.empty:
                w       = np.array([saved_w.get(s,0) for s in prices.columns])
                w      /= w.sum()
                returns = prices.pct_change().dropna()
                port_r  = returns @ w
                bench_r = bench[BENCH_SYMBOL].pct_change().dropna() if not bench.empty else None
                cumport = (1 + port_r).cumprod()

                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(x=cumport.index, y=cumport.values*100-100,
                                           mode="lines", name="התיק שלי",
                                           line=dict(color="#1a73e8",width=3)))
                if bench_r is not None:
                    common   = cumport.index.intersection(bench_r.index)
                    bench_cum = (1 + bench_r[common]).cumprod()
                    fig2.add_trace(go.Scatter(x=bench_cum.index, y=bench_cum.values*100-100,
                                               mode="lines", name="S&P 500",
                                               line=dict(color="orange",width=2,dash="dash")))
                fig2.update_layout(title="ביצועים vs S&P 500",
                                    yaxis_title="תשואה מצטברת %",
                                    height=380, template="plotly_white")
                st.plotly_chart(fig2)

                met = _calc_metrics(prices, w, bench_r)
                cols = st.columns(5)
                labels = ["📈 תשואה שנתית","📊 תנודתיות","⚖️ Sharpe","📉 Max DD","🔢 Beta"]
                vals   = [f"{met['ann_return']:.1f}%", f"{met['ann_vol']:.1f}%",
                          f"{met['sharpe']:.2f}", f"{met['max_dd']:.1f}%", f"{met['beta']:.2f}"]
                for c, l, v in zip(cols, labels, vals):
                    c.metric(l, v)

                # רולינג שארפ
                rolling_ret = port_r.rolling(21).mean() * 252
                rolling_vol = port_r.rolling(21).std() * np.sqrt(252)
                rolling_sh  = (rolling_ret - 0.045) / rolling_vol
                fig3 = go.Figure()
                fig3.add_trace(go.Scatter(x=rolling_sh.index, y=rolling_sh,
                                           mode="lines", fill="tozeroy",
                                           line=dict(color="#9c27b0"),
                                           name="Sharpe רולינג 21 יום"))
                fig3.add_hline(y=1, line_dash="dash", line_color="green",
                               annotation_text="Sharpe=1 (מצוין)")
                fig3.update_layout(title="Sharpe Ratio רולינג",
                                    height=280, template="plotly_white")
                st.plotly_chart(fig3)

    # ══ TAB 3: קורלציות ══════════════════════════════════════════════════════
    with t3:
        symbols_c = st.multiselect("בחר נכסים:", load("opt_symbols", []) + ["GC=F","BTC-USD"],
                                    default=load("opt_symbols", [])[:6], key="corr_syms")
        if symbols_c and st.button("🔗 חשב קורלציות", key="corr_run"):
            prices_c = _get_prices(symbols_c, "6mo")
            if not prices_c.empty:
                corr = prices_c.pct_change().dropna().corr().round(2)
                fig_c = px.imshow(corr, text_auto=True, color_continuous_scale="RdYlGn",
                                   zmin=-1, zmax=1, title="מטריצת קורלציה (6 חודשים)")
                fig_c.update_layout(height=420)
                st.plotly_chart(fig_c)
                st.caption("""
                🟢 +1 = תנועה זהה (לא מפזר) | 🔴 -1 = תנועה הפוכה (גידור מושלם)
                💡 פיזור אידיאלי: קורלציות בין 0.2 ל-0.5
                """)

    # ══ TAB 4: Rebalancing ════════════════════════════════════════════════════
    with t4:
        st.markdown("### ⚖️ Rebalancing — איזון מחדש אוטומטי")
        st.info("השווה את הרכב התיק הנוכחי להרכב האופטימלי וחשב מה צריך לקנות/למכור.")
        saved_w = load("opt_best_weights", {})
        if not saved_w:
            st.warning("הרץ אופטימיזציה קודם.")
        else:
            total_val = st.number_input("💰 שווי כולל של התיק (₪):", 1000, 10000000,
                                         50000, 1000, key="reb_total")
            rows = []
            for sym, target_pct in sorted(saved_w.items(), key=lambda x: x[1], reverse=True):
                target_ils = total_val * target_pct
                rows.append({
                    "📌 נכס":     sym,
                    "🎯 יעד %":   f"{target_pct*100:.1f}%",
                    "💰 יעד ₪":   f"₪{target_ils:,.0f}",
                    "📋 פעולה":   f"קנה ₪{target_ils:,.0f} מ-{sym}",
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True)
            st.success("💡 בצע את הפעולות האלה כדי להגיע להרכב האופטימלי!")
