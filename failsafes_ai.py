# failsafes_ai.py — Kill Switch + Circuit Breaker
import streamlit as st
from datetime import datetime


def _log(msg):
    if "failsafe_log" not in st.session_state:
        st.session_state.failsafe_log = []
    st.session_state.failsafe_log.insert(0, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def render_failsafes():
    st.markdown(
        '<div class="ai-card" style="border-right-color: #d32f2f;">'
        '<b>🛡️ מנגנון הגנה:</b> Kill Switch, Circuit Breaker, Stop Loss אוטומטי.</div>',
        unsafe_allow_html=True,
    )

    for key, default in [
        ("kill_switch_active", False), ("failsafe_log", []),
        ("daily_loss_pct", 0.0), ("circuit_breaker_triggered", False),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    if st.session_state.kill_switch_active:
        st.error("🚨 **מתג ההשמדה פעיל!** כל המסחר מושהה.")
    elif st.session_state.circuit_breaker_triggered:
        st.warning("⚡ **Circuit Breaker הופעל!**")
    else:
        st.success("✅ **מערכת ההגנה תקינה.**")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("📉 הפסד יומי", f"{st.session_state.daily_loss_pct:.1f}%", delta_color="inverse")
    m2.metric("🛡️ Kill Switch", "🔴 פעיל" if st.session_state.kill_switch_active else "🟢 כבוי")
    m3.metric("⚡ Circuit Breaker", "🔴 הופעל" if st.session_state.circuit_breaker_triggered else "🟢 תקין")
    m4.metric("📝 אירועי אבטחה", len(st.session_state.failsafe_log))

    st.subheader("⚙️ הגדרות")
    col1, col2 = st.columns(2)
    with col1:
        max_loss = st.slider("🚫 הפסד יומי מקסימלי (%)", 1.0, 20.0, 5.0, 0.5, key="fs_maxloss")
        st.slider("💼 פוזיציה מקסימלית (% מתיק)", 5.0, 50.0, 20.0, 5.0, key="fs_maxpos")
        st.slider("🛑 Stop Loss (%)", 1.0, 15.0, 5.0, 0.5, key="fs_stoploss")
    with col2:
        st.slider("🎯 Take Profit (%)", 1.0, 30.0, 10.0, 0.5, key="fs_tp")
        vix_halt = st.slider("😨 עצור אם VIX >", 20, 80, 40, 5, key="fs_vix")
        st.number_input("📊 מקסימום פוזיציות", 1, 20, 5, key="fs_maxpositions")

    st.subheader("🔧 סימולציות")
    b1, b2, b3, b4 = st.columns(4)
    with b1:
        if st.button("📉 הדמה -3%", key="fs_sim3"):
            st.session_state.daily_loss_pct = 3.0
            _log("הדמיית הפסד -3%")
            if 3.0 >= max_loss:
                st.session_state.circuit_breaker_triggered = True
                _log("⚡ Circuit Breaker!")
            st.rerun()
    with b2:
        if st.button("📉 הדמה -7%", key="fs_sim7"):
            st.session_state.daily_loss_pct = 7.0
            st.session_state.circuit_breaker_triggered = True
            _log("🚨 הפסד קריטי -7%!")
            st.rerun()
    with b3:
        if st.button("😨 הדמה VIX 45", key="fs_vix45"):
            st.session_state.circuit_breaker_triggered = True
            _log("⚠️ VIX הגיע ל-45")
            st.rerun()
    with b4:
        if st.button("🔄 איפוס יום", key="fs_resetday"):
            st.session_state.daily_loss_pct = 0.0
            st.session_state.circuit_breaker_triggered = False
            _log("✅ איפוס יומי")
            st.rerun()

    st.divider()
    st.subheader("☢️ מתג השמדה")
    ck1, ck2 = st.columns(2)
    with ck1:
        if not st.session_state.kill_switch_active:
            if st.button("🚨 הפעל מתג השמדה!", type="primary", key="fs_killswitch"):
                st.session_state.kill_switch_active = True
                for k in ["val_portfolio","day_portfolio","div_portfolio","ins_portfolio","deep_portfolio"]:
                    if k in st.session_state:
                        st.session_state[k] = []
                _log("🚨 KILL SWITCH! כל הפוזיציות נסגרו!")
                st.rerun()
        else:
            if st.button("✅ איפוס — חזרה לפעולה", key="fs_resume"):
                st.session_state.kill_switch_active = False
                st.session_state.circuit_breaker_triggered = False
                st.session_state.daily_loss_pct = 0.0
                _log("✅ מערכת אופסה")
                st.rerun()
    with ck2:
        st.markdown("""
        🔴 כל הסוכנים נעצרים מיידית  
        🔴 כל הפוזיציות נסגרות למזומן  
        🔴 לא ניתן לפתוח פקודות חדשות  
        🟢 נתונים נשמרים  
        🟢 ניתן לאפס בלחיצה
        """)

    st.subheader("⚙️ כללים נוספים")
    r1, r2 = st.columns(2)
    with r1:
        st.toggle("🔒 מנע Pre-Market", value=True, key="fs_pre")
        st.toggle("🔒 מנע After-Hours", value=True, key="fs_after")
        st.toggle("⚠️ אשר עסקאות >$5K", value=True, key="fs_big")
    with r2:
        st.toggle("📊 ניטור VIX", value=True, key="fs_vix_toggle")
        st.toggle("🔄 Rebalance בסוף יום", value=False, key="fs_rebal")
        st.toggle("📱 התראה לטלגרם", value=False, key="fs_tg")

    if st.session_state.failsafe_log:
        with st.expander(f"📋 יומן ({len(st.session_state.failsafe_log)} אירועים)"):
            for ev in st.session_state.failsafe_log[:40]:
                icon = "🔴" if any(x in ev for x in ["KILL","קריטי","Circuit"]) else "🟡" if "הדמ" in ev else "🟢"
                st.markdown(f"{icon} `{ev}`")
            if st.button("🗑️ נקה יומן", key="fs_clearlog"):
                st.session_state.failsafe_log = []
                st.rerun()
