import pandas as pd
import streamlit as st
import yfinance as yf

from auth import (
    sign_up,
    sign_in,
    sign_out,
    is_logged_in,
    get_current_user_id,
    get_current_user_email,
)
from db import load_user_settings, save_user_settings
from main import (
    get_drawdown,
    get_buy_signal,
    normalize_target_weights,
)


st.set_page_config(
    page_title="HeliosAI",
    page_icon="📈",
    layout="wide"
)


def rerun_app():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def hide_streamlit_sidebar_button():
    st.markdown(
        """
        <style>
        [data-testid="collapsedControl"] {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True
    )


def get_ticker_label_map(settings: dict):
    label_map = {}

    for label, ticker in settings["market_tickers"].items():
        label_map[ticker] = label

    for ticker in settings.get("watchlist_tickers", []):
        label_map.setdefault(ticker, ticker)

    for ticker in settings.get("portfolio_tickers", []):
        label_map.setdefault(ticker, ticker)

    return label_map


def display_ticker(settings: dict, ticker: str):
    label_map = get_ticker_label_map(settings)
    return label_map.get(ticker, ticker)


def format_won(value):
    return f"{value:,.0f}원"


def format_percent(value):
    return f"{value:.2f}%"


def format_market_value(ticker: str, value: float):
    if ticker == "USDKRW=X":
        return f"{value:,.2f}원"
    elif ticker == "^VIX":
        return f"{value:.2f}"
    else:
        return f"{value:,.2f}"


def normalize_ticker_list(text: str):
    return [
        ticker.strip().upper()
        for ticker in text.split(",")
        if ticker.strip()
    ]


def render_auth_page():
    st.title("📈 HeliosAI")
    st.caption("데이터 기반 장기투자 관리 도구 · 로그인 후 개인 설정을 저장할 수 있습니다.")

    st.divider()

    login_tab, signup_tab = st.tabs(["로그인", "회원가입"])

    with login_tab:
        st.subheader("로그인")

        email = st.text_input("이메일", key="login_email")
        password = st.text_input("비밀번호", type="password", key="login_password")

        if st.button("로그인", type="primary"):
            if not email or not password:
                st.warning("이메일과 비밀번호를 입력해주세요.")
                return

            try:
                user, session = sign_in(email, password)

                if user and session:
                    st.success("로그인 성공")
                    rerun_app()
                else:
                    st.warning("로그인에 실패했습니다.")

            except Exception as error:
                st.error(f"로그인 실패: {error}")

    with signup_tab:
        st.subheader("회원가입")

        email = st.text_input("이메일", key="signup_email")
        password = st.text_input("비밀번호", type="password", key="signup_password")
        password_check = st.text_input(
            "비밀번호 확인",
            type="password",
            key="signup_password_check"
        )

        if st.button("회원가입"):
            if not email or not password:
                st.warning("이메일과 비밀번호를 입력해주세요.")
                return

            if password != password_check:
                st.warning("비밀번호가 서로 다릅니다.")
                return

            if len(password) < 6:
                st.warning("비밀번호는 최소 6자 이상으로 설정해주세요.")
                return

            try:
                user, session = sign_up(email, password)

                if user and session:
                    st.success("회원가입 및 로그인 성공")
                    rerun_app()
                elif user and not session:
                    st.success("회원가입 성공. 이메일 확인이 필요할 수 있습니다. 메일함을 확인한 뒤 로그인해주세요.")
                else:
                    st.warning("회원가입에 실패했습니다.")

            except Exception as error:
                st.error(f"회원가입 실패: {error}")

    st.divider()
    st.caption("주의: 이 앱은 투자 판단을 돕는 보조 도구이며 수익을 보장하지 않습니다.")


@st.cache_data(ttl=300)
def cached_get_drawdown(ticker: str):
    return get_drawdown(ticker)


@st.cache_data(ttl=300)
def cached_get_market_average_status(ticker: str, average_days: int = 20):
    data = yf.download(
        ticker,
        period="6mo",
        interval="1d",
        progress=False,
        auto_adjust=True
    )

    if data.empty:
        raise ValueError(f"{ticker} 데이터를 가져오지 못했습니다.")

    close = data["Close"]

    if hasattr(close, "columns"):
        close = close.iloc[:, 0]

    close = pd.to_numeric(close, errors="coerce").dropna()

    if close.empty:
        raise ValueError(f"{ticker} 유효한 가격 데이터가 없습니다.")

    current_price = float(close.iloc[-1])
    latest_time = close.index[-1]

    recent_close = close.tail(average_days)

    if recent_close.empty:
        raise ValueError(f"{ticker} 평균 계산용 데이터가 부족합니다.")

    average_price = float(recent_close.mean())

    if average_price == 0:
        raise ValueError(f"{ticker} 평균 가격이 0이라 계산할 수 없습니다.")

    average_diff_percent = (current_price / average_price - 1) * 100

    if len(close) >= 2:
        previous_price = float(close.iloc[-2])

        if previous_price == 0:
            daily_change_percent = 0
        else:
            daily_change_percent = (current_price / previous_price - 1) * 100
    else:
        previous_price = None
        daily_change_percent = 0

    return {
        "ticker": ticker,
        "current_price": current_price,
        "average_price": average_price,
        "average_days": average_days,
        "average_diff_percent": average_diff_percent,
        "previous_price": previous_price,
        "daily_change_percent": daily_change_percent,
        "latest_time": latest_time,
    }


@st.cache_data(ttl=300)
def cached_get_price_history(ticker: str, period: str, interval: str, chart_mode: str):
    download_interval = interval
    download_period = period

    if chart_mode == "연봉":
        download_interval = "1mo"
        download_period = "max"

    data = yf.download(
        ticker,
        period=download_period,
        interval=download_interval,
        progress=False,
        auto_adjust=True
    )

    if data.empty:
        raise ValueError(f"{ticker} 가격 데이터를 가져오지 못했습니다.")

    close = data["Close"]

    if hasattr(close, "columns"):
        close = close.iloc[:, 0]

    close = pd.to_numeric(close, errors="coerce").dropna()

    if close.empty:
        raise ValueError(f"{ticker} 유효한 가격 데이터가 없습니다.")

    chart_df = pd.DataFrame({
        "가격": close
    })

    if chart_mode == "연봉":
        chart_df = chart_df.resample("YE").last().dropna()

    if chart_df.empty:
        raise ValueError(f"{ticker} 차트로 표시할 데이터가 없습니다.")

    return chart_df


def analyze_portfolio_data(settings: dict):
    portfolio = settings["portfolio"]
    portfolio_tickers = settings["portfolio_tickers"]
    target_weights_raw = settings["target_weights"]
    tolerance = settings.get("rebalance_tolerance_percent", 5) / 100

    invest_assets = {
        ticker: float(portfolio.get(ticker, 0))
        for ticker in portfolio_tickers
    }

    total_invested = sum(invest_assets.values())
    cash = float(portfolio.get("CASH", 0))
    total_assets = total_invested + cash

    target_total = sum(
        float(target_weights_raw.get(ticker, 0))
        for ticker in portfolio_tickers
    )

    if total_invested == 0:
        return {
            "configured": False,
            "reason": "투자 비율을 설정해주세요.",
            "total_invested": 0,
            "cash": cash,
            "total_assets": total_assets,
            "cash_weight": 0,
            "rows": [],
            "recommendation": "설정에서 보유금액과 목표 비중을 입력해주세요.",
        }

    if target_total == 0:
        return {
            "configured": False,
            "reason": "투자 비율을 설정해주세요.",
            "total_invested": total_invested,
            "cash": cash,
            "total_assets": total_assets,
            "cash_weight": cash / total_assets * 100 if total_assets > 0 else 0,
            "rows": [],
            "recommendation": "설정에서 목표 비중을 입력해주세요.",
        }

    target_weights = normalize_target_weights({
        ticker: float(target_weights_raw.get(ticker, 0))
        for ticker in portfolio_tickers
    })

    rows = []
    gaps = {}

    for ticker in portfolio_tickers:
        current_value = invest_assets.get(ticker, 0)
        current_weight = current_value / total_invested
        target_weight = target_weights.get(ticker, 0)
        gap = target_weight - current_weight
        gaps[ticker] = gap

        if gap > tolerance:
            status = "부족"
        elif gap < -tolerance:
            status = "초과"
        else:
            status = "정상 범위"

        rows.append({
            "티커": ticker,
            "현재 금액": current_value,
            "현재 비중": current_weight * 100,
            "목표 비중": target_weight * 100,
            "차이": gap * 100,
            "상태": status,
        })

    recommended = max(gaps, key=gaps.get)
    biggest_gap = gaps[recommended]

    if biggest_gap <= tolerance:
        recommendation = (
            f"목표 비중과의 차이가 모두 ±{tolerance * 100:.0f}%p 이내입니다. "
            "기본 매수 계획대로 진행하세요."
        )
    else:
        recommendation = (
            f"{recommended} 비중이 목표보다 {biggest_gap * 100:.2f}%p 낮습니다. "
            f"다음 매수는 {recommended} 우선 추천입니다."
        )

    cash_weight = cash / total_assets * 100 if total_assets > 0 else 0

    return {
        "configured": True,
        "reason": "",
        "total_invested": total_invested,
        "cash": cash,
        "total_assets": total_assets,
        "cash_weight": cash_weight,
        "rows": rows,
        "recommendation": recommendation,
    }


def render_portfolio_pie(settings: dict, portfolio_result: dict):
    portfolio = settings["portfolio"]
    portfolio_tickers = settings["portfolio_tickers"]

    data = []

    for ticker in portfolio_tickers:
        value = float(portfolio.get(ticker, 0))

        if value > 0:
            data.append({
                "자산": ticker,
                "금액": value
            })

    cash = float(portfolio.get("CASH", 0))

    if cash > 0:
        data.append({
            "자산": "현금",
            "금액": cash
        })

    if not data:
        st.info("투자 비율을 설정해주세요.")
        return

    chart_df = pd.DataFrame(data)

    st.vega_lite_chart(
        chart_df,
        {
            "mark": {"type": "arc", "innerRadius": 55},
            "encoding": {
                "theta": {
                    "field": "금액",
                    "type": "quantitative",
                    "stack": True
                },
                "color": {
                    "field": "자산",
                    "type": "nominal"
                },
                "tooltip": [
                    {"field": "자산", "type": "nominal"},
                    {"field": "금액", "type": "quantitative", "format": ","}
                ]
            },
            "height": 320
        },
        use_container_width=True
    )

    if portfolio_result["total_assets"] > 0:
        st.caption(
            f"총 자산 {format_won(portfolio_result['total_assets'])} · "
            f"현금 비중 {format_percent(portfolio_result['cash_weight'])}"
        )


def render_price_chart(settings: dict, mobile_mode: bool = False):
    st.subheader("시장 차트")
    st.caption("선택한 티커의 가격 흐름을 분봉, 일봉, 주봉, 월봉, 연봉 기준으로 확인합니다.")

    label_map = get_ticker_label_map(settings)

    ticker_options = []

    for ticker in settings["market_tickers"].values():
        if ticker not in ticker_options:
            ticker_options.append(ticker)

    for ticker in settings.get("watchlist_tickers", []):
        if ticker not in ticker_options:
            ticker_options.append(ticker)

    for ticker in settings.get("portfolio_tickers", []):
        if ticker not in ticker_options:
            ticker_options.append(ticker)

    if not ticker_options:
        st.warning("차트로 볼 티커가 없습니다.")
        return

    chart_mode_options = [
        "1분봉",
        "5분봉",
        "15분봉",
        "1시간봉",
        "일봉",
        "주봉",
        "월봉",
        "연봉",
    ]

    period_options_by_mode = {
        "1분봉": ["1d", "5d"],
        "5분봉": ["1d", "5d", "1mo"],
        "15분봉": ["5d", "1mo", "60d"],
        "1시간봉": ["5d", "1mo", "3mo", "6mo"],
        "일봉": ["1mo", "6mo", "1y", "5y", "max"],
        "주봉": ["6mo", "1y", "5y", "10y", "max"],
        "월봉": ["1y", "5y", "10y", "max"],
        "연봉": ["max"],
    }

    interval_by_mode = {
        "1분봉": "1m",
        "5분봉": "5m",
        "15분봉": "15m",
        "1시간봉": "1h",
        "일봉": "1d",
        "주봉": "1wk",
        "월봉": "1mo",
        "연봉": "1mo",
    }

    default_period_index_by_mode = {
        "1분봉": 0,
        "5분봉": 1,
        "15분봉": 1,
        "1시간봉": 2,
        "일봉": 2,
        "주봉": 4,
        "월봉": 3,
        "연봉": 0,
    }

    if mobile_mode:
        selected_ticker = st.selectbox(
            "차트 티커",
            options=ticker_options,
            format_func=lambda ticker: label_map.get(ticker, ticker),
            key="chart_ticker"
        )

        chart_mode = st.selectbox(
            "차트 기준",
            options=chart_mode_options,
            index=6,
            key="chart_mode"
        )

        selected_period = st.selectbox(
            "조회 기간",
            options=period_options_by_mode[chart_mode],
            index=default_period_index_by_mode[chart_mode],
            key="chart_period"
        )

    else:
        col1, col2, col3 = st.columns(3)

        with col1:
            selected_ticker = st.selectbox(
                "차트 티커",
                options=ticker_options,
                format_func=lambda ticker: label_map.get(ticker, ticker),
                key="chart_ticker"
            )

        with col2:
            chart_mode = st.selectbox(
                "차트 기준",
                options=chart_mode_options,
                index=6,
                key="chart_mode"
            )

        with col3:
            selected_period = st.selectbox(
                "조회 기간",
                options=period_options_by_mode[chart_mode],
                index=default_period_index_by_mode[chart_mode],
                key="chart_period"
            )

    interval = interval_by_mode[chart_mode]

    try:
        chart_df = cached_get_price_history(
            selected_ticker,
            selected_period,
            interval,
            chart_mode
        )

        st.line_chart(chart_df, use_container_width=True)

        latest_price = float(chart_df["가격"].iloc[-1])
        latest_time = chart_df.index[-1]

        st.caption(
            f"최근 데이터: {latest_time} · "
            f"{display_ticker(settings, selected_ticker)} 현재값: {format_market_value(selected_ticker, latest_price)}"
        )

        if chart_mode in ["1분봉", "5분봉", "15분봉", "1시간봉"]:
            st.caption("참고: 분봉/시간봉 데이터는 Yahoo Finance 정책상 조회 가능 기간이 제한될 수 있습니다.")

    except Exception as error:
        st.warning(f"차트 데이터를 불러오지 못했습니다: {error}")


def render_watchlist_cards(results: list, settings: dict):
    for result in results:
        ticker = result["ticker"]
        name = display_ticker(settings, ticker)

        with st.container(border=True):
            st.markdown(f"### {name}")

            if "error" in result:
                st.warning(f"오류: {result['error']}")
                continue

            st.write(f"**티커:** {ticker}")
            st.write(f"**가격 기준:** {result['price_source']}")
            st.write(f"**최근 데이터:** {result['latest_time']}")
            st.write(f"**현재가:** {result['current_price']:.2f}")
            st.write(f"**ATH:** {result['ath_price']:.2f}")
            st.write(f"**고점 대비:** {result['drawdown']:.2f}%")
            st.info(result["signal"])


def render_portfolio_cards(portfolio_result: dict):
    if portfolio_result["total_assets"] == 0:
        st.info("투자 비율을 설정해주세요.")
        return

    st.metric("투자 중인 금액", format_won(portfolio_result["total_invested"]))
    st.metric("현금", format_won(portfolio_result["cash"]))
    st.metric("총 자산", format_won(portfolio_result["total_assets"]))
    st.metric("현금 비중", format_percent(portfolio_result["cash_weight"]))

    if portfolio_result["rows"]:
        for row in portfolio_result["rows"]:
            with st.container(border=True):
                st.markdown(f"### {row['티커']}")
                st.write(f"**현재 금액:** {row['현재 금액']:,.0f}원")
                st.write(f"**현재 비중:** {row['현재 비중']:.2f}%")
                st.write(f"**목표 비중:** {row['목표 비중']:.2f}%")
                st.write(f"**차이:** {row['차이']:.2f}%p")
                st.write(f"**상태:** {row['상태']}")


def render_settings_form(settings: dict, user_id: str, key_prefix: str = "main"):
    st.caption("관심 티커, 목표 비중, 보유금액 등을 설정할 수 있습니다.")

    with st.expander("관심 티커 / 핵심 판단 기준", expanded=True):
        watchlist_text = ", ".join(settings["watchlist_tickers"])

        new_watchlist_text = st.text_input(
            "관심 티커",
            value=watchlist_text,
            help="예: SPY, VOO, QQQM, AAPL, NVDA, 005930.KS",
            key=f"{key_prefix}_watchlist_tickers"
        )

        settings["watchlist_tickers"] = normalize_ticker_list(new_watchlist_text)

        label_map = get_ticker_label_map(settings)

        signal_options = (
            list(settings["market_tickers"].values())
            + settings["watchlist_tickers"]
        )

        current_signal = settings.get("signal_ticker", "^GSPC")

        if current_signal not in signal_options:
            signal_options.append(current_signal)

        settings["signal_ticker"] = st.selectbox(
            "핵심 판단 기준",
            options=signal_options,
            index=signal_options.index(current_signal),
            format_func=lambda ticker: label_map.get(ticker, ticker),
            key=f"{key_prefix}_signal_ticker"
        )

    with st.expander("포트폴리오 자산", expanded=False):
        portfolio_text = ", ".join(settings["portfolio_tickers"])

        new_portfolio_text = st.text_input(
            "비중 관리할 자산",
            value=portfolio_text,
            help="예: VOO, QQQM",
            key=f"{key_prefix}_portfolio_tickers"
        )

        new_portfolio_tickers = normalize_ticker_list(new_portfolio_text)

        if new_portfolio_tickers:
            settings["portfolio_tickers"] = new_portfolio_tickers

        for ticker in settings["portfolio_tickers"]:
            settings["base_buy_plan"].setdefault(ticker, 0)
            settings["target_weights"].setdefault(ticker, 0)
            settings["portfolio"].setdefault(ticker, 0)

    with st.expander("평소 매수 계획", expanded=False):
        for ticker in settings["portfolio_tickers"]:
            current = float(settings["base_buy_plan"].get(ticker, 0))

            settings["base_buy_plan"][ticker] = st.number_input(
                f"{ticker} 평소 매수금액(USD)",
                min_value=0.0,
                value=current,
                step=1.0,
                key=f"{key_prefix}_base_buy_{ticker}"
            )

    with st.expander("목표 비중", expanded=False):
        for ticker in settings["portfolio_tickers"]:
            current = float(settings["target_weights"].get(ticker, 0))

            settings["target_weights"][ticker] = st.number_input(
                f"{ticker} 목표 비중(%)",
                min_value=0.0,
                value=current,
                step=1.0,
                key=f"{key_prefix}_target_weight_{ticker}"
            )

        current_tolerance = float(settings.get("rebalance_tolerance_percent", 5))

        settings["rebalance_tolerance_percent"] = st.number_input(
            "허용 오차(%p)",
            min_value=0.0,
            value=current_tolerance,
            step=1.0,
            key=f"{key_prefix}_rebalance_tolerance"
        )

    with st.expander("현재 포트폴리오", expanded=False):
        for ticker in settings["portfolio_tickers"]:
            current = float(settings["portfolio"].get(ticker, 0))

            settings["portfolio"][ticker] = st.number_input(
                f"{ticker} 보유금액(원)",
                min_value=0.0,
                value=current,
                step=10000.0,
                key=f"{key_prefix}_portfolio_{ticker}"
            )

        current_cash = float(settings["portfolio"].get("CASH", 0))

        settings["portfolio"]["CASH"] = st.number_input(
            "현금 보유금액(원)",
            min_value=0.0,
            value=current_cash,
            step=10000.0,
            key=f"{key_prefix}_cash"
        )

    with st.expander("추매 규칙", expanded=False):
        sorted_rules = sorted(
            settings["buy_rules"],
            key=lambda rule: float(rule.get("drawdown", 0)),
            reverse=True
        )

        updated_rules = []

        for idx, rule in enumerate(sorted_rules):
            rule_drawdown = st.number_input(
                f"{idx + 1}단계 하락률(%)",
                value=float(rule["drawdown"]),
                step=1.0,
                key=f"{key_prefix}_rule_drawdown_{idx}"
            )

            rule_message = st.text_input(
                f"{idx + 1}단계 메시지",
                value=rule["message"],
                key=f"{key_prefix}_rule_message_{idx}"
            )

            updated_rules.append({
                "drawdown": rule_drawdown,
                "message": rule_message
            })

        settings["buy_rules"] = updated_rules

    if st.button("설정 저장", type="primary", key=f"{key_prefix}_save_settings"):
        try:
            save_user_settings(user_id, settings)
            st.success("DB 저장 완료")
        except Exception as error:
            st.error(f"저장 실패: {error}")


def settings_sidebar(settings: dict, user_id: str):
    st.sidebar.title("⚙️ 설정")
    st.sidebar.caption(f"로그인: {get_current_user_email()}")

    if st.sidebar.button("로그아웃"):
        sign_out()
        rerun_app()

    st.sidebar.divider()

    render_settings_form(settings, user_id, key_prefix="sidebar")


def fetch_watchlist_results(tickers: list, settings: dict):
    results = []

    for ticker in tickers:
        try:
            result = cached_get_drawdown(ticker)
            result["signal"] = get_buy_signal(settings, result["drawdown"])
            results.append(result)
        except Exception as error:
            results.append({
                "ticker": ticker,
                "error": str(error)
            })

    return results


def fetch_market_status(settings: dict):
    results = []

    for label, ticker in settings["market_tickers"].items():
        try:
            result = cached_get_market_average_status(ticker)
            result["label"] = label
            results.append(result)
        except Exception as error:
            results.append({
                "label": label,
                "ticker": ticker,
                "error": str(error)
            })

    return results


def watchlist_results_to_dataframe(results: list, settings: dict):
    rows = []

    for result in results:
        label = display_ticker(settings, result["ticker"])

        if "error" in result:
            rows.append({
                "이름": label,
                "티커": result["ticker"],
                "가격 기준": "-",
                "최근 데이터 시간": "-",
                "현재가": "-",
                "ATH": "-",
                "고점 대비 하락률(%)": "-",
                "판단": f"오류: {result['error']}",
            })
            continue

        rows.append({
            "이름": label,
            "티커": result["ticker"],
            "가격 기준": result["price_source"],
            "최근 데이터 시간": str(result["latest_time"]),
            "현재가": round(result["current_price"], 2),
            "ATH": round(result["ath_price"], 2),
            "고점 대비 하락률(%)": round(result["drawdown"], 2),
            "판단": result["signal"],
        })

    return pd.DataFrame(rows)


def render_top_summary(settings: dict, mobile_mode: bool):
    buy_plan_text = " / ".join(
        f"{ticker} USD {amount:g}"
        for ticker, amount in settings["base_buy_plan"].items()
        if ticker in settings["portfolio_tickers"]
    )

    if buy_plan_text == "":
        buy_plan_text = "미설정"

    if mobile_mode:
        st.metric("핵심 판단 기준", display_ticker(settings, settings["signal_ticker"]))
        st.metric("평소 매수", buy_plan_text)
        st.metric("허용 오차", f"±{settings.get('rebalance_tolerance_percent', 5):g}%p")
    else:
        c1, c2, c3 = st.columns(3)

        with c1:
            st.metric("핵심 판단 기준", display_ticker(settings, settings["signal_ticker"]))

        with c2:
            st.metric("평소 매수", buy_plan_text)

        with c3:
            st.metric("허용 오차", f"±{settings.get('rebalance_tolerance_percent', 5):g}%p")


def render_signal_section(settings: dict, mobile_mode: bool):
    st.subheader("📌 오늘의 핵심 판단")
    st.caption("핵심 판단은 추매 규칙 적용을 위해 ATH 대비 하락률 기준으로 계산합니다.")

    signal_ticker = settings["signal_ticker"]

    try:
        signal_result = cached_get_drawdown(signal_ticker)
        signal_result["signal"] = get_buy_signal(settings, signal_result["drawdown"])

        if mobile_mode:
            st.metric("기준", display_ticker(settings, signal_result["ticker"]))
            st.metric(
                "현재가",
                format_market_value(
                    signal_result["ticker"],
                    signal_result["current_price"]
                )
            )
            st.metric(
                "ATH",
                format_market_value(
                    signal_result["ticker"],
                    signal_result["ath_price"]
                )
            )
            st.metric("고점 대비", f"{signal_result['drawdown']:.2f}%")
        else:
            k1, k2, k3, k4 = st.columns(4)

            with k1:
                st.metric("기준", display_ticker(settings, signal_result["ticker"]))

            with k2:
                st.metric(
                    "현재가",
                    format_market_value(
                        signal_result["ticker"],
                        signal_result["current_price"]
                    )
                )

            with k3:
                st.metric(
                    "ATH",
                    format_market_value(
                        signal_result["ticker"],
                        signal_result["ath_price"]
                    )
                )

            with k4:
                st.metric("고점 대비", f"{signal_result['drawdown']:.2f}%")

        st.info(signal_result["signal"])

    except Exception as error:
        st.warning(f"핵심 판단 기준 티커 데이터를 가져오지 못했습니다: {error}")


def render_market_summary_section(settings: dict, mobile_mode: bool):
    st.subheader("시장 요약")
    st.caption("시장 요약은 ATH 대비가 아니라 20일 평균 대비로 표시합니다.")

    with st.spinner("시장 지표를 불러오는 중..."):
        market_status = fetch_market_status(settings)

    if market_status:
        if mobile_mode:
            for result in market_status:
                with st.container(border=True):
                    if "error" in result:
                        st.metric(result["label"], "오류")
                        st.warning(result["error"])
                    else:
                        current_text = format_market_value(
                            result["ticker"],
                            result["current_price"]
                        )

                        delta_text = f"{result['average_diff_percent']:.2f}% vs 20일 평균"

                        st.metric(
                            result["label"],
                            current_text,
                            delta=delta_text,
                            help=(
                                f"{result['ticker']}\n"
                                f"20일 평균: {result['average_price']:.2f}\n"
                                f"전일 대비: {result['daily_change_percent']:.2f}%"
                            )
                        )
        else:
            cols = st.columns(min(4, len(market_status)))

            for idx, result in enumerate(market_status):
                col = cols[idx % len(cols)]

                with col:
                    if "error" in result:
                        st.metric(result["label"], "오류")
                    else:
                        current_text = format_market_value(
                            result["ticker"],
                            result["current_price"]
                        )

                        delta_text = f"{result['average_diff_percent']:.2f}% vs 20일 평균"

                        st.metric(
                            result["label"],
                            current_text,
                            delta=delta_text,
                            help=(
                                f"{result['ticker']}\n"
                                f"20일 평균: {result['average_price']:.2f}\n"
                                f"전일 대비: {result['daily_change_percent']:.2f}%"
                            )
                        )


def render_portfolio_section(settings: dict, mobile_mode: bool):
    st.subheader("포트폴리오 분석")

    portfolio_result = analyze_portfolio_data(settings)

    if not portfolio_result["configured"]:
        st.info(portfolio_result["reason"])

    if mobile_mode:
        render_portfolio_pie(settings, portfolio_result)
        render_portfolio_cards(portfolio_result)
    else:
        left, right = st.columns([1.1, 1])

        with left:
            render_portfolio_pie(settings, portfolio_result)

        with right:
            p1, p2 = st.columns(2)

            with p1:
                st.metric("투자 중인 금액", format_won(portfolio_result["total_invested"]))

            with p2:
                st.metric("현금", format_won(portfolio_result["cash"]))

            p3, p4 = st.columns(2)

            with p3:
                st.metric("총 자산", format_won(portfolio_result["total_assets"]))

            with p4:
                st.metric("현금 비중", format_percent(portfolio_result["cash_weight"]))

            if portfolio_result["rows"]:
                portfolio_df = pd.DataFrame(portfolio_result["rows"])

                display_df = portfolio_df.copy()
                display_df["현재 금액"] = display_df["현재 금액"].map(lambda x: f"{x:,.0f}원")
                display_df["현재 비중"] = display_df["현재 비중"].map(lambda x: f"{x:.2f}%")
                display_df["목표 비중"] = display_df["목표 비중"].map(lambda x: f"{x:.2f}%")
                display_df["차이"] = display_df["차이"].map(lambda x: f"{x:.2f}%p")

                st.dataframe(display_df, use_container_width=True)

    st.markdown("### 다음 매수 추천")
    st.success(portfolio_result["recommendation"])


def main():
    if not is_logged_in():
        render_auth_page()
        return

    user_id = get_current_user_id()

    try:
        settings = load_user_settings(user_id)
    except Exception as error:
        st.error(f"사용자 설정을 불러오지 못했습니다: {error}")
        st.stop()

    settings_sidebar(settings, user_id)

    st.title("📈 HeliosAI")
    st.caption("데이터 기반 장기투자 관리 도구 · v1.8 USD Display Fix")

    mobile_mode = st.toggle("📱 모바일 보기", value=False)

    if mobile_mode:
        hide_streamlit_sidebar_button()

    if st.button("시장 데이터 새로고침 / 분석 실행", type="primary"):
        st.cache_data.clear()

    st.divider()

    tab_home, tab_chart, tab_watchlist, tab_settings = st.tabs(
        ["홈", "차트", "관심 티커", "설정"]
    )

    with tab_home:
        render_top_summary(settings, mobile_mode)

        st.divider()

        render_signal_section(settings, mobile_mode)

        st.divider()

        render_market_summary_section(settings, mobile_mode)

        st.divider()

        render_portfolio_section(settings, mobile_mode)

    with tab_chart:
        render_price_chart(settings, mobile_mode)

    with tab_watchlist:
        st.subheader("관심 티커별 하락률")
        st.caption("관심 티커는 ATH 대비 하락률 기준으로 표시합니다.")

        with st.spinner("관심 티커 데이터를 불러오는 중..."):
            watchlist_results = fetch_watchlist_results(
                settings["watchlist_tickers"],
                settings
            )

        watchlist_df = watchlist_results_to_dataframe(watchlist_results, settings)

        if mobile_mode:
            render_watchlist_cards(watchlist_results, settings)
        else:
            st.dataframe(watchlist_df, use_container_width=True)

    with tab_settings:
        st.subheader("⚙️ 투자 설정")
        render_settings_form(settings, user_id, key_prefix="main_settings")

    st.divider()

    st.caption(
        "주의: 이 프로그램은 투자 판단을 돕는 보조 도구이며, "
        "수익을 보장하지 않습니다. 실제 매매는 본인 판단과 책임으로 진행해야 합니다."
    )


if __name__ == "__main__":
    main()