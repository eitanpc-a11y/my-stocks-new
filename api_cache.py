# api_cache.py — TTL Cache עמיד לתהליכי רקע
# ════════════════════════════════════════════════════════════════════════
# הבעיה: @st.cache_data לא עובד בתהליך רקע (scheduler_agents.py runs in Thread).
# הפתרון: cache בזיכרון + fallback לגיבוי ב-DB (storage.py) לפי TTL.
#
# משתמשים ב:
#   cached_api_call(key, fn, ttl_seconds)
#   cache_get(key, ttl_seconds)  /  cache_set(key, value)
# ════════════════════════════════════════════════════════════════════════
import time
import threading
import logging

logger = logging.getLogger(__name__)

# ── In-Memory cache (מנוגד לסשן, לא נשמר לדיסק אבל מאוד מהיר) ────────
_mem: dict = {}
_lock = threading.Lock()


def cache_get(key: str, ttl: int):
    """
    מחזיר (value, hit) מהזיכרון אם הערך עדיין תקף.
    hit=False → יש לרענן.
    """
    with _lock:
        entry = _mem.get(key)
    if entry is None:
        return None, False
    value, ts = entry
    if time.time() - ts > ttl:
        return None, False
    return value, True


def cache_set(key: str, value):
    with _lock:
        _mem[key] = (value, time.time())


def cached_api_call(key: str, fn, ttl: int):
    """
    מריץ fn() רק אם הקאש פג תוקף.
    key    — מחרוזת ייחודית (e.g. f"earnings_{symbol}")
    fn     — callable ללא ארגומנטים (השתמש ב-lambda)
    ttl    — שניות תוקף
    """
    value, hit = cache_get(key, ttl)
    if hit:
        return value
    try:
        value = fn()
    except Exception as e:
        logger.warning(f"api_cache: error in fn for key={key}: {e}")
        value = None
    cache_set(key, value)
    return value


# ── API Rate Limiter — מרווח מינימלי בין קריאות לאותו שירות ─────────
_last_call: dict = {}
_rl_lock = threading.Lock()

def throttle(service: str, min_gap: float = 1.0):
    """
    חוסם עד ש-min_gap שניות עברו מאז הקריאה האחרונה לאותו service.
    ברירת מחדל: 1 שנייה בין כל קריאה ל-yfinance.
    """
    with _rl_lock:
        last = _last_call.get(service, 0)
        wait = min_gap - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        _last_call[service] = time.time()
