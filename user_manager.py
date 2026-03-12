# user_manager.py — ניהול משתמשים, התחברות והפרדת תיקים
import streamlit as st
import hashlib
from storage import load, save

USERS_DB_KEY = "app_users_db"

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def init_user_session():
    if "current_user" not in st.session_state:
        st.session_state["current_user"] = None
    if "users_db" not in st.session_state:
        st.session_state["users_db"] = load(USERS_DB_KEY, {})

def register_user(username, password):
    db = st.session_state["users_db"]
    if username in db:
        return False, "שם המשתמש כבר קיים במערכת."
    
    db[username] = {
        "password": _hash_password(password),
        "portfolio_buy_prices": {},
        "portfolio_quantities": {}
    }
    save(USERS_DB_KEY, db)
    st.session_state["users_db"] = db
    return True, "ההרשמה בוצעה בהצלחה! כעת ניתן להתחבר."

def authenticate_user(username, password):
    db = st.session_state["users_db"]
    if username in db and db[username]["password"] == _hash_password(password):
        st.session_state["current_user"] = username
        # שולף את התיק הפרטי של המשתמש לסשן
        st.session_state["portfolio_buy_prices"] = db[username].get("portfolio_buy_prices", {})
        st.session_state["portfolio_quantities"] = db[username].get("portfolio_quantities", {})
        # מנקה תיק זמני קודם אם היה
        if "portfolio" in st.session_state:
            del st.session_state["portfolio"]
        return True
    return False

def reset_password(username, new_password):
    db = st.session_state["users_db"]
    if username in db:
        db[username]["password"] = _hash_password(new_password)
        save(USERS_DB_KEY, db)
        st.session_state["users_db"] = db
        return True, "הסיסמה שונתה בהצלחה! נא להתחבר עם הסיסמה החדשה."
    return False, "שם המשתמש לא נמצא במערכת."

def save_user_data():
    username = st.session_state.get("current_user")
    if username:
        db = st.session_state["users_db"]
        db[username]["portfolio_buy_prices"] = st.session_state.get("portfolio_buy_prices", {})
        db[username]["portfolio_quantities"] = st.session_state.get("portfolio_quantities", {})
        save(USERS_DB_KEY, db)

def render_login_page():
    st.markdown("""
    <style>
    /* הסתרת סרגל הצד לחלוטין גם במסך ההתחברות */
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    .stApp { background:#f5f7fa !important; direction:rtl; text-align:right; font-family:'Heebo',sans-serif; }
    .hub-header {
        background:linear-gradient(135deg,#1565c0 0%,#1976d2 55%,#42a5f5 100%);
        border-radius:14px; padding:16px 22px; margin-bottom:12px;
        box-shadow:0 4px 18px rgba(21,101,192,0.22);
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="hub-header"><div style="font-size:24px;color:#fff;font-weight:bold;">🔒 התחברות — Investment Hub Elite</div></div>', unsafe_allow_html=True)
    
    tab1, tab2, tab3 = st.tabs(["🔑 כניסה", "📝 הרשמה", "❓ שכחתי סיסמה"])
    
    with tab1:
        st.subheader("התחבר לחשבון שלך")
        login_user = st.text_input("שם משתמש", key="log_user")
        login_pass = st.text_input("סיסמה", type="password", key="log_pass")
        if st.button("כניסה", type="primary"):
            if authenticate_user(login_user, login_pass):
                st.success(f"ברוך הבא {login_user}!")
                st.rerun()
            else:
                st.error("שם משתמש או סיסמה שגויים.")
                
    with tab2:
        st.subheader("צור חשבון חדש")
        st.info("💡 כל משתמש חדש מקבל תיק ריק משלו לחלוטין.")
        reg_user = st.text_input("שם משתמש", key="reg_user")
        reg_pass = st.text_input("סיסמה", type="password", key="reg_pass")
        if st.button("הרשמה"):
            if reg_user and len(reg_pass) >= 4:
                success, msg = register_user(reg_user, reg_pass)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.warning("נא להזין שם משתמש וסיסמה (לפחות 4 תווים).")
                
    with tab3:
        st.subheader("שחזור סיסמה")
        st.info("ניתן לאפס את הסיסמה ישירות על ידי הזנת שם המשתמש שלך והסיסמה החדשה שתרצה.")
        reset_user = st.text_input("שם משתמש לאיפוס", key="res_user")
        reset_pass = st.text_input("סיסמה חדשה", type="password", key="res_pass")
        if st.button("אפס סיסמה"):
            if reset_user and len(reset_pass) >= 4:
                success, msg = reset_password(reset_user, reset_pass)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.warning("נא להזין שם משתמש וסיסמה חדשה (לפחות 4 תווים).")
