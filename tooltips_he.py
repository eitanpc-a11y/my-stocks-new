# tooltips_he.py — מילון הסברים עבריים לכל מושג פיננסי במערכת
# ════════════════════════════════════════════════════════════════════════════
# שימוש:
#   from tooltips_he import tooltip, inject_tooltip_css
#   inject_tooltip_css()
#   st.markdown(tooltip("RSI", "RSI"), unsafe_allow_html=True)
# ════════════════════════════════════════════════════════════════════════════

import streamlit as st

# ─── מילון הסברים ─────────────────────────────────────────────────────────────
TOOLTIPS = {
    # ── מדדים טכניים ──────────────────────────────────────────────────────────
    "RSI": {
        "title": "RSI — מדד חוזק יחסי",
        "body": """
📊 <b>Relative Strength Index</b> — מדד בין 0 ל-100 שמראה האם המניה נקנתה/נמכרה יתר על המידה.<br><br>
• <b>מתחת ל-30</b> 🟢 — מכירת יתר. המניה ירדה מהר מדי. <i>הזדמנות קנייה אפשרית.</i><br>
• <b>30–50</b> ⬜ — ניטרלי-שלילי. שוק חלש.<br>
• <b>50–70</b> ⬜ — ניטרלי-חיובי. שוק בריא.<br>
• <b>מעל 70</b> 🔴 — קנייה יתר. המניה עלתה מהר מדי. <i>שקול מימוש.</i>
        """,
    },
    "MA50": {
        "title": "MA50 — ממוצע נע 50 יום",
        "body": """
📈 <b>Moving Average 50 Days</b> — ממוצע מחיר המניה ב-50 הימים האחרונים.<br><br>
• <b>מחיר מעל MA50</b> 🟢 — מגמה עולה. השוק אופטימי.<br>
• <b>מחיר מתחת MA50</b> 🔴 — מגמה יורדת. שוק חלש.<br><br>
💡 <i>כאשר MA50 חוצה מעל MA200 = "Golden Cross" — סיגנל עוצמה מאוד חיובי!</i>
        """,
    },
    "MA200": {
        "title": "MA200 — ממוצע נע 200 יום",
        "body": """
📈 <b>Moving Average 200 Days</b> — ממוצע מחיר ב-200 הימים האחרונים. קו התמיכה/התנגדות הארוך ביותר.<br><br>
• <b>מחיר מעל MA200</b> 🟢 — מגמה ארוכת-טווח חיובית. (Bull Market)<br>
• <b>מחיר מתחת MA200</b> 🔴 — מגמה ארוכת-טווח שלילית. (Bear Market)
        """,
    },
    "Score": {
        "title": "ציון PDF — 0 עד 6",
        "body": """
⭐ <b>ציון איכות מקיף</b> — מבוסס על 6 קריטריונים:<br><br>
1. 📈 <b>צמיחת מכירות</b> מעל 10%<br>
2. 💰 <b>צמיחת רווחים</b> מעל 10%<br>
3. 📊 <b>שולי רווח</b> מעל 10%<br>
4. 🏦 <b>ROE</b> (תשואה על הון) מעל 15%<br>
5. 💵 <b>מזומן > חוב</b><br>
6. 🔵 <b>אפס חוב</b><br><br>
<b>5-6</b> 💎 = מניית זהב | <b>3-4</b> ✅ = טוב | <b>0-2</b> ⚠️ = סיכון
        """,
    },
    "P/L": {
        "title": "P/L — רווח/הפסד",
        "body": """
💰 <b>Profit & Loss</b> — הרווח או ההפסד הנוכחי על ההשקעה שלך.<br><br>
<b>חישוב:</b> (מחיר נוכחי − מחיר קנייה) × כמות מניות<br><br>
• 🟢 מספר חיובי = אתה ברווח<br>
• 🔴 מספר שלילי = אתה בהפסד<br><br>
💡 <i>זה "רווח על הנייר" — נהפך לאמיתי רק כשתמכור.</i>
        """,
    },
    "FairValue": {
        "title": "שווי הוגן (Fair Value)",
        "body": """
🎯 <b>השווי האמיתי של המניה לפי חישוב AI</b><br><br>
<b>שיטה:</b> Free Cash Flow × 15 ÷ מספר מניות<br><br>
• <b>מחיר שוק < שווי הוגן</b> 🟢 — המניה זולה. <i>כדאי לשקול קנייה.</i><br>
• <b>מחיר שוק > שווי הוגן</b> 🔴 — המניה יקרה. <i>שקול להמתין.</i><br><br>
💡 <i>זה הערכה — לא מדע מדויק. תמיד גבה עם ניתוח נוסף.</i>
        """,
    },
    "Sharpe": {
        "title": "Sharpe Ratio — יחס תשואה לסיכון",
        "body": """
⚖️ <b>Sharpe Ratio</b> — מודד כמה תשואה מקבלים לכל יחידת סיכון.<br><br>
<b>חישוב:</b> (תשואה שנתית − ריבית חסרת-סיכון) ÷ תנודתיות<br><br>
• <b>מעל 2.0</b> 💎 = מצוין<br>
• <b>1.0–2.0</b> 🟢 = טוב<br>
• <b>0.5–1.0</b> 🟡 = סביר<br>
• <b>מתחת 0.5</b> 🔴 = לא שווה את הסיכון<br><br>
💡 <i>ממשקיע מתחיל: Sharpe > 1 = התיק שלך "עובד טוב".</i>
        """,
    },
    "Beta": {
        "title": "Beta — רגישות לשוק",
        "body": """
🔢 <b>Beta</b> — כמה המניה/תיק נע ביחס ל-S&P 500.<br><br>
• <b>Beta = 1.0</b> ⬜ — זז בדיוק כמו השוק<br>
• <b>Beta > 1</b> 🔴 — מגנן: עולה/יורד <i>יותר</i> מהשוק (סיכון גבוה)<br>
• <b>Beta < 1</b> 🟢 — יציב: עולה/יורד <i>פחות</i> מהשוק (סיכון נמוך)<br>
• <b>Beta שלילי</b> 💎 — נע <i>הפוך</i> לשוק (גידור מושלם — כמו זהב)<br><br>
💡 <i>כמשקיע מתחיל: Beta 0.7–1.3 = בטוח. מעל 1.5 = הימור.</i>
        """,
    },
    "MaxDD": {
        "title": "Max Drawdown — ירידה מקסימלית",
        "body": """
📉 <b>Maximum Drawdown</b> — הירידה הגדולה ביותר מהשיא לשפל בתקופה נתונה.<br><br>
<b>דוגמה:</b> תיק עלה ל-₪100,000 ואז ירד ל-₪70,000 → MaxDD = -30%<br><br>
• <b>מתחת -10%</b> 🟢 = ירידה קטנה, תיק יציב<br>
• <b>-10% עד -25%</b> 🟡 = ירידה בינונית, רגיל בשוק<br>
• <b>מעל -25%</b> 🔴 = ירידה גדולה, בדוק את הסיכון<br><br>
💡 <i>שאל את עצמך: "האם אני יכול לספוג ירידה של X% בלי לפחד?"</i>
        """,
    },
    "DivYield": {
        "title": "תשואת דיבידנד",
        "body": """
💰 <b>Dividend Yield</b> — אחוז מהמחיר שמחולק לך כדיבידנד בשנה.<br><br>
<b>דוגמה:</b> מניה ב-$100, דיבידנד $3/שנה → תשואה = 3%<br><br>
• <b>מעל 4%</b> 🟢 = גבוה (כמו שכ"ד מנדל"ן)<br>
• <b>2%–4%</b> ✅ = בריא ויציב<br>
• <b>מתחת 1%</b> ⬜ = חברת צמיחה (מחזירה פחות)<br><br>
💡 <i>דיבידנד גבוה מדי (>7%) עלול להיות מסוכן — בדוק PayoutRatio!</i>
        """,
    },
    "PayoutRatio": {
        "title": "PayoutRatio — שיעור חלוקה",
        "body": """
📊 <b>Payout Ratio</b> — כמה אחוז מהרווח החברה מחלקת כדיבידנד.<br><br>
• <b>מתחת 50%</b> 💎 = בטוח מאוד, יש מקום לגדול<br>
• <b>50%–75%</b> ✅ = יציב ובריא<br>
• <b>75%–90%</b> 🟡 = צפוף, עלול לקצץ<br>
• <b>מעל 90%</b> 🔴 = מסוכן! ייתכן שהדיבידנד יקוצץ<br><br>
💡 <i>Payout > 100% = החברה משלמת יותר ממה שהיא מרוויחה!</i>
        """,
    },
    "ROE": {
        "title": "ROE — תשואה על ההון",
        "body": """
🏦 <b>Return on Equity</b> — כמה רווח החברה מייצרת על כל ₪ של הון בעלים.<br><br>
<b>דוגמה:</b> ROE 20% = על כל $100 שהמשקיעים שמו, החברה מרוויחה $20<br><br>
• <b>מעל 20%</b> 💎 = מצוין — חברה יעילה מאוד<br>
• <b>15%–20%</b> 🟢 = טוב<br>
• <b>10%–15%</b> 🟡 = סביר<br>
• <b>מתחת 10%</b> 🔴 = חלש — החברה לא יעילה
        """,
    },
    "Margin": {
        "title": "שולי רווח נקי",
        "body": """
📊 <b>Net Profit Margin</b> — כמה מכל ₪ הכנסה נשאר כרווח נקי.<br><br>
<b>דוגמה:</b> מכירות $1M, רווח נקי $150K → Margin = 15%<br><br>
• <b>מעל 20%</b> 💎 = מצוין (כמו Apple, NVIDIA)<br>
• <b>10%–20%</b> ✅ = טוב<br>
• <b>5%–10%</b> 🟡 = סביר<br>
• <b>מתחת 5%</b> 🔴 = שולי — כל בעיה תפגע ברווחיות
        """,
    },
    "RevGrowth": {
        "title": "צמיחת מכירות (Revenue Growth)",
        "body": """
📈 <b>Revenue Growth</b> — באיזה קצב גדלות המכירות לעומת השנה הקודמת.<br><br>
• <b>מעל 20%</b> 🚀 = חברת צמיחה עליונה<br>
• <b>10%–20%</b> 🟢 = צמיחה בריאה<br>
• <b>5%–10%</b> ✅ = יציב<br>
• <b>מתחת 5%</b> ⬜ = תקוע<br>
• <b>שלילי</b> 🔴 = חברה מצטמקת — אזהרה!
        """,
    },
    "EarnGrowth": {
        "title": "צמיחת רווחים",
        "body": """
💰 <b>Earnings Growth</b> — קצב גידול הרווח נקי.<br><br>
<b>חשוב מאשר צמיחת מכירות!</b> חברה יכולה למכור יותר אבל להרוויח פחות.<br><br>
• <b>מעל 20%</b> 💎 = מעולה<br>
• <b>10%–20%</b> 🟢 = בריא<br>
• <b>0%–10%</b> 🟡 = איטי<br>
• <b>שלילי</b> 🔴 = בעיה — מה קורה?
        """,
    },
    "InsiderHeld": {
        "title": "החזקת בעלי עניין (Insider Held)",
        "body": """
🏛️ <b>Insider Ownership</b> — כמה אחוז מהמניות מחזיקים המנהלים ומייסדי החברה.<br><br>
• <b>מעל 10%</b> 💎 = ההנהלה מאמינה בחברה (אלון מאסק מחזיק ~13% בטסלה)<br>
• <b>5%–10%</b> 🟢 = חיובי<br>
• <b>1%–5%</b> ✅ = רגיל<br>
• <b>מתחת 1%</b> ⬜ = ההנהלה מכרה הרבה<br><br>
💡 <i>כאשר מנהלים קונים מניות של החברה שלהם → סיגנל חיובי חזק!</i>
        """,
    },
    "TargetUpside": {
        "title": "פוטנציאל עלייה (Target Upside)",
        "body": """
🎯 <b>Target Upside</b> — כמה אחוזים אנליסטי וול סטריט חושבים שהמניה תעלה.<br><br>
<b>דוגמה:</b> מחיר היום $100, יעד אנליסטים $130 → Upside = 30%<br><br>
• <b>מעל 30%</b> 🚀 = פוטנציאל גבוה לפי אנליסטים<br>
• <b>15%–30%</b> 🟢 = אטרקטיבי<br>
• <b>0%–15%</b> ✅ = סביר<br>
• <b>שלילי</b> 🔴 = אנליסטים חושבים שהמחיר גבוה מדי<br><br>
💡 <i>אנליסטים לא תמיד צודקים — השתמש כנקודת מבט אחת בלבד!</i>
        """,
    },
    "Change": {
        "title": "שינוי יומי %",
        "body": """
📊 <b>Daily Change</b> — בכמה אחוזים השתנה מחיר המניה היום.<br><br>
• 🟢 מספר חיובי = המניה עלתה היום<br>
• 🔴 מספר שלילי = המניה ירדה היום<br><br>
💡 <i>שינוי יומי של מניה רגילה: בדרך כלל בין -3% ל+3%. מעל 5% = אירוע חריג.</i>
        """,
    },
    "VIX": {
        "title": "VIX — מדד הפחד",
        "body": """
😱 <b>CBOE Volatility Index</b> — מדד הפחד של וול סטריט.<br><br>
• <b>מתחת 15</b> 😌 = שוק שקט, אופטימי<br>
• <b>15–25</b> 😐 = שגרה<br>
• <b>25–35</b> 😰 = פחד — תנודתיות גבוהה<br>
• <b>מעל 35</b> 😱 = פאניקה! כולם מוכרים<br><br>
💡 <i>"כשהדם ברחובות, קנה" — בורשם: VIX גבוה = הזדמנות קנייה לאמיצים!</i>
        """,
    },
    "FearGreed": {
        "title": "Fear & Greed Index",
        "body": """
😱🤑 <b>מדד פחד/חמדנות של CNN Money</b> — 0 עד 100.<br><br>
• <b>0–25</b> 😱 = פחד קיצוני → <i>קנה! כולם מוכרים מפחד</i><br>
• <b>25–45</b> 😰 = פחד<br>
• <b>45–55</b> 😐 = ניטרלי<br>
• <b>55–75</b> 🤑 = חמדנות<br>
• <b>75–100</b> 🚨 = חמדנות קיצונית → <i>מכור! כולם קונים יתר על המידה</i><br><br>
💡 <i> וורן באפט: "היה פחדן כשכולם חמדנים, היה חמדן כשכולם פחדים"</i>
        """,
    },
    "GoldenCross": {
        "title": "Golden Cross",
        "body": """
🌟 <b>Golden Cross</b> — אחד הסיגנלים החזקים ביותר בניתוח טכני!<br><br>
מה זה? MA50 חוצה מעל MA200.<br><br>
המשמעות: המגמה הקצרה (50 יום) חזקה יותר מהארוכה (200 יום) → <b>תחילת עלייה ארוכת-טווח</b><br><br>
💡 <i>היסטורית, Golden Cross ב-S&P 500 הניב תשואה ממוצעת של +15% ב-12 חודשים.</i>
        """,
    },
    "DeathCross": {
        "title": "Death Cross",
        "body": """
💀 <b>Death Cross</b> — סיגנל אזהרה חמור!<br><br>
מה זה? MA50 חוצה מתחת ל-MA200.<br><br>
המשמעות: המגמה הקצרה חלשה מהארוכה → <b>התחלה אפשרית של ירידה ממושכת</b><br><br>
💡 <i>שקול להפחית חשיפה למניה עד שיחול היפוך מגמה.</i>
        """,
    },
    "StopLoss": {
        "title": "Stop-Loss — עצור הפסד",
        "body": """
🛡️ <b>Stop-Loss</b> — מחיר שמתחתיו המערכת תמכור אוטומטית כדי להגביל הפסד.<br><br>
<b>דוגמה:</b> קנית ב-$100 עם Stop-Loss 8% → אם המחיר יגיע ל-$92 → מכירה אוטומטית<br><br>
💡 <i>Stop-Loss מגן על ההון שלך! ללא Stop-Loss, הפסד קטן יכול להפוך לגדול.</i>
        """,
    },
    "TakeProfit": {
        "title": "Take-Profit — מימוש רווח",
        "body": """
🎯 <b>Take-Profit</b> — מחיר שמעליו המערכת תמכור אוטומטית כדי לממש רווח.<br><br>
<b>דוגמה:</b> קנית ב-$100 עם Take-Profit 20% → כשמגיע ל-$120 → מכירה אוטומטית<br><br>
💡 <i>רווח שלא מומש הוא עדיין "על הנייר". Take-Profit נועל את הרווח בפועל!</i>
        """,
    },
    "Inflation": {
        "title": "אינפלציה (CPI)",
        "body": """
📊 <b>Consumer Price Index</b> — מדד המחירים לצרכן. כמה יקר יותר לחיות מדי שנה.<br><br>
• <b>מתחת 2%</b> ✅ = יעד הפד — שוק בריא<br>
• <b>2%–4%</b> 🟡 = סביר<br>
• <b>מעל 5%</b> 🔴 = אינפלציה גבוהה → הפד מעלה ריבית → מניות יורדות<br><br>
💡 <i>אינפלציה = "הכסף שלך שווה פחות". זהב ומניות ריאליות הן גידור טוב.</i>
        """,
    },
    "FedRate": {
        "title": "ריבית הפד (Fed Funds Rate)",
        "body": """
🏦 <b>Federal Funds Rate</b> — הריבית שהבנק המרכזי האמריקאי קובע.<br><br>
• <b>ריבית נמוכה</b> 🟢 → הלוואות זולות → עסקים גדלים → מניות עולות<br>
• <b>ריבית גבוהה</b> 🔴 → הלוואות יקרות → עסקים מתכווצים → מניות יורדות<br><br>
💡 <i>הפד מעלה ריבית כדי להילחם באינפלציה. כשהאינפלציה יורדת → הפד מוריד ריבית → מניות עולות.</i>
        """,
    },
    "YieldCurve": {
        "title": "עקום תשואה (Yield Curve)",
        "body": """
📉 <b>Yield Curve (T10Y2Y)</b> — ההפרש בין אגח 10 שנה לאגח 2 שנה.<br><br>
• <b>חיובי (רגיל)</b> ✅ = כלכלה בריאה<br>
• <b>שלילי (היפוך)</b> 🔴 = <b>אזהרת מיתון!</b> היסטורית — מיתון מגיע תוך 12–18 חודשים<br><br>
💡 <i>היפוך עקום התשואה ניבא כל מיתון מ-1970 עד היום. מדד אמין מאוד!</i>
        """,
    },
    "Correlation": {
        "title": "קורלציה בין נכסים",
        "body": """
🔗 <b>Correlation</b> — עד כמה שני נכסים זזים יחד.<br><br>
• <b>+1.0</b> 🔵 = זהה לחלוטין — עולים ויורדים יחד<br>
• <b>+0.5 עד +0.8</b> 🟢 = קשורים חלקית<br>
• <b>0</b> ⬜ = אין קשר — פיזור מושלם!<br>
• <b>-0.5 עד -0.8</b> 🟡 = גידור חלקי<br>
• <b>-1.0</b> 🔴 = הפוכים לחלוטין — גידור מושלם<br><br>
💡 <i>תיק מפוזר = נכסים עם קורלציה נמוכה. זהב ומניות = קורלציה שלילית!</i>
        """,
    },
    "EfficientFrontier": {
        "title": "Efficient Frontier — גבול היעילות",
        "body": """
📐 <b>Efficient Frontier (Markowitz)</b> — הגרף שמראה את שילוב התיק הטוב ביותר.<br><br>
כל נקודה = תיק אפשרי עם שילוב שונה של נכסים.<br><br>
• ⭐ <b>נקודת הכוכב</b> = תיק Sharpe מקסימלי (הכי הרבה תשואה לכל יחידת סיכון)<br>
• 💎 <b>נקודת היהלום</b> = תיק סיכון מינימלי (הכי יציב)<br><br>
💡 <i>כמשקיע מתחיל: בחר קרוב לנקודת ה-⭐ — תשואה טובה עם סיכון מנוהל.</i>
        """,
    },
    "IsolationForest": {
        "title": "Isolation Forest — זיהוי חריגות",
        "body": """
🔬 <b>Isolation Forest</b> — אלגוריתם AI שמוצא מניות "חריגות".<br><br>
איך עובד? הוא מסתכל על RSI, שולי רווח, ROE, דיבידנד, Insider וכו' ומחפש נכסים שלא מתנהגים כמו האחרים.<br><br>
• 🔴 <b>חריג מאוד</b> = ציון מתחת -0.15 — שונה מאוד מהממוצע<br>
• 🟡 <b>חריג</b> = ציון שלילי<br>
• ⚪ <b>רגיל</b> = ציון חיובי<br><br>
💡 <i>חריגות = לא בהכרח רע! לפעמים חריגות = הזדמנות שמר השוק פספס.</i>
        """,
    },
    "ML": {
        "title": "ML — למידת מכונה (Machine Learning)",
        "body": """
🤖 <b>Machine Learning</b> — האפליקציה מאמנת מודל AI על נתוני בורסה היסטוריים ומנבאת עתיד.<br><br>
<b>שלב 1 — אימון:</b> האלגוריתם לומד מ-2 שנות נתונים של מאות מניות<br>
<b>שלב 2 — ניבוי:</b> לכל מניה: "האם תעלה יותר מ-7% ב-15 יום הקרובים?"<br><br>
• <b>Random Forest</b> — אוסף של "עצי החלטה" שמצביעים בדמוקרטיה<br>
• <b>Gradient Boosting</b> — אלגוריתם שלומד מטעויות שלו<br><br>
💡 <i>דיוק 65-75% נחשב טוב מאוד בשוק ההון!</i>
        """,
    },
    "CV": {
        "title": "Cross Validation — אימות צולב",
        "body": """
🔄 <b>5-Fold Cross Validation</b> — שיטה לבדיקת דיוק המודל בצורה אמינה.<br><br>
<b>איך עובד?</b><br>
• מחלק את הנתונים ל-5 חלקים<br>
• 4 חלקים לאימון, 1 לבדיקה<br>
• חוזר 5 פעמים עם חלקים שונים<br>
• ממוצע התוצאות = הדיוק האמיתי<br><br>
💡 <i>CV% גבוה = המודל לא "שינן" — הוא באמת יודע לנבא!</i>
        """,
    },
}

# ─── פונקציה ראשית: יצירת Tooltip ─────────────────────────────────────────────
def tooltip(text: str, key: str, icon: str = "ℹ️") -> str:
    """
    יוצר טקסט עם אייקון מידע שבריחוף מציג הסבר עברי.
    
    שימוש:
        st.markdown(tooltip("RSI", "RSI"), unsafe_allow_html=True)
    """
    tip = TOOLTIPS.get(key, {})
    if not tip:
        return text
    title = tip.get("title", key)
    body  = tip.get("body", "").strip().replace("\n", " ")
    body  = body.replace('"', '&quot;').replace("'", "&#39;")
    title_safe = title.replace('"', '&quot;')

    return f'''<span class="tt-wrap">
  {text} <span class="tt-icon">{icon}</span>
  <span class="tt-box">
    <span class="tt-title">{title_safe}</span>
    <span class="tt-body">{body}</span>
  </span>
</span>'''


def inject_tooltip_css():
    """מזריק CSS לטולטיפים — קרא פעם אחת בתחילת הדף."""
    st.markdown("""
<style>
/* ── Tooltip container ── */
.tt-wrap {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 3px;
    cursor: help;
}

/* ── Icon ── */
.tt-icon {
    font-size: 11px;
    color: #90caf9;
    opacity: 0.8;
    transition: opacity 0.15s;
}
.tt-wrap:hover .tt-icon { opacity: 1; }

/* ── Tooltip box ── */
.tt-box {
    visibility: hidden;
    opacity: 0;
    position: absolute;
    bottom: calc(100% + 8px);
    right: 0;
    width: 320px;
    background: #1a237e;
    color: #e8eaf6;
    border-radius: 12px;
    padding: 14px 16px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.35);
    z-index: 9999;
    transition: opacity 0.2s ease, visibility 0.2s ease;
    pointer-events: none;
    text-align: right;
    direction: rtl;
    border: 1px solid rgba(255,255,255,0.15);
}

/* Arrow */
.tt-box::after {
    content: "";
    position: absolute;
    top: 100%;
    right: 14px;
    border: 7px solid transparent;
    border-top-color: #1a237e;
}

/* Show on hover */
.tt-wrap:hover .tt-box {
    visibility: visible;
    opacity: 1;
}

/* Title */
.tt-title {
    display: block;
    font-size: 14px;
    font-weight: 800;
    color: #90caf9;
    margin-bottom: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(255,255,255,0.15);
}

/* Body */
.tt-body {
    display: block;
    font-size: 13px;
    line-height: 1.6;
    color: #e8eaf6;
}
.tt-body b { color: #fff; }
.tt-body i { color: #b0bec5; font-style: normal; }
</style>
""", unsafe_allow_html=True)


# ─── פונקציה: כותרת טבלה עם tooltips ─────────────────────────────────────────
def column_header(col_name: str, key: str, icon: str = "ℹ️") -> str:
    """גנרה כותרת עמודה עם Tooltip. לשימוש ב-st.markdown."""
    return tooltip(col_name, key, icon)


# ─── פונקציה: רשימת הסברים מרוכזת לדף ───────────────────────────────────────
def render_glossary():
    """מציג מילון מונחים מלא — לשימוש בטאב עזרה."""
    st.markdown("## 📖 מילון מונחים פיננסיים")
    cats = {
        "📊 ניתוח טכני":   ["RSI","MA50","MA200","Change","GoldenCross","DeathCross"],
        "💰 יסודות חברה":  ["Score","RevGrowth","EarnGrowth","Margin","ROE","InsiderHeld","TargetUpside"],
        "💵 דיבידנדים":    ["DivYield","PayoutRatio"],
        "📐 תיק ואופטימיזציה": ["Sharpe","Beta","MaxDD","Correlation","EfficientFrontier","FairValue","P/L"],
        "🌍 מאקרו":        ["VIX","FearGreed","Inflation","FedRate","YieldCurve"],
        "🤖 AI/ML":        ["ML","CV","IsolationForest","StopLoss","TakeProfit"],
    }
    for cat, keys in cats.items():
        with st.expander(cat):
            for k in keys:
                tip = TOOLTIPS.get(k, {})
                if tip:
                    st.markdown(
                        f'<div style="background:#f8f9ff;border-right:4px solid #1565c0;'
                        f'border-radius:8px;padding:10px 14px;margin:6px 0;">'
                        f'<b style="color:#1565c0">{tip["title"]}</b><br>'
                        f'<span style="font-size:13px;color:#37474f">{tip["body"].replace("<br>","<br>")}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
