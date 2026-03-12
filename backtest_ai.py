# backtest_ai.py — Streamlit UI for Strategy Backtester + Walk-Forward
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

from backtest_engine import (
    _bulk_download, run_backtest, run_walk_forward,
    DEFAULT_TP, DEFAULT_SL, DEFAULT_TE, BACKTEST_UNIVERSE,
)


def _plot_equity(results: list, capital: float):
    fig = go.Figure()
    colors = ["#1a73e8", "#34a853", "#fbbc04", "#ea4335", "#9334e8"]
    for i, r in enumerate(results):
        eq = pd.DataFrame(r["equity_curve"])
        if eq.empty:
            continue
        fig.add_trace(go.Scatter(
            x=eq["date"], y=eq["equity"],
            name=r["label"],
            line=dict(color=colors[i % len(colors)], width=2),
        ))
    if results and results[0].get("spy_curve"):
        spy = pd.DataFrame(results[0]["spy_curve"])
        fig.add_trace(go.Scatter(
            x=spy["date"], y=spy["equity"],
            name="📊 SPY Benchmark",
            line=dict(color="#aaa", width=1.5, dash="dot"),
        ))
    fig.add_hline(y=capital, line_color="#888", line_dash="dash",
                  annotation_text="הון התחלתי")
    fig.update_layout(
        title="📈 עקומת Equity",
        height=420, template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=0, r=0, t=40, b=0),
        yaxis_tickprefix="$", yaxis_tickformat=",",
        hovermode="x unified",
    )
    return fig


def _plot_drawdown(r: dict):
    eq   = pd.DataFrame(r["equity_curve"]).set_index("date")["equity"]
    peak = eq.cummax()
    dd   = (eq - peak) / peak * 100
    fig  = go.Figure(go.Scatter(
        x=dd.index, y=dd.values,
        fill="tozeroy", fillcolor="rgba(234,67,53,0.15)",
        line=dict(color="#ea4335"), name="Drawdown",
    ))
    fig.update_layout(
        title="🕳️ Drawdown לאורך זמן",
        height=250, template="plotly_white",
        yaxis_ticksuffix="%",
        margin=dict(l=0, r=0, t=35, b=0),
    )
    return fig


def _plot_walk_forward_bars(results: list):
    labels  = [r["label"] for r in results]
    strat   = [r["total_return"] for r in results]
    spy     = [r["spy_return"]   for r in results]
    colors  = ["#34a853" if v >= 0 else "#ea4335" for v in strat]
    fig = go.Figure()
    fig.add_bar(name="אסטרטגיה", x=labels, y=strat,
                marker_color=colors,
                text=[f"{v:+.1f}%" for v in strat], textposition="outside")
    fig.add_bar(name="SPY", x=labels, y=spy,
                marker_color="rgba(120,120,120,0.4)",
                text=[f"{v:+.1f}%" for v in spy], textposition="outside")
    fig.update_layout(
        title="📊 Walk-Forward — תשואה לפי שנה vs SPY",
        barmode="group", height=380, template="plotly_white",
        margin=dict(l=0, r=0, t=40, b=0),
        yaxis_ticksuffix="%",
    )
    return fig


def render_backtester(df_all=None):
    st.markdown("""
    <div class="ai-card" style="border-right-color:#1a73e8;">
    <b>⏪ Backtester + Walk-Forward — אימון ואמות עצמי לפני כסף אמיתי</b>
    </div>""", unsafe_allow_html=True)

    with st.expander("⚙️ הגדרות אסטרטגיה", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        tp  = c1.number_input("🎯 Take-Profit %",  min_value=3.0,  max_value=30.0,
                              value=float(DEFAULT_TP), step=0.5, key="bt_tp")
        sl  = c2.number_input("🛡️ Stop-Loss %",    min_value=2.0,  max_value=20.0,
                              value=float(DEFAULT_SL), step=0.5, key="bt_sl")
        te  = c3.number_input("⏳ Time-Exit ימים", min_value=5,    max_value=60,
                              value=int(DEFAULT_TE),   step=1,   key="bt_te")
        cap = c4.number_input("💵 הון ($)",        min_value=10000, max_value=1_000_000,
                              value=100_000, step=10000, key="bt_cap")

    tab_bt, tab_wf = st.tabs(["📈 Backtest מלא", "🔄 Walk-Forward Validation"])

    # ════════════════════════════════════════════════════════
    # TAB 1 — Backtest מלא
    # ════════════════════════════════════════════════════════
    with tab_bt:
        st.info(
            f"🔍 {len(BACKTEST_UNIVERSE)} סימבולים | "
            "עמלה 0.1% + Slippage 0.1% לכל כיוון | "
            "Benchmark: SPY | נתונים: קריאת yfinance אחת לכולם"
        )
        c1, c2 = st.columns(2)
        bt_start = c1.selectbox("מתאריך",  ["2020-01-01","2021-01-01","2022-01-01","2023-01-01"], key="bt_start")
        bt_end   = c2.selectbox("עד תאריך",["2024-12-31","2023-12-31","2022-12-31","2025-03-01"], key="bt_end")

        if st.button("▶️ הרץ Backtest", type="primary", key="run_bt"):
            with st.spinner("⬇️ מוריד נתונים היסטוריים — קריאה אחת לכל הסימבולים..."):
                data = _bulk_download(tuple(BACKTEST_UNIVERSE), bt_start, bt_end)
            if not data:
                st.error("שגיאה בהורדת נתונים. בדוק חיבור ונסה שנית.")
                st.stop()
            with st.spinner(f"⚙️ מריץ סימולציה על {len(data)} סימבולים..."):
                r = run_backtest(data, list(data.keys()), bt_start, bt_end,
                                 tp=tp, sl=sl, te=te, capital=cap,
                                 label=f"{bt_start[:4]}–{bt_end[:4]}")
            if not r:
                st.warning("לא נמצאו עסקאות בתקופה זו — נסה לשנות פרמטרים.")
                st.stop()
            st.session_state["bt_result"] = r

        r = st.session_state.get("bt_result")
        if not r:
            st.caption("לחץ ▶️ להרצת הבאקטסט")
            return

        # מדדים
        st.divider()
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("💰 תשואה כוללת",  f"{r['total_return']:+.1f}%",
                  delta=f"SPY: {r['spy_return']:+.1f}%")
        c2.metric("🎯 Sharpe Ratio",  f"{r['sharpe']:.2f}",
                  delta="✅ טוב" if r["sharpe"] > 1 else "⚠️ שפר")
        c3.metric("🕳️ Max Drawdown", f"{r['max_dd']:.1f}%",
                  delta="⚠️ גבוה" if r["max_dd"] < -20 else "✅ סביר")
        c4.metric("🏆 Win Rate",      f"{r['win_rate']:.0f}%")
        c5.metric("⚖️ Profit Factor", f"{r['profit_factor']:.2f}" if r["profit_factor"] < 999 else "∞")
        c6.metric("🚀 Alpha vs SPY",  f"{r['alpha']:+.1f}%",
                  delta="מכה SPY ✅" if r["alpha"] > 0 else "מפסיד לSPY ❌")

        c1, c2, c3 = st.columns(3)
        c1.metric("📋 עסקאות",      str(r["total_trades"]))
        c2.metric("📈 Avg Win",     f"+{r['avg_win']:.1f}%")
        c3.metric("📉 Avg Loss",    f"{r['avg_loss']:.1f}%")

        # גרפים
        st.plotly_chart(_plot_equity([r], cap), use_container_width=True)
        st.plotly_chart(_plot_drawdown(r), use_container_width=True)

        with st.expander("📋 יומן עסקאות מלא"):
            sells = [t for t in r["trades"] if t["type"] == "SELL"]
            if sells:
                df_t = pd.DataFrame(sells)[["date","sym","price","pnl_pct","reason","hold_days"]]
                df_t.columns = ["📅 תאריך","📌 סימבול","💰 מחיר","📊 P&L%","↔️ סיבה","⏱️ ימים"]
                df_t["🎨"] = df_t["📊 P&L%"].apply(lambda v: "🟢" if v > 0 else "🔴")
                st.dataframe(df_t.sort_values("📅 תאריך", ascending=False),
                             hide_index=True, use_container_width=True)

    # ════════════════════════════════════════════════════════
    # TAB 2 — Walk-Forward Validation
    # ════════════════════════════════════════════════════════
    with tab_wf:
        st.markdown("""
        **Walk-Forward Validation** — הדרך היחידה לדעת אם האסטרטגיה **באמת** עובדת:
        - מריץ את אותה אסטרטגיה על **5 שנים שונות** בנפרד
        - כל שנה = תנאי שוק שונים לחלוטין
        - אם היא רווחית ב-4/5 שנים → האסטרטגיה רובוסטית ואפשר לסמוך עליה
        """)

        c1, c2, c3 = st.columns(3)
        c1.markdown("🔴 **2022** — שוק דובי (SPY ‑18%)")
        c2.markdown("🟡 **2020** — קורונה + התאוששות")
        c3.markdown("🟢 **2021/23/24** — שוק שורי חזק")

        if st.button("🔄 הרץ Walk-Forward (2020–2024)", type="primary", key="run_wf"):
            with st.spinner("⬇️ מוריד נתונים 2020-2024 — קריאה אחת לכל הסימבולים..."):
                wf_data = _bulk_download(tuple(BACKTEST_UNIVERSE), "2020-01-01", "2024-12-31")
            if not wf_data:
                st.error("שגיאה בהורדת נתונים.")
                st.stop()
            bar = st.progress(0, text="מריץ 5 חלונות זמן...")
            wf_results = []
            windows = [
                ("2020-01-01", "2020-12-31", "2020 (קורונה)"),
                ("2021-01-01", "2021-12-31", "2021 (שורי)"),
                ("2022-01-01", "2022-12-31", "2022 (דובי)"),
                ("2023-01-01", "2023-12-31", "2023 (התאוששות)"),
                ("2024-01-01", "2024-12-31", "2024 (AI בום)"),
            ]
            for i, (s, e, label) in enumerate(windows):
                bar.progress((i + 1) / len(windows), text=f"מריץ {label}...")
                r = run_backtest(wf_data, list(wf_data.keys()), s, e,
                                 tp=tp, sl=sl, te=te, capital=cap, label=label)
                if r:
                    wf_results.append(r)
            bar.empty()
            if not wf_results:
                st.warning("לא הצלחנו להריץ Walk-Forward.")
                st.stop()
            st.session_state["wf_results"] = wf_results

        wf_results = st.session_state.get("wf_results")
        if not wf_results:
            st.caption("לחץ 🔄 כדי להריץ")
            return

        # טבלת סיכום
        st.divider()
        rows = []
        for r in wf_results:
            rows.append({
                "📅 תקופה":     r["label"],
                "💰 תשואה":     f"{r['total_return']:+.1f}%",
                "📊 SPY":       f"{r['spy_return']:+.1f}%",
                "🚀 Alpha":     f"{r['alpha']:+.1f}%",
                "🎯 Sharpe":    f"{r['sharpe']:.2f}",
                "🕳️ Max DD":   f"{r['max_dd']:.1f}%",
                "🏆 Win%":      f"{r['win_rate']:.0f}%",
                "📋 עסקאות":    r["total_trades"],
                "✅ מכה SPY?":  "✅ כן" if r["alpha"] > 0 else "❌ לא",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        # מסקנה אוטומטית
        beats      = sum(1 for r in wf_results if r["alpha"] > 0)
        total_w    = len(wf_results)
        avg_alpha  = np.mean([r["alpha"]  for r in wf_results])
        avg_sharpe = np.mean([r["sharpe"] for r in wf_results])
        avg_dd     = np.mean([r["max_dd"] for r in wf_results])

        if beats >= 4 and avg_alpha > 3:
            verdict = "🟢 **אסטרטגיה רובוסטית** — עובדת ברוב תנאי השוק ומכה את ה-SPY. מוכנה לשלב Paper Trading."
        elif beats >= 3:
            verdict = "🟡 **אסטרטגיה בינונית** — עובדת בשוק שורי, חלשה בדובי. שקול להחמיר SL בשוק דובי."
        else:
            verdict = "🔴 **אסטרטגיה לא רובוסטית** — לא עוברת Walk-Forward. יש לשנות TP/SL/TE ולהריץ שוב."

        st.markdown(f"""
        ---
        ### 🧠 מסקנת Walk-Forward
        {verdict}

        | מדד | ערך |
        |---|---|
        | מכה SPY | **{beats}/{total_w}** שנים |
        | Alpha ממוצע לשנה | **{avg_alpha:+.1f}%** |
        | Sharpe ממוצע | **{avg_sharpe:.2f}** |
        | Max Drawdown ממוצע | **{avg_dd:.1f}%** |
        """)

        # גרפים
        st.plotly_chart(_plot_walk_forward_bars(wf_results), use_container_width=True)
        st.plotly_chart(_plot_equity(wf_results, cap), use_container_width=True)
