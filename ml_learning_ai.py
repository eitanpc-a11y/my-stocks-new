# ml_learning_ai.py — ML מתקדם: XGBoost, LightGBM, Backtest, הסבר חיזויים
# מכסה: מניות ארה"ב, תא"ב, קריפטו, אנרגיה + מודל יומי + שיתוף עם כל הסוכנים
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from storage import save, load
from shared_signals import write_signal, get_top_buys, read_signals

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, IsolationForest
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import cross_val_score, TimeSeriesSplit
    from sklearn.metrics import classification_report, confusion_matrix
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False

try:
    import xgboost as xgb
    XGB_OK = True
except Exception:
    XGB_OK = False

try:
    import lightgbm as lgb
    LGB_OK = True
except Exception:
    LGB_OK = False

try:
    import yfinance as yf
    import pickle, io, base64
    YF_OK = True
except ImportError:
    YF_OK = False

try:
    import plotly.graph_objects as go
    import plotly.express as px
    PLT_OK = True
except ImportError:
    PLT_OK = False


# ══════════════════════════════════════════════════════════════════════════════
# פיצ'רים טכניים
# ══════════════════════════════════════════════════════════════════════════════

FEAT_COLS = [
    "rsi", "macd", "macd_signal", "bb_width", "bb_pct",
    "ret_5d", "ret_20d", "ret_60d",
    "vol_ratio", "vol_trend",
    "above_ma20", "above_ma50", "above_ma200",
    "ma20_slope", "ma50_slope",
    "volatility", "momentum", "candle_body", "gap",
    "high_low_pct", "close_position"
]

FEAT_HE = {
    "rsi": "RSI", "macd": "MACD", "macd_signal": "MACD Signal",
    "bb_width": "רוחב Bollinger", "bb_pct": "מיקום בBollinger",
    "ret_5d": "תשואה 5י׳", "ret_20d": "תשואה 20י׳", "ret_60d": "תשואה 60י׳",
    "vol_ratio": "יחס נפח", "vol_trend": "טרנד נפח",
    "above_ma20": "מעל MA20", "above_ma50": "מעל MA50", "above_ma200": "מעל MA200",
    "ma20_slope": "שיפוע MA20", "ma50_slope": "שיפוע MA50",
    "volatility": "תנודתיות", "momentum": "מומנטום",
    "candle_body": "גוף נר", "gap": "גאפ",
    "high_low_pct": "טווח יומי", "close_position": "מיקום סגירה"
}


def _rsi(s, p=14):
    d = s.diff()
    g = d.where(d > 0, 0.0).rolling(p).mean()
    l = (-d.where(d < 0, 0.0)).rolling(p).mean().replace(0, 1e-10)
    return 100 - (100 / (1 + g / l))


def _macd(s):
    ema12 = s.ewm(span=12, adjust=False).mean()
    ema26 = s.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line, signal


def _build_features(hist: pd.DataFrame, target_days=15, target_pct=0.07) -> pd.DataFrame:
    df = pd.DataFrame(index=hist.index)
    c = hist["Close"]
    o = hist["Open"]
    h = hist["High"]
    l = hist["Low"]
    v = hist["Volume"]

    # RSI
    df["rsi"] = _rsi(c)

    # MACD
    macd_line, macd_sig = _macd(c)
    df["macd"] = macd_line
    df["macd_signal"] = macd_sig

    # Bollinger Bands
    ma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std()
    upper = ma20 + 2 * std20
    lower = ma20 - 2 * std20
    df["bb_width"] = (upper - lower) / ma20
    df["bb_pct"] = (c - lower) / (upper - lower + 1e-10)

    # תשואות
    df["ret_5d"] = c.pct_change(5)
    df["ret_20d"] = c.pct_change(20)
    df["ret_60d"] = c.pct_change(60)

    # נפח
    vol_ma = v.rolling(20).mean()
    df["vol_ratio"] = v / vol_ma
    df["vol_trend"] = vol_ma.pct_change(5)

    # ממוצעים נעים
    ma50 = c.rolling(50).mean()
    ma200 = c.rolling(200).mean()
    df["above_ma20"] = (c > ma20).astype(int)
    df["above_ma50"] = (c > ma50).astype(int)
    df["above_ma200"] = (c > ma200).astype(int)

    # שיפוע ממוצעים
    df["ma20_slope"] = ma20.pct_change(5)
    df["ma50_slope"] = ma50.pct_change(10)

    # תנודתיות ומומנטום
    df["volatility"] = c.pct_change().rolling(20).std()
    df["momentum"] = c / c.shift(10) - 1

    # מבנה נר
    df["candle_body"] = abs(c - o) / (h - l + 1e-10)
    df["gap"] = (o - c.shift(1)) / c.shift(1)
    df["high_low_pct"] = (h - l) / c
    df["close_position"] = (c - l) / (h - l + 1e-10)

    # יעד: עלייה > target_pct בתוך target_days ימים
    df["target"] = (c.shift(-target_days) / c - 1 > target_pct).astype(int)
    df["future_return"] = c.shift(-target_days) / c - 1

    return df.dropna()


def _gather_data(symbols, target_days=15, target_pct=0.07, progress_bar=None):
    all_X, all_y, all_dates, all_syms = [], [], [], []
    for i, sym in enumerate(symbols):
        if progress_bar:
            progress_bar.progress((i + 1) / len(symbols), text=f"מוריד {sym}...")
        try:
            hist = yf.Ticker(sym).history(period="3y")
            if len(hist) < 250:
                continue
            df = _build_features(hist, target_days, target_pct)
            if len(df) < 50:
                continue
            all_X.append(df[FEAT_COLS].values)
            all_y.append(df["target"].values)
            all_dates.extend(df.index.tolist())
            all_syms.extend([sym] * len(df))
        except Exception:
            pass
    if progress_bar:
        progress_bar.empty()
    if not all_X:
        return None, None, None, None
    return np.vstack(all_X), np.concatenate(all_y), all_dates, all_syms


def _build_model(algo: str):
    if algo == "XGBoost ⚡" and XGB_OK:
        return xgb.XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            use_label_encoder=False, eval_metric="logloss",
            random_state=42, n_jobs=-1
        )
    elif algo == "LightGBM 🚀" and LGB_OK:
        return lgb.LGBMClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, n_jobs=-1, verbose=-1
        )
    elif algo == "Random Forest 🌲":
        return RandomForestClassifier(
            n_estimators=300, max_depth=10, min_samples_leaf=5,
            random_state=42, n_jobs=-1
        )
    elif algo == "Gradient Boosting 📈":
        return GradientBoostingClassifier(
            n_estimators=200, learning_rate=0.05, max_depth=5,
            subsample=0.8, random_state=42
        )
    else:
        return LogisticRegression(max_iter=1000, random_state=42, C=1.0)


def _get_feat_importance(model, algo: str) -> dict:
    try:
        if hasattr(model, "feature_importances_"):
            return dict(zip(FEAT_COLS, model.feature_importances_))
        elif hasattr(model, "coef_"):
            return dict(zip(FEAT_COLS, abs(model.coef_[0])))
    except Exception:
        pass
    return {}


def _backtest_model(model, scaler, symbols, target_days=15, target_pct=0.07):
    """Walk-forward backtest: אמן על שנה ראשונה, בדוק על שנה שנייה."""
    results = []
    for sym in symbols[:8]:
        try:
            hist = yf.Ticker(sym).history(period="3y")
            if len(hist) < 400:
                continue
            df = _build_features(hist, target_days, target_pct)
            if len(df) < 100:
                continue

            mid = len(df) // 2
            X_train = scaler.transform(np.nan_to_num(df[FEAT_COLS].iloc[:mid].values))
            X_test  = scaler.transform(np.nan_to_num(df[FEAT_COLS].iloc[mid:].values))
            y_test  = df["target"].iloc[mid:].values
            ret_test = df["future_return"].iloc[mid:].values

            preds = model.predict(X_test)
            probas = model.predict_proba(X_test)[:, 1]

            for pred, prob, actual, ret in zip(preds, probas, y_test, ret_test):
                if prob > 0.6:
                    results.append({
                        "Symbol": sym,
                        "Predicted": int(pred),
                        "Confidence": round(prob * 100, 1),
                        "Actual": int(actual),
                        "Return%": round(ret * 100, 2),
                        "Hit": int(pred) == int(actual),
                    })
        except Exception:
            pass
    return pd.DataFrame(results) if results else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
# ממשק ראשי
# ══════════════════════════════════════════════════════════════════════════════

ALGOS = ["XGBoost ⚡", "LightGBM 🚀", "Random Forest 🌲",
         "Gradient Boosting 📈", "Logistic Regression 📐"]


def render_machine_learning(df_all=None):
    st.markdown(
        '<div class="ai-card" style="border-right-color:#9c27b0;">'
        '<b>🧠 למידת מכונה אמיתית — גרסה משודרגת</b><br>'
        'XGBoost · LightGBM · Backtest · הסבר חיזויים · היסטוריה'
        '</div>',
        unsafe_allow_html=True,
    )

    if not SKLEARN_OK:
        st.error("❌ scikit-learn לא מותקן. הוסף ל-requirements.txt")
        return

    # ── אתחול session state ──────────────────────────────────────────────
    defs = {
        "ml_trained": False, "ml_accuracy": 0.0, "ml_runs": 0,
        "ml_model_type": "XGBoost ⚡" if XGB_OK else "Random Forest 🌲",
        "ml_cv_scores": [], "ml_feat_imp": {},
        "ml_train_n": 0, "ml_insights": [],
        "ml_model_b64": None, "ml_scaler_b64": None,
        "ml_pred_history": [],
        "ml_params": {"target_days": 15, "target_pct": 7, "conf_threshold": 60},
    }
    for k, v in defs.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # נרמול ml_params — תיקון פורמט ישן
    p = st.session_state.ml_params
    if "target_days" not in p:
        p["target_days"] = 15
    if "target_pct" not in p:
        p["target_pct"] = 7
    if "conf_threshold" not in p:
        p["conf_threshold"] = 60
    st.session_state.ml_params = p

    # ── לוח ראשי ────────────────────────────────────────────────────────
    if st.session_state.ml_trained:
        st.success(
            f"✅ מודל **{st.session_state.ml_model_type}** | "
            f"דיוק CV: **{st.session_state.ml_accuracy:.1f}%** | "
            f"אומן על **{st.session_state.ml_train_n:,}** דגימות | "
            f"ריצה #{st.session_state.ml_runs}"
        )
    else:
        st.info("🟡 מודל לא אומן עדיין — עבור לטאב **אימון**")

    avail = []
    if XGB_OK: avail.append("✅ XGBoost")
    else:       avail.append("❌ XGBoost")
    if LGB_OK: avail.append("✅ LightGBM")
    else:       avail.append("❌ LightGBM")
    st.caption("  |  ".join(avail))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🎯 דיוק CV", f"{st.session_state.ml_accuracy:.1f}%")
    c2.metric("📦 דגימות", f"{st.session_state.ml_train_n:,}")
    c3.metric("🔮 חיזויים", str(len(st.session_state.ml_pred_history)))
    c4.metric("🔁 ריצות", str(st.session_state.ml_runs))

    st.divider()

    tab_train, tab_pred, tab_day, tab_bt, tab_opt, tab_anom, tab_hist = st.tabs([
        "🚀 אימון", "🔮 חיזוי (ערך)", "⚡ מסחר יומי ML",
        "📊 Backtest", "📐 תיק Markowitz", "🔍 חריגות", "📋 היסטוריה"
    ])

    # ════════════════════════════════════════════════════════════════
    # TAB 1 — אימון
    # ════════════════════════════════════════════════════════════════
    with tab_train:
        col1, col2 = st.columns(2)
        # ── מצב אוטומטי ──────────────────────────────────────────────────
        st.markdown("#### 🤖 מצב אוטומטי — המכונה בוחרת הכל")
        st.info(
            "**אימון אוטומטי** — המכונה בוחרת את האלגוריתם הטוב ביותר, "
            "מגוון מניות אופטימלי ופרמטרים חכמים. אין צורך בשום הגדרה!"
        )

        if st.button("✨ אמן אוטומטית", type="primary", key="ml_auto_btn"):
            # בחירה אוטומטית של אלגוריתם
            if XGB_OK:
                auto_algo = "XGBoost ⚡"
            elif LGB_OK:
                auto_algo = "LightGBM 🚀"
            else:
                auto_algo = "Random Forest 🌲"

            # בחירה אוטומטית — כל סוגי הנכסים
            auto_base = {
                "ארה\"ב 🇺🇸":   ["AAPL","NVDA","MSFT","AMZN","META","GOOGL","TSLA","JPM","V","AVGO","AMD"],
                "תא\"ב 📈":     ["TEVA.TA","ICL.TA","NICE.TA","ENLT.TA","POLI.TA","LUMI.TA"],
                "קריפטו ₿":    ["BTC-USD","ETH-USD","SOL-USD","BNB-USD"],
                "אנרגיה ⛽":   ["XLE","USO","GLD","SLV","UNG"],
            }
            auto_syms = []
            for cat, syms in auto_base.items():
                auto_syms += syms[:3]   # 3 מכל קטגוריה
            if df_all is not None and not df_all.empty and "Symbol" in df_all.columns:
                from_scan = df_all["Symbol"].tolist()
                extra = [s for s in from_scan if s not in auto_syms][:4]
                auto_syms = auto_syms + extra

            # פרמטרים אוטומטיים — בדיקת שני יעדים ובחירת הטוב
            best_auto = {"acc": 0, "days": 15, "pct": 7}
            for t_d, t_p in [(10, 5), (15, 7), (20, 10)]:
                try:
                    pb_auto = st.progress(0, f"בדיקה: {t_p}% ב-{t_d} ימים...")
                    X_a, y_a, _, _ = _gather_data(auto_syms[:5], t_d, t_p / 100, pb_auto)
                    if X_a is not None and len(X_a) > 100:
                        sc_a = StandardScaler()
                        Xs_a = sc_a.fit_transform(X_a)
                        m_a  = _build_model(auto_algo)
                        cv_a = cross_val_score(m_a, Xs_a, y_a,
                                               cv=TimeSeriesSplit(3), scoring="accuracy")
                        if cv_a.mean() > best_auto["acc"]:
                            best_auto = {"acc": cv_a.mean(), "days": t_d, "pct": t_p}
                except Exception:
                    pass

            auto_days = best_auto["days"]
            auto_pct  = best_auto["pct"]
            algo      = auto_algo
            train_syms = auto_syms
            t_days    = auto_days
            t_pct     = auto_pct

            st.success(
                f"🤖 נבחר אוטומטית: **{auto_algo}** | "
                f"מניות: {', '.join(auto_syms[:5])}... | "
                f"יעד: >{auto_pct}% ב-{auto_days} ימים"
            )

            pb = st.progress(0, "מוריד נתונים מלאים...")
            X, y, _, _ = _gather_data(train_syms, t_days, t_pct / 100, pb)
            if X is None:
                st.error("לא ניתן להוריד נתונים.")
            else:
                with st.spinner(f"מאמן {algo} על {len(X):,} דגימות..."):
                    scaler   = StandardScaler()
                    X_scaled = scaler.fit_transform(X)
                    model    = _build_model(algo)
                    tscv     = TimeSeriesSplit(n_splits=5)
                    cv       = cross_val_score(model, X_scaled, y, cv=tscv, scoring="accuracy")
                    model.fit(X_scaled, y)

                    fi   = _get_feat_importance(model, algo)
                    acc  = round(cv.mean() * 100, 1)
                    top3 = sorted(fi.items(), key=lambda x: x[1], reverse=True)[:3]
                    mb   = io.BytesIO(); pickle.dump(model, mb)
                    sb   = io.BytesIO(); pickle.dump(scaler, sb)

                    st.session_state.ml_trained    = True
                    st.session_state.ml_accuracy   = acc
                    st.session_state.ml_runs      += 1
                    st.session_state.ml_model_type = algo
                    st.session_state.ml_cv_scores  = cv.tolist()
                    st.session_state.ml_model_b64  = base64.b64encode(mb.getvalue()).decode()
                    st.session_state.ml_scaler_b64 = base64.b64encode(sb.getvalue()).decode()
                    st.session_state.ml_feat_imp   = fi
                    st.session_state.ml_train_n    = len(X)
                    st.session_state.ml_params     = {
                        "target_days": t_days, "target_pct": t_pct, "conf_threshold": 60
                    }
                    pos_rate = round(y.mean() * 100, 1)
                    st.session_state.ml_insights   = [
                        f"🤖 **אוטומטי** — אלגוריתם: {algo} | מניות: {len(train_syms)}",
                        f"🏆 פיצ'ר #1: **{FEAT_HE.get(top3[0][0], top3[0][0])}** ({top3[0][1]*100:.1f}%)" if top3 else "",
                        f"🥈 פיצ'ר #2: **{FEAT_HE.get(top3[1][0], top3[1][0])}** ({top3[1][1]*100:.1f}%)" if len(top3) > 1 else "",
                        f"📊 {pos_rate}% מהמקרים היסטורית עלו >{t_pct}% ב-{t_days} ימים",
                        f"📈 דיוק CV: {acc:.1f}% ± {cv.std()*100:.1f}%",
                        f"✅ {len(X):,} דגימות מ-{len(train_syms)} מניות (3 שנים)",
                    ]
                    save("ml_session", {
                        "accuracy": acc, "model_type": algo,
                        "train_n": len(X), "runs": st.session_state.ml_runs,
                        "feat_imp": fi, "trained_at": datetime.now().isoformat(),
                        "auto_mode": True,
                    })
                st.success(f"✅ אימון אוטומטי הסתיים! דיוק: **{acc:.1f}%**")
                st.balloons()
                st.rerun()

        st.divider()
        st.markdown("#### ⚙️ מצב ידני — הגדר בעצמך")

        with col1:
            algo = st.selectbox("🤖 אלגוריתם", ALGOS, key="ml_algo",
                                help="XGBoost ו-LightGBM בד\"כ מדויקים יותר")
            if algo == "XGBoost ⚡" and not XGB_OK:
                st.warning("XGBoost לא מותקן — נסה Random Forest")
            if algo == "LightGBM 🚀" and not LGB_OK:
                st.warning("LightGBM לא מותקן — נסה XGBoost")

        with col2:
            t_days = st.slider("📅 ימי יעד (כמה ימים קדימה?)", 5, 60, 15, key="ml_tdays")
            t_pct  = st.slider("🎯 % עלייה יעד", 3, 20, 7, key="ml_tpct")

        if df_all is not None and not df_all.empty and "Symbol" in df_all.columns:
            sym_opts = df_all["Symbol"].tolist()
        else:
            sym_opts = ["AAPL", "NVDA", "MSFT", "TSLA", "META",
                        "AMZN", "GOOGL", "PLTR", "AMD", "NFLX",
                        "V", "JPM", "COST", "AVGO", "BRK-B"]

        train_syms = st.multiselect(
            "📌 מניות לאימון (מומלץ 5+)",
            sym_opts + ["V", "JPM", "COST", "AVGO", "BRK-B", "NFLX", "AMD"],
            default=sym_opts[:6], key="ml_syms",
            help="יותר מניות = מודל חזק יותר, אבל אימון ארוך יותר"
        )

        st.caption(
            f"ℹ️ יעד: עלייה >{t_pct}% בתוך {t_days} ימים | "
            f"כל מניה ≈ 500 דגימות מ-3 שנות מסחר | "
            f"Cross-Validation עם TimeSeriesSplit"
        )

        if st.button("🚀 אמן מודל ידנית", type="secondary", key="ml_train_btn"):
            if len(train_syms) < 2:
                st.warning("בחר לפחות 2 מניות.")
            elif (algo == "XGBoost ⚡" and not XGB_OK) or (algo == "LightGBM 🚀" and not LGB_OK):
                st.error(f"{algo} לא מותקן. בחר אלגוריתם אחר.")
            else:
                pb = st.progress(0, "מכין נתונים...")
                X, y, _, _ = _gather_data(train_syms, t_days, t_pct / 100, pb)
                if X is None:
                    st.error("לא ניתן להוריד נתונים.")
                else:
                    with st.spinner(f"מאמן {algo} על {len(X):,} דגימות..."):
                        scaler   = StandardScaler()
                        X_scaled = scaler.fit_transform(X)

                        model = _build_model(algo)
                        tscv  = TimeSeriesSplit(n_splits=5)
                        cv    = cross_val_score(model, X_scaled, y, cv=tscv, scoring="accuracy")
                        model.fit(X_scaled, y)

                        fi   = _get_feat_importance(model, algo)
                        acc  = round(cv.mean() * 100, 1)
                        top3 = sorted(fi.items(), key=lambda x: x[1], reverse=True)[:3]

                        mb = io.BytesIO(); pickle.dump(model, mb)
                        sb = io.BytesIO(); pickle.dump(scaler, sb)

                        st.session_state.ml_trained    = True
                        st.session_state.ml_accuracy   = acc
                        st.session_state.ml_runs      += 1
                        st.session_state.ml_model_type = algo
                        st.session_state.ml_cv_scores  = cv.tolist()
                        st.session_state.ml_model_b64  = base64.b64encode(mb.getvalue()).decode()
                        st.session_state.ml_scaler_b64 = base64.b64encode(sb.getvalue()).decode()
                        st.session_state.ml_feat_imp   = fi
                        st.session_state.ml_train_n    = len(X)
                        st.session_state.ml_params     = {
                            "target_days": t_days, "target_pct": t_pct, "conf_threshold": 60
                        }
                        pos_rate = round(y.mean() * 100, 1)
                        st.session_state.ml_insights   = [
                            f"🏆 פיצ'ר #1: **{FEAT_HE.get(top3[0][0], top3[0][0])}** ({top3[0][1]*100:.1f}%)" if top3 else "",
                            f"🥈 פיצ'ר #2: **{FEAT_HE.get(top3[1][0], top3[1][0])}** ({top3[1][1]*100:.1f}%)" if len(top3) > 1 else "",
                            f"🥉 פיצ'ר #3: **{FEAT_HE.get(top3[2][0], top3[2][0])}** ({top3[2][1]*100:.1f}%)" if len(top3) > 2 else "",
                            f"📊 {pos_rate}% מהמקרים היסטורית עלו >{t_pct}% ב-{t_days} ימים",
                            f"📈 דיוק CV ממוצע: {acc:.1f}% ± {cv.std()*100:.1f}%",
                            f"✅ אומן על {len(X):,} דגימות מ-{len(train_syms)} מניות (3 שנים)",
                        ]
                        save("ml_session", {
                            "accuracy": acc, "model_type": algo,
                            "train_n": len(X), "runs": st.session_state.ml_runs,
                            "feat_imp": fi, "trained_at": datetime.now().isoformat(),
                        })

                st.success(f"✅ אימון הסתיים! דיוק TimeSeriesCV: **{acc:.1f}%**")
                st.balloons()
                st.rerun()

        # תובנות
        if st.session_state.ml_insights:
            st.subheader("💡 תובנות מהמודל")
            for ins in st.session_state.ml_insights:
                if ins:
                    st.markdown(f"- {ins}")

        # Feature Importance
        if st.session_state.ml_feat_imp:
            st.divider()
            st.subheader("📊 חשיבות פיצ'רים")
            fi_sorted = sorted(st.session_state.ml_feat_imp.items(),
                               key=lambda x: x[1], reverse=True)
            fi_df = pd.DataFrame([
                {"פיצ'ר": FEAT_HE.get(k, k), "חשיבות %": round(v * 100, 2)}
                for k, v in fi_sorted
            ])
            if PLT_OK:
                fig = px.bar(fi_df.head(12), x="חשיבות %", y="פיצ'ר",
                             orientation="h", color="חשיבות %",
                             color_continuous_scale="Purples",
                             title="חשיבות פיצ'רים — מה המודל מסתכל עליו?")
                fig.update_layout(height=400, showlegend=False,
                                  yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.dataframe(fi_df, hide_index=True)

        # CV
        if st.session_state.ml_cv_scores:
            st.divider()
            cv = st.session_state.ml_cv_scores
            st.subheader("📈 Cross-Validation (TimeSeriesSplit × 5)")
            cv_df = pd.DataFrame({
                "Fold": [f"Fold {i+1}" for i in range(len(cv))],
                "דיוק %": [round(v * 100, 1) for v in cv],
            })
            st.dataframe(cv_df, hide_index=True)
            c1, c2 = st.columns(2)
            c1.metric("ממוצע", f"{np.mean(cv)*100:.1f}%")
            c2.metric("סטיית תקן", f"±{np.std(cv)*100:.1f}%")
            if np.std(cv) * 100 > 8:
                st.warning("⚠️ סטייה גבוהה — הוסף יותר מניות לאימון")

    # ════════════════════════════════════════════════════════════════
    # TAB 2 — חיזוי עם הסבר
    # ════════════════════════════════════════════════════════════════
    with tab_pred:
        if not st.session_state.ml_trained:
            st.info("🟡 אמן מודל קודם.")
        else:
            p = st.session_state.ml_params
            st.markdown(
                f"### 🔮 חיזוי: עלייה >{p['target_pct']}% בתוך {p['target_days']} ימים"
            )

            if df_all is not None and not df_all.empty and "Symbol" in df_all.columns:
                pred_syms = st.multiselect("בחר מניות:", df_all["Symbol"].tolist(),
                                           default=df_all["Symbol"].head(6).tolist(),
                                           key="ml_ps")
            else:
                pred_syms = st.multiselect("בחר מניות:",
                    ["AAPL", "NVDA", "MSFT", "TSLA", "META", "AMZN", "GOOGL", "PLTR"],
                    default=["AAPL", "NVDA", "MSFT", "META"], key="ml_ps")

            conf_thresh = st.slider("🎯 סף ביטחון מינימלי לקנייה", 50, 90, 60, key="ml_conf")

            if st.button("🔮 חזה עכשיו", type="primary", key="ml_pred_btn"):
                if not pred_syms:
                    st.warning("בחר מניה.")
                else:
                    model  = pickle.loads(base64.b64decode(st.session_state.ml_model_b64))
                    scaler = pickle.loads(base64.b64decode(st.session_state.ml_scaler_b64))
                    rows, explanation_rows = [], []

                    with st.spinner("מנתח..."):
                        for sym in pred_syms:
                            try:
                                hist = yf.Ticker(sym).history(period="1y")
                                if len(hist) < 220:
                                    continue
                                df_f = _build_features(hist)
                                if df_f.empty:
                                    continue

                                last = df_f[FEAT_COLS].iloc[[-1]]
                                Xp   = np.nan_to_num(last.values)
                                Xs   = scaler.transform(Xp)
                                pred = model.predict(Xs)[0]
                                prob = model.predict_proba(Xs)[0]
                                conf = prob[int(pred)] * 100

                                # הסבר: תרומת כל פיצ'ר
                                fi = st.session_state.ml_feat_imp
                                feat_vals = {k: float(last[k].iloc[0]) for k in FEAT_COLS if k in last.columns}
                                top_feats = sorted(fi.items(), key=lambda x: x[1], reverse=True)[:4]
                                explain = " | ".join([
                                    f"{FEAT_HE.get(f, f)}={feat_vals.get(f, 0):.2f}"
                                    for f, _ in top_feats
                                ])

                                rec = "🟢 קנה" if (pred == 1 and conf >= conf_thresh) else \
                                      "⚠️ המתן" if pred == 1 else "🔴 לא"

                                rows.append({
                                    "📌 מניה":   sym,
                                    "🔮 חיזוי":  "✅ עלייה" if pred == 1 else "❌ לא",
                                    "🎯 ביטחון": f"{conf:.1f}%",
                                    "📊 RSI":    f"{feat_vals.get('rsi', 0):.1f}",
                                    "MA50":      "✅" if feat_vals.get("above_ma50", 0) else "❌",
                                    "MA200":     "✅" if feat_vals.get("above_ma200", 0) else "❌",
                                    "📈 נפח":    "⚡" if feat_vals.get("vol_ratio", 1) > 1.5 else "רגיל",
                                    "🤖 המלצה":  rec,
                                })
                                explanation_rows.append({
                                    "מניה": sym, "המלצה": rec,
                                    "הסבר (פיצ'רים מובילים)": explain,
                                })

                                # שמור היסטוריה
                                st.session_state.ml_pred_history.insert(0, {
                                    "⏰ זמן": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "📌 מניה": sym,
                                    "🔮 חיזוי": "עלייה" if pred == 1 else "לא עלייה",
                                    "🎯 ביטחון": f"{conf:.1f}%",
                                    "🤖 המלצה": rec,
                                    "📝 הסבר": explain,
                                })

                                # ✅ כתוב לאוטובוס המשותף — מזין את כל הסוכנים
                                direction = "BUY" if pred == 1 else "HOLD"
                                write_signal(
                                    source="ml_value",
                                    symbol=sym,
                                    direction=direction,
                                    confidence=conf,
                                    reason=f"{st.session_state.ml_model_type} | {explain}",
                                    timeframe="long",
                                    price=feat_vals.get("close_position", 0),
                                    model_type=st.session_state.ml_model_type,
                                )
                            except Exception:
                                pass

                    if rows:
                        st.dataframe(pd.DataFrame(rows), hide_index=True)
                        st.divider()
                        st.subheader("🧠 הסבר — למה המודל המליץ כך?")
                        st.dataframe(pd.DataFrame(explanation_rows), hide_index=True)

                        buys = [r["📌 מניה"] for r in rows if r["🤖 המלצה"] == "🟢 קנה"]
                        if buys:
                            st.success(f"🟢 ממליץ לקנות (ביטחון ≥{conf_thresh}%): **{', '.join(buys)}**")
                            st.info(f"🔗 הסיגנלים נשלחו לסוכן הערך ולסוכן היומי אוטומטית!")
                        else:
                            st.warning("⚠️ אין המלצת קנייה חזקה כרגע")

                        # שמור היסטוריה
                        st.session_state.ml_pred_history = st.session_state.ml_pred_history[:100]
                        save("ml_pred_history", st.session_state.ml_pred_history)

    # ════════════════════════════════════════════════════════════════
    # TAB 3 — מסחר יומי ML (מודל קצר-טווח)
    # ════════════════════════════════════════════════════════════════
    with tab_day:
        st.markdown(
            '<div class="ai-card" style="border-right-color:#e65100;">'
            '<b>⚡ מודל ML ליומי</b> — לומד תבניות של עלייה ≥2% בתוך 3-5 ימים.<br>'
            'מכסה: מניות ארה"ב, קריפטו, אנרגיה, תא"ב. מזין את הסוכן היומי.'
            '</div>',
            unsafe_allow_html=True,
        )

        # state ייעודי למודל יומי
        day_defs = {
            "ml_day_trained": False, "ml_day_accuracy": 0.0,
            "ml_day_model_b64": None, "ml_day_scaler_b64": None,
            "ml_day_feat_imp": {}, "ml_day_train_n": 0,
        }
        for k, v in day_defs.items():
            if k not in st.session_state:
                st.session_state[k] = v

        if st.session_state.ml_day_trained:
            st.success(
                f"✅ מודל יומי פעיל | "
                f"דיוק: **{st.session_state.ml_day_accuracy:.1f}%** | "
                f"דגימות: **{st.session_state.ml_day_train_n:,}**"
            )
        else:
            st.info("🟡 מודל יומי לא אומן עדיין")

        st.markdown("#### 🤖 אימון אוטומטי — יעד: עלייה ≥2% ב-3-5 ימים")

        # כל סוגי הנכסים למסחר יומי
        DAY_SYMBOLS = {
            "ארה\"ב":  ["AAPL","NVDA","TSLA","AMD","PLTR","NFLX","META","AMZN"],
            "קריפטו":  ["BTC-USD","ETH-USD","SOL-USD","BNB-USD"],
            "אנרגיה":  ["XLE","USO","GLD","SLV"],
            "תא\"ב":   ["TEVA.TA","ICL.TA","NICE.TA","ENLT.TA"],
        }
        day_all_syms = [s for syms in DAY_SYMBOLS.values() for s in syms]

        d1, d2 = st.columns(2)
        with d1:
            day_target_days = st.slider("📅 ימי יעד", 2, 7, 3, key="ml_day_tdays")
        with d2:
            day_target_pct  = st.slider("🎯 % עלייה יעד", 1, 5, 2, key="ml_day_tpct")

        if st.button("✨ אמן מודל יומי אוטומטית", type="primary", key="ml_day_train"):
            # בחר אלגוריתם
            day_algo = "XGBoost ⚡" if XGB_OK else ("LightGBM 🚀" if LGB_OK else "Random Forest 🌲")
            pb_day   = st.progress(0, "מוריד נתונים לכל הנכסים...")
            X_day, y_day, _, _ = _gather_data(day_all_syms, day_target_days,
                                              day_target_pct / 100, pb_day)
            if X_day is None or len(X_day) < 100:
                st.error("לא ניתן להוריד מספיק נתונים.")
            else:
                with st.spinner(f"מאמן מודל יומי על {len(X_day):,} דגימות..."):
                    sc_day  = StandardScaler()
                    Xd_sc   = sc_day.fit_transform(X_day)
                    m_day   = _build_model(day_algo)
                    cv_day  = cross_val_score(m_day, Xd_sc, y_day,
                                             cv=TimeSeriesSplit(5), scoring="accuracy")
                    m_day.fit(Xd_sc, y_day)
                    fi_day  = _get_feat_importance(m_day, day_algo)
                    acc_day = round(cv_day.mean() * 100, 1)

                    mb_d = io.BytesIO(); pickle.dump(m_day, mb_d)
                    sb_d = io.BytesIO(); pickle.dump(sc_day, sb_d)

                    st.session_state.ml_day_trained    = True
                    st.session_state.ml_day_accuracy   = acc_day
                    st.session_state.ml_day_model_b64  = base64.b64encode(mb_d.getvalue()).decode()
                    st.session_state.ml_day_scaler_b64 = base64.b64encode(sb_d.getvalue()).decode()
                    st.session_state.ml_day_feat_imp   = fi_day
                    st.session_state.ml_day_train_n    = len(X_day)

                    save("ml_day_session", {
                        "accuracy": acc_day, "trained_at": datetime.now().isoformat(),
                        "symbols": day_all_syms, "target_days": day_target_days,
                        "target_pct": day_target_pct,
                    })
                st.success(f"✅ מודל יומי אומן! דיוק: **{acc_day:.1f}%** | {len(X_day):,} דגימות")
                st.rerun()

        st.divider()
        st.markdown("#### ⚡ חיזוי יומי — סיגנלים לסוכן היומי")

        if not st.session_state.ml_day_trained:
            st.warning("⚠️ אמן את המודל היומי קודם")
        else:
            day_conf_thresh = st.slider("סף ביטחון", 50, 90, 55, key="ml_day_conf")

            if st.button("⚡ חזה ושלח לסוכן היומי", type="primary", key="ml_day_pred"):
                m_day  = pickle.loads(base64.b64decode(st.session_state.ml_day_model_b64))
                sc_day = pickle.loads(base64.b64decode(st.session_state.ml_day_scaler_b64))
                fi_day = st.session_state.ml_day_feat_imp
                rows_day = []
                signals_sent = 0

                with st.spinner("מנתח כל הנכסים..."):
                    for sym in day_all_syms:
                        try:
                            hist = yf.Ticker(sym).history(period="6mo")
                            if len(hist) < 100:
                                continue
                            df_f  = _build_features(hist, day_target_days, day_target_pct / 100)
                            if df_f.empty:
                                continue
                            last  = df_f[FEAT_COLS].iloc[[-1]]
                            Xp    = np.nan_to_num(last.values)
                            Xs    = sc_day.transform(Xp)
                            pred  = m_day.predict(Xs)[0]
                            prob  = m_day.predict_proba(Xs)[0]
                            conf  = prob[int(pred)] * 100

                            feat_vals = {k: float(last[k].iloc[0]) for k in FEAT_COLS if k in last.columns}
                            top_feats = sorted(fi_day.items(), key=lambda x: x[1], reverse=True)[:3]
                            explain   = " | ".join([
                                f"{FEAT_HE.get(f,f)}={feat_vals.get(f,0):.2f}"
                                for f, _ in top_feats
                            ])

                            asset_type = (
                                "קריפטו ₿" if "-USD" in sym else
                                "תא\"ב 📈" if sym.endswith(".TA") else
                                "אנרגיה ⛽" if sym in ("XLE","USO","GLD","SLV","UNG") else
                                "ארה\"ב 🇺🇸"
                            )

                            if pred == 1 and conf >= day_conf_thresh:
                                rec = "🟢 קנה יומי"
                                # כתוב לאוטובוס המשותף
                                write_signal(
                                    source="ml_day",
                                    symbol=sym,
                                    direction="BUY",
                                    confidence=conf,
                                    reason=f"ML יומי | {explain}",
                                    timeframe="short",
                                    model_type="Day ML",
                                )
                                signals_sent += 1
                            else:
                                rec = "⚪ לא"

                            if pred == 1:
                                rows_day.append({
                                    "📌 נכס":    sym,
                                    "🏷️ סוג":   asset_type,
                                    "🔮 חיזוי":  "✅ עלייה" if pred == 1 else "❌",
                                    "🎯 ביטחון": f"{conf:.1f}%",
                                    "📊 RSI":    f"{feat_vals.get('rsi',0):.1f}",
                                    "📈 נפח":    "⚡" if feat_vals.get("vol_ratio",1)>1.5 else "רגיל",
                                    "🤖 המלצה":  rec,
                                })
                        except Exception:
                            pass

                if rows_day:
                    st.dataframe(pd.DataFrame(rows_day), hide_index=True)
                    if signals_sent > 0:
                        st.success(
                            f"✅ {signals_sent} סיגנלי קנייה נשלחו לסוכן היומי! "
                            f"(ביטחון ≥{day_conf_thresh}%)"
                        )
                        st.info("💡 עבור לסוכן היומי ולחץ 'קנה יומי' — הוא יראה את ההמלצות")
                else:
                    st.info("אין סיגנלים יומיים חזקים כרגע")

        # פיצ'ר אימפורטנס של מודל יומי
        if st.session_state.get("ml_day_feat_imp"):
            st.divider()
            st.subheader("📊 מה המודל היומי מסתכל עליו?")
            fi_sorted = sorted(st.session_state.ml_day_feat_imp.items(),
                               key=lambda x: x[1], reverse=True)[:10]
            fi_df = pd.DataFrame([
                {"פיצ'ר": FEAT_HE.get(k, k), "חשיבות %": round(v * 100, 2)}
                for k, v in fi_sorted
            ])
            st.dataframe(fi_df, hide_index=True)

    # ════════════════════════════════════════════════════════════════
    # TAB 4 — Backtest
    # ════════════════════════════════════════════════════════════════
    with tab_bt:
        st.markdown("### 📊 Backtest — בדיקת המודל על נתוני עבר")
        st.info(
            "בודק את המודל על נתונים שלא ראה: אמון על מחצית ראשונה, "
            "בדיקה על מחצית שנייה. מחשב את הרווח/הפסד של החיזויים."
        )
        if not st.session_state.ml_trained:
            st.warning("🟡 אמן מודל קודם.")
        else:
            bt_syms = st.multiselect(
                "מניות לבדיקה:",
                ["AAPL", "NVDA", "MSFT", "TSLA", "META", "AMZN", "GOOGL", "PLTR", "AMD", "NFLX"],
                default=["AAPL", "NVDA", "MSFT", "META", "AMZN"],
                key="ml_bt_syms"
            )

            if st.button("📊 הרץ Backtest", type="primary", key="ml_bt_btn"):
                with st.spinner("מריץ backtest..."):
                    model  = pickle.loads(base64.b64decode(st.session_state.ml_model_b64))
                    scaler = pickle.loads(base64.b64decode(st.session_state.ml_scaler_b64))
                    bt_df  = _backtest_model(model, scaler, bt_syms)

                if bt_df.empty:
                    st.error("לא מספיק נתונים לbacktest.")
                else:
                    # מסנן רק המלצות עם ביטחון גבוה
                    high_conf = bt_df[bt_df["Confidence"] >= 60]
                    if high_conf.empty:
                        high_conf = bt_df

                    acc_bt   = round(high_conf["Hit"].mean() * 100, 1)
                    avg_ret  = round(high_conf[high_conf["Predicted"] == 1]["Return%"].mean(), 2)
                    n_trades = len(high_conf[high_conf["Predicted"] == 1])
                    win_rate = round(
                        high_conf[high_conf["Predicted"] == 1]["Hit"].mean() * 100, 1
                    ) if n_trades > 0 else 0

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("🎯 דיוק Backtest", f"{acc_bt:.1f}%")
                    c2.metric("💰 תשואה ממוצעת", f"{avg_ret:+.1f}%",
                              delta="כשהמודל חיזה עלייה")
                    c3.metric("📊 עסקאות", str(n_trades))
                    c4.metric("✅ Win Rate", f"{win_rate:.1f}%")

                    st.divider()

                    # גרף התפלגות תשואות
                    if PLT_OK and not high_conf.empty:
                        buys_only = high_conf[high_conf["Predicted"] == 1]
                        if not buys_only.empty:
                            fig = px.histogram(
                                buys_only, x="Return%", color="Hit",
                                color_discrete_map={True: "#4caf50", False: "#f44336"},
                                labels={"Hit": "חיזוי נכון?", "Return%": "תשואה בפועל %"},
                                title="התפלגות תשואות בפועל כשהמודל המליץ קנייה",
                                barmode="overlay"
                            )
                            fig.add_vline(x=0, line_dash="dash", line_color="white")
                            st.plotly_chart(fig, use_container_width=True)

                    with st.expander("📋 כל העסקאות"):
                        st.dataframe(high_conf.round(2), hide_index=True)

                    if avg_ret > 0:
                        st.success(f"✅ המודל יצר תשואה חיובית ממוצעת של **{avg_ret:+.1f}%** בbacktest!")
                    else:
                        st.warning(f"⚠️ תשואה ממוצעת שלילית ({avg_ret:+.1f}%) — נסה לאמן עם יותר מניות")

    # ════════════════════════════════════════════════════════════════
    # TAB 4 — Portfolio Optimizer (Markowitz)
    # ════════════════════════════════════════════════════════════════
    with tab_opt:
        st.markdown("### 📐 אופטימיזציית תיק — Markowitz MPT")
        st.info("מחשב את הרכב התיק עם Sharpe Ratio מקסימלי (10,000 סימולציות)")

        if df_all is not None and not df_all.empty and "Symbol" in df_all.columns:
            opt_syms = st.multiselect("בחר מניות:", df_all["Symbol"].tolist(),
                                      default=df_all["Symbol"].head(5).tolist(), key="ml_os")
        else:
            opt_syms = st.multiselect("בחר מניות:",
                ["AAPL", "NVDA", "MSFT", "TSLA", "META", "AMZN", "GOOGL", "BRK-B"],
                default=["AAPL", "NVDA", "MSFT", "META", "AMZN"], key="ml_os")

        rf_rate = st.slider("📉 ריבית חסרת סיכון (%)", 0.0, 8.0, 4.5, 0.5, key="ml_rf")

        if st.button("📐 חשב תיק אופטימלי", type="primary", key="ml_opt_btn"):
            if len(opt_syms) < 2:
                st.warning("בחר ≥2 מניות.")
            else:
                with st.spinner("מחשב 10,000 תיקים..."):
                    prices = {}
                    for sym in opt_syms:
                        try:
                            h = yf.Ticker(sym).history(period="2y")["Close"]
                            if len(h) > 100:
                                prices[sym] = h
                        except Exception:
                            pass

                    if len(prices) < 2:
                        st.error("לא ניתן להוריד נתונים.")
                    else:
                        pdf = pd.DataFrame(prices).dropna()
                        ret = pdf.pct_change().dropna()
                        mu  = ret.mean() * 252
                        cov = ret.cov() * 252
                        n   = len(mu)
                        np.random.seed(42)

                        best = {"sharpe": -999, "w": None, "r": 0, "v": 0}
                        sim_r, sim_v, sim_s = [], [], []
                        for _ in range(10000):
                            w = np.random.dirichlet(np.ones(n))
                            r = float(np.dot(w, mu))
                            v = float(np.sqrt(w @ cov.values @ w))
                            s = (r - rf_rate / 100) / v if v > 0 else 0
                            sim_r.append(r * 100)
                            sim_v.append(v * 100)
                            sim_s.append(s)
                            if s > best["sharpe"]:
                                best = {"sharpe": s, "w": w, "r": r, "v": v}

                alloc = {sym: round(w * 100, 1) for sym, w in zip(pdf.columns, best["w"])}
                alloc_df = pd.DataFrame([
                    {"📌 מניה": sym, "💼 הקצאה %": pct,
                     "📊 גרף": "█" * max(1, int(pct / 3))}
                    for sym, pct in sorted(alloc.items(), key=lambda x: x[1], reverse=True)
                ])
                st.dataframe(alloc_df, hide_index=True)
                c1, c2, c3 = st.columns(3)
                c1.metric("📈 תשואה שנתית", f"{best['r']*100:.1f}%")
                c2.metric("📊 תנודתיות",    f"{best['v']*100:.1f}%")
                c3.metric("⚖️ Sharpe",       f"{best['sharpe']:.2f}")

                if PLT_OK:
                    fig = px.scatter(
                        x=sim_v, y=sim_r, color=sim_s,
                        color_continuous_scale="RdYlGn",
                        labels={"x": "תנודתיות %", "y": "תשואה %", "color": "Sharpe"},
                        title="Efficient Frontier — 10,000 תיקים"
                    )
                    fig.add_scatter(
                        x=[best["v"] * 100], y=[best["r"] * 100],
                        mode="markers", marker=dict(size=15, color="gold", symbol="star"),
                        name="תיק אופטימלי"
                    )
                    st.plotly_chart(fig, use_container_width=True)

                with st.expander("🔗 מטריצת קורלציה"):
                    corr_clean = ret.corr().round(2)
                    if PLT_OK:
                        fig_c = px.imshow(corr_clean, text_auto=True,
                                          color_continuous_scale="RdYlGn",
                                          zmin=-1, zmax=1,
                                          title="קורלציה בין נכסים")
                        st.plotly_chart(fig_c, use_container_width=True)
                    st.caption("🟢 חיובי = זזים יחד | 🔴 שלילי = גידור | 🟡 אפס = פיזור טוב")

    # ════════════════════════════════════════════════════════════════
    # TAB 5 — Anomaly Detection
    # ════════════════════════════════════════════════════════════════
    with tab_anom:
        st.markdown("### 🔍 זיהוי חריגות — Isolation Forest")
        st.info("מזהה מניות עם פרמטרים יוצאי דופן — לעיתים סיגנל מוקדם להזדמנות")
        if df_all is not None and not df_all.empty:
            if st.button("🔍 סרוק חריגות", type="primary", key="ml_anom_btn"):
                try:
                    feat_cols_anom = ["RSI", "Margin", "ROE", "DivYield", "Score"]
                    available = [c for c in feat_cols_anom if c in df_all.columns]
                    if len(available) < 2:
                        st.warning("אין מספיק עמודות לניתוח.")
                    else:
                        feat = np.nan_to_num(df_all[available].values)
                        iso  = IsolationForest(contamination=0.15, random_state=42)
                        iso.fit(feat)
                        scores = iso.score_samples(feat)
                        df2    = df_all.copy()
                        df2["חריגות"] = scores
                        df2["סטטוס"]  = df2["חריגות"].apply(
                            lambda s: "🔴 חריג מאוד" if s < -0.15
                            else ("🟡 חריג" if s < 0 else "⚪ רגיל")
                        )
                        anom = df2[df2["חריגות"] < 0].sort_values("חריגות")
                        if anom.empty:
                            st.info("לא נמצאו חריגות — שוק נורמלי")
                        else:
                            st.success(f"נמצאו {len(anom)} מניות חריגות:")
                            show = [c for c in
                                    ["Symbol", "Price", "RSI", "Score",
                                     "Margin", "חריגות", "סטטוס"]
                                    if c in anom.columns]
                            st.dataframe(anom[show].round(3), hide_index=True)
                            st.caption("💡 חריגות יכולות להצביע על הזדמנות — בדוק ידנית!")
                except Exception as e:
                    st.error(f"שגיאה: {e}")
        else:
            st.warning("טען נתוני מניות קודם.")

    # ════════════════════════════════════════════════════════════════
    # TAB 6 — היסטוריית חיזויים
    # ════════════════════════════════════════════════════════════════
    with tab_hist:
        st.markdown("### 📋 היסטוריית חיזויים")
        hist_data = st.session_state.ml_pred_history
        if not hist_data:
            saved = load("ml_pred_history", [])
            if saved:
                st.session_state.ml_pred_history = saved
                hist_data = saved

        if hist_data:
            df_hist = pd.DataFrame(hist_data)
            st.info(f"סה\"כ {len(df_hist)} חיזויים נשמרו")
            st.dataframe(df_hist, hide_index=True)

            buys = df_hist[df_hist["🤖 המלצה"] == "🟢 קנה"] if "🤖 המלצה" in df_hist.columns else pd.DataFrame()
            if not buys.empty:
                st.subheader(f"🟢 המלצות קנייה ({len(buys)})")
                st.dataframe(buys, hide_index=True)

            if st.button("🗑️ נקה היסטוריה", key="ml_clear_hist"):
                st.session_state.ml_pred_history = []
                save("ml_pred_history", [])
                st.success("נוקה!")
                st.rerun()
        else:
            st.info("אין היסטוריה עדיין — הרץ חיזוי קודם.")

        st.divider()
        if st.button("🗑️ איפוס מודל מלא", key="ml_reset_btn"):
            for k in list(defs.keys()):
                st.session_state[k] = defs[k]
            save("ml_session", {})
            save("ml_pred_history", [])
            st.success("✅ מודל ונתונים אופסו")
            st.rerun()
