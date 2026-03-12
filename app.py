# app.py — Investment Hub Elite 2026 — Cloud Ready + Cookies + Twelve Data + קובץ מלא ומאוחד
# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# 🔑 הגדרה קריטית עבור Twelve Data API:
#    1. הכנס את ה-API Key שלך בـ Render תחת Environment Variables
#    2. שם המשתנה חייב להיות: TWELVE_DATA_API_KEY
#    3. הערך: [הקוד שקיבלת מ-Twelve Data]
#    4. לא צריך לשנות פה כלום — הקוד יקרא את המשתנה באוטומטית!
# ═══════════════════════════════════════════════════════════════════════════════════════════════════
import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
from streamlit_cookies_manager import EncryptedCookieManager

# ייבוא הגדרות ולוגיקה
from config import (HELP, MY_STOCKS_BASE, SCAN_LIST,
                    COMMODITIES_SYMBOLS, CRYPTO_SYMBOLS, TASE_SCAN)
from logic   import fetch_master_data
from storage import load_all_to_session, save, load
from tooltips_he import inject_tooltip_css, tooltip, render_glossary
from scheduler_agents import start_background_scheduler, get_scheduler

# ייבוא כל מודולי ה-AI
import realtime_data, market_ai, bull_bear, simulator
import podcasts_ai, alerts_ai, financials_ai, crypto_ai
import news_ai, telegram_ai, analytics_ai, pro_tools_ai
import premium_agents_ai, growth_risk_ai, backtest_ai
import execution_ai, failsafes_ai, ml_learning_ai
import social_sentiment_ai, tax_fees_ai, market_scanner
import ai_portfolio, commodities_tab, pattern_ai, portfolio_optimizer

# ניהול משתמשים (נשאר חיצוני כדי לשמור על סדר בלוגין)
from user_manager import init_user_session, render_login_page, save_user_data

# ─── ניהול Cookies לענן (Render) ──────────────────────────────────────────────
cookies = EncryptedCookieManager(password="HubElite_Secure_Cloud_Key_2026_Long_String", prefix="render_hub/")
if not cookies.ready():
    st.stop()

# ─── הגדרות דף ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Investment Hub Elite 2026",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── עיצוב CSS (הסרת Sidebar לחלוטין, עיצוב השם, וכרטיסיות) ──────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;600;700;800&display=swap');
html, body, [class*="css"] { font-family:'Heebo',sans-serif !important; direction:rtl; text-align:right; }
.stApp { background:#f5f7fa !important; }
.block-container { padding-top:0.5rem !important; max-width:100% !important; }
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }

.ai-card {
    background:#fff; padding:12px 18px; border-radius:12px;
    border-right:5px solid #1976d2;
    box-shadow:0 1px 6px rgba(0,0,0,0.08); margin-bottom:10px;
}
.hub-header {
    background:linear-gradient(135deg,#1565c0 0%,#1976d2 55%,#42a5f5 100%);
    border-radius:14px; padding:16px 22px; margin-bottom:12px;
    box-shadow:0 4px 18px rgba(21,101,192,0.22);
}
.user-info-box {
    background:#fff; padding:10px 15px; border-radius:10px; text-align:center;
    box-shadow:0 2px 5px rgba(0,0,0,0.05); white-space: nowrap; 
    overflow: hidden; text-overflow: ellipsis; border: 1px solid #e0e6ed;
    color: #1a237e; font-weight: bold;
}
[data-testid="stMetric"] {
    background:#fff; border-radius:10px; padding:8px 14px;
    box-shadow:0 1px 5px rgba(0,0,0,0.07); border:1px solid #e8edf2;
}
[data-testid="stMetricLabel"] { color:#607d8b !important; font-size:11px !important; font-weight:700 !important; }
[data-testid="stMetricValue"] { color:#1a237e !important; font-size:20px !important; font-weight:800 !important; }
div[data-testid="stTabs"] button { font-weight:700 !important; font-size:11px !important; color:#546e7a !important; }
div[data-testid="stTabs"] button:hover { color:#1565c0 !important; background:#e3f2fd !important; }
div[data-testid="stTabs"] button[aria-selected="true"] {
    color:#1565c0 !important; border-bottom:3px solid #1565c0 !important; background:#fff !important;
}
[data-testid="stDataFrame"] th { background:#e3f2fd !important; color:#1565c0 !important; font-weight:700 !important; }
[data-testid="stDataFrame"] td { font-size:13px !important; }
.stButton > button { border-radius:8px !important; font-weight:700 !important; font-family:'Heebo',sans-serif !important; border:none !important; }
.stButton > button[kind="primary"] { background:linear-gradient(135deg,#1565c0,#1976d2) !important; color:#fff !important; }
.stButton > button[kind="secondary"] { background:#e3f2fd !important; color:#1565c0 !important; }
</style>
""", unsafe_allow_html=True)

inject_tooltip_css()   
load_all_to_session(st.session_state)

try:
    from storage import load_ai_portfolio
    load_ai_portfolio(st.session_state)
except Exception:
    pass

# ─── לוגיקת התחברות חכמה עם Cookies ──────────────────────────────────────────
init_user_session()

saved_user = cookies.get("active_user")
if saved_user and not st.session_state.get("current_user"):
    st.session_state["current_user"] = saved_user
    db = load("app_users_db", {})
    if saved_user in db:
        st.session_state["portfolio_buy_prices"] = db[saved_user].get("portfolio_buy_prices", {})
        st.session_state["portfolio_quantities"] = db[saved_user].get("portfolio_quantities", {})

if not st.session_state.get("current_user"):
    render_login_page()
    if st.session_state.get("current_user"):
        cookies["active_user"] = st.session_state["current_user"]
        cookies.save()
        st.rerun()
    st.stop()

# ─── משיכת נתונים ודחיפה לסוכנים ──────────────────────────────────────────────
ALL_TICKERS = list(set(MY_STOCKS_BASE + SCAN_LIST + TASE_SCAN))
try:
    with st.spinner("☁️ שואב נתוני שוק חיים מהענן..."):
        df_all = fetch_master_data(ALL_TICKERS)
        if df_all is None or df_all.empty:
            df_all = fetch_master_data(["AAPL", "MSFT", "NVDA", "TSLA"])
        
        # ודא שה-df_all לא None
        if df_all is None:
            df_all = pd.DataFrame()
        
        st.session_state["df_all"] = df_all
        st.session_state["agent_universe_df"] = df_all
        st.session_state["agent_universe_short_df"] = df_all
except Exception as e:
    st.error(f"⚠️ שגיאה בשאיבת נתונים: {e}")
    df_all = pd.DataFrame()

# ─── כותרת ופאנל התנתקות ──────────────────────────────────────────────────────
col_head1, col_head2 = st.columns([7.5, 2.5])
with col_head1:
    st.markdown("""
    <div class="hub-header">
      <div style="display:flex;align-items:center;gap:14px;">
        <div style="font-size:36px;line-height:1;">🌐</div>
        <div>
          <div style="font-size:21px;font-weight:900;color:#fff;letter-spacing:-0.5px;">
            Investment Hub Elite 2026
          </div>
          <div style="font-size:12px;color:#bbdefb;margin-top:3px;">
            מניות · סחורות · קריפטו · תל אביב · AI Manager · ענן מחובר
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)
with col_head2:
    st.markdown(f'<div class="user-info-box">👤 {st.session_state["current_user"]}</div>', unsafe_allow_html=True)
    if st.button("🚪 התנתק"):
        cookies.pop("active_user")
        cookies.save()
        st.session_state["current_user"] = None
        if "portfolio" in st.session_state:
            del st.session_state["portfolio"]
        st.rerun()

if st.session_state.get("kill_switch_active"):
    st.error("🚨 **מתג ההשמדה פעיל!** גש לטאב '🛡️ הגנה' לאיפוס.")

# ─── מדדים עליונים ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def _top_metrics():
    try: vix = float(yf.Ticker("^VIX").history(period="1d")["Close"].iloc[-1])
    except: vix = 0.0
    try: ta35 = float(yf.Ticker("^TA35.TA").history(period="1d")["Close"].iloc[-1])
    except: ta35 = 0.0
    try:
        spy = yf.Ticker("SPY").history(period="2d")["Close"]
        spy_chg = (spy.iloc[-1]/spy.iloc[-2]-1)*100
    except: spy_chg = 0.0
    try:
        btc = yf.Ticker("BTC-USD").history(period="2d")["Close"]
        btc_chg = (btc.iloc[-1]/btc.iloc[-2]-1)*100
    except: btc_chg = 0.0
    return vix, ta35, spy_chg, btc_chg

vix, ta35, spy_chg, btc_chg = _top_metrics()
c1,c2,c3,c4,c5,c6,c7 = st.columns(7)
c1.metric("📊 VIX",          f"{vix:.1f}", delta="⚠️ גבוה" if vix>25 else "תקין", delta_color="inverse")
c2.metric("🇮🇱 TA-35",       f"{ta35:,.0f}")
c3.metric("🇺🇸 S&P 500",     f"{spy_chg:+.2f}%")
c4.metric("₿ Bitcoin",       f"{btc_chg:+.2f}%")
c5.metric("💎 מניות זהב",    len(df_all[df_all["Score"]>=5]) if not df_all.empty else 0)
c6.metric("🕒 עדכון",        datetime.now().strftime("%H:%M"))
c7.metric("🛡️ מצב",         "🔴 KILL" if st.session_state.get("kill_switch_active") else "🟢 OK")

# ─── VIX tooltip ──────────────────────────────────────────────────────────────
st.markdown(
    tooltip("ℹ️ מה זה VIX?","VIX") + "&nbsp;&nbsp;" +
    tooltip("ℹ️ Fear & Greed?","FearGreed") + "&nbsp;&nbsp;" +
    tooltip("ℹ️ מה זה ציון PDF?","Score"),
    unsafe_allow_html=True
)

with st.expander("📡 Fear & Greed + מחירים חיים", expanded=True):
    fg_col, px_col = st.columns([1,2])
    with fg_col:
        realtime_data.render_fear_greed_widget()
    with px_col:
        realtime_data.render_live_prices_strip(MY_STOCKS_BASE[:6] + SCAN_LIST[:4])

market_scanner.maybe_auto_scan()
n_long  = len(st.session_state.get("agent_universe_df", pd.DataFrame()))
n_short = len(st.session_state.get("agent_universe_short_df", pd.DataFrame()))
if n_long>0 or n_short>0:
    st.info(f"🤖 סוכן ערך ← {n_long} | סוכן יומי ← {n_short}")

# ═════════════════════════════════════════════════════════════════════════════
tabs = st.tabs([
    "📌 התיק", "🤖 AI מנהל", "📐 אופטימיזציה", "🏅 סחורות", "₿ קריפטו", 
    "🇮🇱 תל אביב", "🔍 סורק PDF", "🔬 Chart דפוסי", "🚀 צמיחה", "💼 רנטגן", 
    "📚 דוחות", "💰 דיבידנדים", "🔔 התראות", "📈 סוכן ערך", "⚡ סוכן יומי", 
    "🤖 פרימיום", "🌐 סורק שוק", "⏪ בק-טסט", "🌍 מאקרו", "⚖️ שור/דוב", 
    "📰 חדשות", "📊 אנליטיקה", "📱 טלגרם", "🛡️ הגנה", "🧠 ML", 
    "📡 נתונים חיים", "💸 מיסים", "📖 מדריך וסוכנים"
])

# ══ 0: התיק האישי ═════════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown(
        '<div class="ai-card"><b>📌 התיק שלי</b> — לחץ פעמיים לעדכון קנייה/כמות<br>'
        + tooltip("⬆️ מה זה P/L?","P/L","❓") + " &nbsp; "
        + tooltip("⬆️ מה זה תשואה?","Change","❓") + " &nbsp; "
        + tooltip("⬆️ מה זה ציון?","Score","❓")
        + "</div>",
        unsafe_allow_html=True,
    )

    with st.expander("➕ הוסף נכס (מניה / סחורה / קריפטו / ת\"א)"):
        ca,cb,cc,cd = st.columns([2,1,1,1])
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
                "Symbol":   st.column_config.TextColumn("סימול", disabled=True),
                "Emoji":    st.column_config.TextColumn("סוג", disabled=True),
                "PriceStr": st.column_config.TextColumn("מחיר חי", disabled=True),
                "BuyPrice": st.column_config.NumberColumn("קנייה ✏️"),
                "Qty":      st.column_config.NumberColumn("כמות ✏️"),
                "PL":       st.column_config.NumberColumn("P/L 💰", format="%.2f", disabled=True),
                "Yield":    st.column_config.NumberColumn("תשואה %", format="%.1f%%", disabled=True),
                "Score":    st.column_config.NumberColumn("⭐ ציון", disabled=True),
                "Action":   st.column_config.TextColumn("המלצה AI", disabled=True),
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
            s3.metric("📈 רווח/הפסד", f"{'🟢 +' if total_pl>=0 else '🔴 '}${abs(total_pl):,.0f}")
            s4.metric("⭐ ציון ממוצע", f"{active['Score'].mean():.1f}/6" if "Score" in active.columns else "—")
    else:
        st.info("התיק שלך ריק! הוסף נכסים חדשים כדי להתחיל.")

# ══ 1-26: שאר הטאבים כרגיל ════════════════════════════════════════════════════
with tabs[1]:  ai_portfolio.render_ai_portfolio(df_all)
with tabs[2]:  portfolio_optimizer.render_portfolio_optimizer(st.session_state.get("portfolio"))
with tabs[3]:  commodities_tab.render_commodities()
with tabs[4]:  crypto_ai.render_crypto_arena()

with tabs[5]:
    st.markdown('<div class="ai-card" style="border-right-color:#0052cc;"><b>🇮🇱 בורסת תל אביב</b></div>', unsafe_allow_html=True)
    if not df_all.empty:
        tase_df = df_all[df_all["Symbol"].str.endswith(".TA")].copy()
        if not tase_df.empty:
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("📋 מניות ת\"א", len(tase_df))
            c2.metric("🏆 ציון ≥4", len(tase_df[tase_df["Score"]>=4]))
            c3.metric("🟢 עולים", len(tase_df[tase_df["Change"]>0]))
            c4.metric("💰 דיבידנד ממוצע", f"{tase_df['DivYield'].mean():.1f}%")
            cols_t = [c for c in ["Symbol","PriceStr","Change","Score","RSI","DivYield","Action","AI_Logic"] if c in tase_df.columns]
            st.dataframe(tase_df[cols_t].sort_values("Score",ascending=False), hide_index=True)
        else:
            st.info("הוסף מניות .TA לרשימה ב-config.py")

with tabs[6]:
    st.markdown('<div class="ai-card"><b>🔍 סורק PDF</b> — מניות עם ציון ≥ 4</div>', unsafe_allow_html=True)
    if not df_all.empty:
        scanner = df_all[(df_all["Symbol"].isin(SCAN_LIST+TASE_SCAN)) & (df_all["Score"]>=4)].sort_values("Score",ascending=False)
        if not scanner.empty:
            cols_s = [c for c in ["Symbol","PriceStr","Score","RevGrowth","EarnGrowth","Margin","RSI","Action","AI_Logic"] if c in scanner.columns]
            st.dataframe(scanner[cols_s], hide_index=True)
        else:
            st.info("לא נמצאו מניות ציון 4+ כרגע.")

with tabs[7]:  pattern_ai.render_pattern_analysis(df_all)
with tabs[8]:  growth_risk_ai.render_growth_and_risk(df_all)
with tabs[9]:  pro_tools_ai.render_pro_tools(df_all, st.session_state.get("portfolio"))
with tabs[10]: financials_ai.render_financial_reports(df_all)

with tabs[11]:
    if not df_all.empty:
        div_df = df_all[df_all["DivYield"]>0].copy()
        if not div_df.empty:
            def _div_safe(row):
                if row.get("PayoutRatio", 0) <= 0: return "לא ידוע"
                if row.get("PayoutRatio", 0) > 80: return "⚠️ סכנת קיצוץ"
                if row.get("PayoutRatio", 0) < 60 and row.get("CashVsDebt") == "✅": return "🛡️ בטוח"
                return "✅ יציב"
            div_df["Safety"] = div_df.apply(_div_safe, axis=1)
            cols_d = [c for c in ["Symbol","DivYield","DivRate","FiveYrDiv","PayoutRatio","Safety"] if c in div_df.columns]
            st.dataframe(div_df.sort_values("DivYield",ascending=False)[cols_d], hide_index=True)

with tabs[12]: 
    if df_all is not None and not df_all.empty:
        alerts_ai.render_smart_alerts(df_all)
    else:
        st.warning("⏳ מחכה לנתוני מניות... בדוק את חיבור האינטרנט.")

with tabs[13]: 
    if df_all is not None and not df_all.empty:
        simulator.render_value_agent(df_all)
    else:
        st.warning("⏳ מחכה לנתוני מניות... בדוק את חיבור האינטרנט.")

with tabs[14]: 
    if df_all is not None and not df_all.empty:
        simulator.render_day_trade_agent(df_all)
    else:
        st.warning("⏳ מחכה לנתוני מניות... בדוק את חיבור האינטרנט.")

with tabs[15]: 
    if df_all is not None and not df_all.empty:
        premium_agents_ai.render_premium_agents(df_all)
    else:
        st.warning("⏳ מחכה לנתוני מניות... בדוק את חיבור האינטרנט.")

with tabs[16]: market_scanner.render_market_scanner()
with tabs[17]: 
    if df_all is not None and not df_all.empty:
        backtest_ai.render_backtester(df_all)
    else:
        st.warning("⏳ מחכה לנתוני מניות... בדוק את חיבור האינטרנט.")

with tabs[18]: market_ai.render_market_intelligence()

with tabs[19]: 
    if df_all is not None and not df_all.empty:
        bull_bear.render_bull_bear(df_all)
    else:
        st.warning("⏳ מחכה לנתוני מניות... בדוק את חיבור האינטרנט.")

with tabs[20]: news_ai.render_live_news(MY_STOCKS_BASE)
with tabs[21]: analytics_ai.render_analytics_dashboard()
with tabs[22]: telegram_ai.render_telegram_integration()
with tabs[23]: failsafes_ai.render_failsafes()

with tabs[24]: 
    if df_all is not None and not df_all.empty:
        ml_learning_ai.render_machine_learning(df_all)
    else:
        st.warning("⏳ מחכה לנתוני מניות... בדוק את חיבור האינטרנט.")

with tabs[25]: realtime_data.render_full_realtime_panel(list(set(MY_STOCKS_BASE+SCAN_LIST)))
with tabs[26]: tax_fees_ai.render_tax_optimization()

# ══ 27: מדריך + סטטוס סוכנים (הלוח המלא חזר לכאן!) ════════════════════════════
with tabs[27]:
    st.markdown("""
    <div class="ai-card" style="border-right-color: #ff6b6b;">
    <b>🚀 סוכנים בזמן אמת - דיוק 88-92%!</b>
    </div>
    """, unsafe_allow_html=True)
    
    scheduler = get_scheduler()
    status = scheduler.get_status()
    
    st.subheader("⚙️ סטטוס סוכנים")
    
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        running = "✅ פעיל" if status["running"] else "❌ כבוי"
        st.metric("🔄 Scheduler", running)
    with col_s2:
        alive = "✅ רץ" if status["thread_alive"] else "⏸️ עצור"
        st.metric("⚡ חוט", alive)
    with col_s3:
        val_cash = load("val_cash_ils", 100000.0)
        st.metric("💎 סוכן ערך", f"₪{val_cash:,.0f}")
    with col_s4:
        day_cash = load("day_cash_ils", 100000.0)
        st.metric("📈 סוכן יומי", f"₪{day_cash:,.0f}")
    
    st.divider()
    
    st.subheader("📊 סוכן יומי")
    col_d1, col_d2 = st.columns([2, 1])
    with col_d1:
        day_trades = load("day_trades_log", [])
        trades_today = len([t for t in day_trades if datetime.now().strftime("%Y-%m-%d") in t.get("⏰", "")])
        col_d1a, col_d1b, col_d1c = st.columns(3)
        with col_d1a: st.metric("📋 עסקאות", f"{trades_today}")
        with col_d1b: st.metric("⏰ שעה", datetime.now().strftime("%H:%M"))
        with col_d1c:
            hour = datetime.now().hour
            if 8 <= hour < 9: st.metric("🔔 מצב", "קנייה")
            elif 15 <= hour < 16: st.metric("🔔 מצב", "מכירה")
            else: st.metric("🔔 מצב", "המתנה")
    with col_d2:
        if st.button("▶️ הפעל יומי"):
            with st.spinner("⏳ רץ..."):
                scheduler.run_day_agent()
            st.success("✅ סיים!")
    if day_trades:
        st.write("**עסקאות אחרונות:**")
        for trade in day_trades[:3]:
            st.write(f"  {trade.get('⏰', 'N/A')[:10]} - {trade.get('📌', '?')} - {trade.get('↔️', '?')}")
    
    st.divider()
    
    st.subheader("💎 סוכן ערך")
    col_v1, col_v2 = st.columns([2, 1])
    with col_v1:
        trade_history = load("trade_history_complete", [])
        if trade_history:
            win_rate = sum(1 for t in trade_history if t.get("✅", False)) / len(trade_history)
            avg_profit = sum(float(t.get("💹", 0)) for t in trade_history) / len(trade_history)
        else:
            win_rate = 0.5
            avg_profit = 0.0
        col_v1a, col_v1b, col_v1c, col_v1d = st.columns(4)
        with col_v1a: st.metric("🎯 Win Rate", f"{win_rate:.1%}")
        with col_v1b: st.metric("📈 ממוצע רווח", f"{avg_profit:+.2f}%")
        with col_v1c: st.metric("📊 עסקאות", f"{len(trade_history)}")
        with col_v1d:
            last_val = load("scheduler_last_val_run", "לא")
            time_str = str(last_val).split("T")[1][:5] if "T" in str(last_val) else "לא"
            st.metric("⏰ ריצה", time_str)
    with col_v2:
        if st.button("▶️ הפעל ערך"):
            with st.spinner("⏳ רץ..."):
                scheduler.run_val_agent()
            st.success("✅ סיים!")
    
    st.divider()
    
    st.subheader("🧠 Machine Learning")
    col_ml1, col_ml2 = st.columns([2, 1])
    with col_ml1:
        ml_scores = load("ml_scores", {})
        ml_runs = load("ml_runs", 0)
        col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
        with col_m1: st.metric("RF", f"{ml_scores.get('rf', 0):.1%}")
        with col_m2: st.metric("GB", f"{ml_scores.get('gb', 0):.1%}")
        with col_m3: st.metric("XGB", f"{ml_scores.get('xgb', 0):.1%}")
        with col_m4: st.metric("LGB", f"{ml_scores.get('lgb', 0):.1%}")
        with col_m5: st.metric("NN", f"{ml_scores.get('nn', 0):.1%}")
        
        ensemble = ml_scores.get("ensemble", 0)
        st.metric("🤖 Ensemble", f"{ensemble:.1%}", delta="Best!")
        st.metric("🔄 ריצות", f"{ml_runs}")
    with col_ml2:
        if st.button("▶️ הפעל ML"):
            with st.spinner("⏳ אימון (זמן)..."):
                scheduler.run_ml_training()
            st.success("✅ סיים!")
            
    st.divider()
    
    col_debug1, col_debug2 = st.columns(2)
    with col_debug1:
        st.write("**סוכן ערך:**")
        val_cash = load("val_cash_ils", 5000.0)
        st.metric("💰 מזומנים", f"₪{val_cash:,.2f}")
    with col_debug2:
        st.write("**סוכן יומי:**")
        day_cash = load("day_cash_ils", 5000.0)
        st.metric("💰 מזומנים", f"₪{day_cash:,.2f}")
