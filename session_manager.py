# session_manager.py — ניהול סשן עם st.query_params (ללא חבילות חיצוניות)
# שומר טוקן ב-URL: ?t=TOKEN — מתמיד גם אחרי ריענון ופתיחת טאב חדש.
import streamlit as st
import uuid
from datetime import datetime, timedelta
from storage import load, save

SESSIONS_KEY  = "hub_sessions"   # מפתח אחסון לכל הטוקנים
TOKEN_PARAM   = "t"              # שם פרמטר ה-URL
TOKEN_DAYS    = 30               # תוקף הסשן בימים


# ─── פנימי ────────────────────────────────────────────────────────────────────
def _load_sessions() -> dict:
    return load(SESSIONS_KEY, {})

def _save_sessions(sessions: dict):
    save(SESSIONS_KEY, sessions)

def _clean_expired(sessions: dict) -> dict:
    """מסיר טוקנים שפגו תוקפם."""
    now = datetime.now().isoformat()
    return {t: v for t, v in sessions.items() if v.get("expires", "") > now}


# ─── API ציבורי ───────────────────────────────────────────────────────────────
def create_session(username: str) -> str:
    """יוצר טוקן חדש לאחר כניסה מוצלחת ושומר ב-storage."""
    token    = str(uuid.uuid4()).replace("-", "")
    expires  = (datetime.now() + timedelta(days=TOKEN_DAYS)).isoformat()
    sessions = _load_sessions()
    sessions = _clean_expired(sessions)
    sessions[token] = {"username": username, "expires": expires,
                       "created": datetime.now().isoformat()}
    _save_sessions(sessions)
    return token


def get_user_from_token(token: str) -> str | None:
    """מחזיר שם משתמש לטוקן תקף, או None."""
    if not token:
        return None
    sessions = _load_sessions()
    entry    = sessions.get(token)
    if not entry:
        return None
    if entry.get("expires", "") < datetime.now().isoformat():
        sessions.pop(token, None)
        _save_sessions(sessions)
        return None
    return entry["username"]


def delete_session(token: str):
    """מוחק טוקן — מתבצע בלוגאאוט."""
    sessions = _load_sessions()
    sessions.pop(token, None)
    _save_sessions(sessions)


def get_current_token() -> str | None:
    """קורא את הטוקן מה-URL."""
    try:
        return st.query_params.get(TOKEN_PARAM)
    except Exception:
        return None


def set_token_in_url(token: str):
    """כותב את הטוקן לפרמטר ה-URL."""
    try:
        st.query_params[TOKEN_PARAM] = token
    except Exception:
        pass


def clear_token_from_url():
    """מנקה את הטוקן מה-URL בלוגאאוט."""
    try:
        st.query_params.pop(TOKEN_PARAM, None)
    except Exception:
        pass


def try_auto_login() -> str | None:
    """
    מנסה להתחבר אוטומטית מהטוקן שב-URL.
    מחזיר שם משתמש אם הצליח, None אחרת.
    """
    token = get_current_token()
    return get_user_from_token(token)
