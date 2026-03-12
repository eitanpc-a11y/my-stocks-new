# tab_portfolio.py — מודול התיק האישי
import streamlit as st
import pandas as pd
from tooltips_he import tooltip
from user_manager import save_user_data

def render_portfolio(df_all):
    st.markdown(
        '<div class="ai-card"><b>📌 התיק שלי</b> — לחץ פעמיים לעדכון קנייה/כמות<br>'
        + tooltip("⬆️ מה זה P/L?","P/L","❓")
        + " &nbsp; "
        + tooltip("⬆️ מה זה תשואה?","Change","❓")
        + " &nbsp; "
        + tooltip("⬆️ מה זה ציון?","Score","❓")
        + "</div>",
        unsafe_allow_html=True,
    )

    with st.expander("➕ הוסף נכס (מניה / סחורה / קריפטו / ת\"א)"):
        ca, cb, cc, cd = st.columns([2, 1, 1, 1])
        ns = ca.text_input("סימול (AAPL / GC=F / BTC-USD / TEVA.TA)", key="ns").upper().strip()
        nb = cb.number_input("מחיר קנייה", 0.0, key="nb")
        nq = cc.number_input("כמות", 0.0, key="nq")
        if cd.button("✅ הוסף", key="nadd"):
            if ns:
                if "portfolio" not in st.session_state:
                    st.session_state.portfolio = pd.DataFrame(columns=["Symbol","BuyPrice","Qty"])
                port = st.session_state.portfolio
                if ns not in port["Symbol"].values:
                    new_row = pd.DataFrame([{"Symbol":ns,"BuyPrice":nb,"Qty":nq}])
                    st.session_state.portfolio = pd.concat([port,new_row],ignore_index=True)
                    st.session_state["portfolio_buy_prices"] = dict(zip(st.session_state.portfolio["Symbol"], st.session_state.portfolio["BuyPrice"]))
                    st.session_state["portfolio_quantities"] = dict(zip(st.session_state.portfolio["Symbol"], st.session_state.portfolio["Qty"]))
                    save_user_data()
                    st.success(f"✅ {ns} נוסף!")
                    st.rerun()

    if "portfolio" not in st.session_state:
        saved_prices = st.session_state.get("portfolio_buy_prices", {})
        saved_qty    = st.session_state.get("portfolio_quantities",  {})
        if saved_prices or saved_qty:
            keys = set(list(saved_prices.keys()) + list(saved_qty.keys()))
            st.session_state.portfolio = pd.DataFrame([
                {"Symbol":t,"BuyPrice":saved_prices.get(t,0.0),"Qty":saved_qty.get(t,0)}
                for t in keys
            ])
        else:
            st.session_state.portfolio = pd.DataFrame(columns=["Symbol","BuyPrice","Qty"])

    if not df_all.empty and not st.session_state.portfolio.empty:
        merged = pd.merge(st.session_state.portfolio, df_all, on="Symbol", how="left")
        merged["Price"]    = merged["Price"].fillna(0)
        merged["PriceStr"] = merged.apply(
            lambda r: str(r.get("PriceStr","")) or f"${r['Price']:.2f}", axis=1)
        merged["PL"]    = (merged["Price"]-merged["BuyPrice"])*merged["Qty"]
        merged["Yield"] = merged.apply(
            lambda r: ((r["Price"]/r["BuyPrice"])-1)*100 if r["BuyPrice"]>0 else 0, axis=1)
        merged["Emoji"] = merged["Symbol"].apply(
            lambda s: "🥇" if "GC" in s else "🛢️" if any(x in s for x in ["CL","BZ","NG"]) else
                      "₿" if "BTC" in s else "Ξ" if "ETH" in s else
                      "🇮🇱" if s.endswith(".TA") else "📈")

        disp = merged[["Symbol","Emoji","PriceStr","BuyPrice","Qty","PL","Yield"]].copy()
        disp["Score"]  = merged["Score"].values  if "Score"  in merged.columns else 0
        disp["Action"] = merged["Action"].values if "Action" in merged.columns else "—"

        edited = st.data_editor(
            disp,
            column_config={
                "Symbol":   st.column_config.TextColumn("סימול",     help="סימול הנכס בבורסה", disabled=True),
                "Emoji":    st.column_config.TextColumn("סוג",       help="סוג הנכס", disabled=True),
                "PriceStr": st.column_config.TextColumn("מחיר חי",  help="מחיר נוכחי", disabled=True),
                "BuyPrice": st.column_config.NumberColumn("קנייה ✏️",help="מחיר קנייה (לחץ לעריכה)"),
                "Qty":      st.column_config.NumberColumn("כמות ✏️", help="כמות נכסים (לחץ לעריכה)"),
                "PL":       st.column_config.NumberColumn("P/L 💰",  help="רווח/הפסד כספי", format="%.2f", disabled=True),
                "Yield":    st.column_config.NumberColumn("תשואה %", help="רווח/הפסד אחוזי", format="%.1f%%", disabled=True),
                "Score":    st.column_config.NumberColumn("⭐ ציון",  help="ציון 0-6", disabled=True),
                "Action":   st.column_config.TextColumn("המלצה AI",  help="המלצת הבינה המלאכותית", disabled=True),
            }, hide_index=True,
        )
        st.session_state.portfolio = edited[["Symbol","BuyPrice","Qty"]]
        st.session_state["portfolio_buy_prices"] = dict(zip(edited["Symbol"], edited["BuyPrice"]))
        st.session_state["portfolio_quantities"] = dict(zip(edited["Symbol"], edited["Qty"]))
        save_user_data()

        active = merged[merged["Qty"]>0].copy()
        if not active.empty:
            active["PL"] = (active["Price"]-active["BuyPrice"])*active["Qty"]
            total_pl     = active["PL"].sum()
            total_val    = (active["Price"]*active["Qty"]).sum()
            st.divider()
            s1,s2,s3,s4 = st.columns(4)
            s1.metric("📊 נכסים פעילים", len(active))
            s2.metric("💼 שווי תיק",     f"${total_val:,.0f}")
            s3.metric("📈 רווח/הפסד",
                      f"{'🟢 +' if total_pl>=0 else '🔴 '}${abs(total_pl):,.0f}")
            s4.metric("⭐ ציון ממוצע",
                      f"{active['Score'].mean():.1f}/6" if "Score" in active.columns else "—")
    else:
        st.info("התיק שלך ריק! הוסף נכסים חדשים כדי להתחיל.")
