# macro_calendar.py — לוח מקרו קלנדר ללא API
# ✅ תאריכי FOMC, CPI, NFP ל-2025-2026 — hardcoded
# ✅ is_macro_event_soon(days) — בודק אם אירוע גדול בטווח ימים
# ✅ zero API calls — כל הנתונים מוטמעים בקוד
from datetime import date, timedelta

# ════════════════════════════════════════════════════════════════════════
# תאריכי אירועים מרכזיים (UTC) — עדכן ידנית לפי לוח שנת הפד
# ════════════════════════════════════════════════════════════════════════

FOMC_DATES = [
    # 2025
    date(2025, 1, 29), date(2025, 3, 19), date(2025, 5, 7),
    date(2025, 6, 18), date(2025, 7, 30), date(2025, 9, 17),
    date(2025, 10, 29), date(2025, 12, 10),
    # 2026
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29),
    date(2026, 6, 17), date(2026, 7, 29), date(2026, 9, 16),
    date(2026, 10, 28), date(2026, 12, 9),
]

CPI_DATES = [
    # 2025
    date(2025, 1, 15), date(2025, 2, 12), date(2025, 3, 12),
    date(2025, 4, 10), date(2025, 5, 13), date(2025, 6, 11),
    date(2025, 7, 15), date(2025, 8, 13), date(2025, 9, 10),
    date(2025, 10, 15), date(2025, 11, 12), date(2025, 12, 10),
    # 2026
    date(2026, 1, 14), date(2026, 2, 11), date(2026, 3, 11),
    date(2026, 4, 9),  date(2026, 5, 13), date(2026, 6, 10),
    date(2026, 7, 15), date(2026, 8, 12), date(2026, 9, 9),
    date(2026, 10, 14), date(2026, 11, 11), date(2026, 12, 9),
]

NFP_DATES = [
    # 2025 — Non-Farm Payrolls (תמיד ראשון שישי של חודש)
    date(2025, 1, 10), date(2025, 2, 7), date(2025, 3, 7),
    date(2025, 4, 4),  date(2025, 5, 2), date(2025, 6, 6),
    date(2025, 7, 4),  date(2025, 8, 1), date(2025, 9, 5),
    date(2025, 10, 3), date(2025, 11, 7), date(2025, 12, 5),
    # 2026
    date(2026, 1, 9),  date(2026, 2, 6), date(2026, 3, 6),
    date(2026, 4, 3),  date(2026, 5, 8), date(2026, 6, 5),
    date(2026, 7, 10), date(2026, 8, 7), date(2026, 9, 4),
    date(2026, 10, 2), date(2026, 11, 6), date(2026, 12, 4),
]

# כל האירועים ביחד
ALL_MACRO_EVENTS = sorted(set(FOMC_DATES + CPI_DATES + NFP_DATES))

# שמות לתצוגה
_EVENT_NAMES = {}
for d in FOMC_DATES: _EVENT_NAMES[d] = "🏦 FOMC"
for d in CPI_DATES:  _EVENT_NAMES[d] = "📊 CPI"
for d in NFP_DATES:  _EVENT_NAMES.setdefault(d, "📋 NFP")


def is_macro_event_soon(days: int = 1) -> dict:
    """
    מחזיר {is_soon: bool, event_name: str, days_away: int, event_date: date}
    days=1  → בודק אם יש אירוע היום או מחר
    days=2  → בודק אם יש אירוע ב-2 הימים הבאים
    """
    today = date.today()
    window_end = today + timedelta(days=days)
    for ev_date in ALL_MACRO_EVENTS:
        if today <= ev_date <= window_end:
            return {
                "is_soon":    True,
                "event_name": _EVENT_NAMES.get(ev_date, "📅 מקרו"),
                "days_away":  (ev_date - today).days,
                "event_date": ev_date,
            }
    return {
        "is_soon":    False,
        "event_name": "",
        "days_away":  999,
        "event_date": None,
    }


def next_macro_event() -> dict:
    """מחזיר האירוע הבא הקרוב ביותר."""
    today = date.today()
    for ev_date in ALL_MACRO_EVENTS:
        if ev_date >= today:
            return {
                "event_name": _EVENT_NAMES.get(ev_date, "📅 מקרו"),
                "days_away":  (ev_date - today).days,
                "event_date": ev_date,
            }
    return {"event_name": "—", "days_away": 999, "event_date": None}
