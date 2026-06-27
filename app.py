import copy
import json
import os

import pandas as pd
import streamlit as st
import yfinance as yf

from config import DEFAULT_SETTINGS, SETTINGS_FILE
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


# =========================
# 설정 저장 / 불러오기
# =========================

def deep_merge(default: dict, saved: dict):
    """
    settings.json이 예전 구조여도 새 DEFAULT_SETTINGS와 병합해서
    새로 추가된 설정값이 자동으로 생기게 함.
    """
    result = copy.deepcopy(default)

    for key, value in saved.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def save_settings(settings: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump(settings, file, ensure_ascii=False, indent=4)


def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        settings = copy.deepcopy(DEFAULT_SETTINGS)
        save_settings(settings)
        return settings

    with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
        saved_settings = json.load(file)

    settings = deep_merge(DEFAULT_SETTINGS, saved_settings)
    save_settings(settings)

    return settings


# =========================
# 표시 / 포맷
# =========================

def get_ticker_label_map(settings: dict):
    """
    내부 티커를 사람이 읽는 이름으로 바꿔주는 맵.
    예: ^GSPC -> S&P500
    """
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


def format_dollar(value):
    return f"${value:,.2f}"


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


# =========================
# 데이터 캐시
# =========================

@st.cache_data(ttl=300)
def cached_get_drawdown(ticker: str):
    """
    ATH 대비 하락률 계산용.
    관심 티커, 핵심 판단, 추매 규칙에 사용.
    """
    return get_drawdown(ticker)


@st.cache_data(ttl=300)
def cached_get_market_average_status(ticker: str, average_days: int = 20):
    """
    시장 요약용.
    ATH 대비가 아니라 최근 20일 평균 대비로 계산.
    """
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

    current_price = close.iloc[-1].item()
    latest_time = close.index[-1]

    recent_close = close.tail(average_days)
    average_price = recent_close.mean().item()

    average_diff_percent = (current_price / average_price - 1) * 100

    if len(close) >= 2:
        previous_price = close.iloc[-2].item()
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


# =========================
# 포트폴리오 분석
# =========================

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
            "reason": "아직 포트폴리오 보유금액이 설정되지 않았습니다.",
            "total_invested": 0,
            "cash": cash,
            "total_assets": total_assets,
            "cash_weight": 0,
            "rows": [],
            "recommendation": "왼쪽 설정에서 보유금액을 입력해주세요.",
        }

    if target_total == 0:
        return {
            "configured": False,
            "reason": "아직 목표 비중이 설정되지 않았습니다.",
            "total_invested": total_invested,
            "cash": cash,
            "total_assets": total_assets,
            "cash_weight": cash / total_assets * 100 if total_assets > 0 else 0,
            "rows": [],
            "recommendation": "왼쪽 설정에서 목표 비중을 입력해주세요.",
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


# =========================
# 사이드바 설정 UI
# =========================

def settings_sidebar(settings: dict):
    st.sidebar.title("⚙️ 설정")
    st.sidebar.caption("값을 바꾼 뒤 저장 버튼을 누르면 settings.json에 저장됩니다.")

    with st.sidebar.expander("시장 지표", expanded=False):
        st.caption("시장 분위기를 보는 지표입니다. 화면 이름과 Yahoo Finance 티커를 수정할 수 있습니다.")

        market_tickers = settings["market_tickers"]
        new_market_tickers = {}

        for name, ticker in market_tickers.items():
            col1, col2 = st.columns([1.2, 1])

            with col1:
                new_name = st.text_input(
                    f"{name} 표시 이름",
                    value=name,
                    key=f"market_name_{name}"
                )

            with col2:
                new_ticker = st.text_input(
                    f"{name} 티커",
                    value=ticker,
                    key=f"market_ticker_{name}"
                ).upper()

            if new_name and new_ticker:
                new_market_tickers[new_name] = new_ticker

        settings["market_tickers"] = new_market_tickers

    with st.sidebar.expander("관심 티커", expanded=True):
        watchlist_text = ", ".join(settings["watchlist_tickers"])

        new_watchlist_text = st.text_input(
            "관심 티커",
            value=watchlist_text,
            help="예: SPY, VOO, QQQM, AAPL, NVDA, 005930.KS"
        )

        settings["watchlist_tickers"] = normalize_ticker_list(new_watchlist_text)

        label_map = get_ticker_label_map(settings)

        signal_options = list(settings["market_tickers"].values()) + settings["watchlist_tickers"]
        current_signal = settings.get("signal_ticker", "^GSPC")

        if current_signal not in signal_options:
            signal_options.append(current_signal)

        settings["signal_ticker"] = st.selectbox(
            "핵심 판단 기준",
            options=signal_options,
            index=signal_options.index(current_signal),
            format_func=lambda ticker: label_map.get(ticker, ticker)
        )

    with st.sidebar.expander("포트폴리오 자산", expanded=True):
        portfolio_text = ", ".join(settings["portfolio_tickers"])

        new_portfolio_text = st.text_input(
            "비중 관리할 자산",
            value=portfolio_text,
            help="예: VOO, QQQM"
        )

        new_portfolio_tickers = normalize_ticker_list(new_portfolio_text)

        if new_portfolio_tickers:
            settings["portfolio_tickers"] = new_portfolio_tickers

        for ticker in settings["portfolio_tickers"]:
            settings["base_buy_plan"].setdefault(ticker, 0)
            settings["target_weights"].setdefault(ticker, 0)
            settings["portfolio"].setdefault(ticker, 0)

    with st.sidebar.expander("평소 매수 계획", expanded=True):
        for ticker in settings["portfolio_tickers"]:
            current = float(settings["base_buy_plan"].get(ticker, 0))
            settings["base_buy_plan"][ticker] = st.number_input(
                f"{ticker} 평소 매수금액($)",
                min_value=0.0,
                value=current,
                step=1.0,
                key=f"base_buy_{ticker}"
            )

    with st.sidebar.expander("목표 비중", expanded=True):
        for ticker in settings["portfolio_tickers"]:
            current = float(settings["target_weights"].get(ticker, 0))
            settings["target_weights"][ticker] = st.number_input(
                f"{ticker} 목표 비중(%)",
                min_value=0.0,
                value=current,
                step=1.0,
                key=f"target_weight_{ticker}"
            )

        current_tolerance = float(settings.get("rebalance_tolerance_percent", 5))
        settings["rebalance_tolerance_percent"] = st.number_input(
            "허용 오차(%p)",
            min_value=0.0,
            value=current_tolerance,
            step=1.0,
        )

    with st.sidebar.expander("현재 포트폴리오", expanded=True):
        for ticker in settings["portfolio_tickers"]:
            current = float(settings["portfolio"].get(ticker, 0))
            settings["portfolio"][ticker] = st.number_input(
                f"{ticker} 보유금액(원)",
                min_value=0.0,
                value=current,
                step=10000.0,
                key=f"portfolio_{ticker}"
            )

        current_cash = float(settings["portfolio"].get("CASH", 0))
        settings["portfolio"]["CASH"] = st.number_input(
            "현금 보유금액(원)",
            min_value=0.0,
            value=current_cash,
            step=10000.0,
        )

    with st.sidebar.expander("추매 규칙", expanded=False):
        for idx, rule in enumerate(settings["buy_rules"]):
            col1, col2 = st.columns([1, 3])

            with col1:
                rule["drawdown"] = st.number_input(
                    f"{idx + 1}단계 하락률(%)",
                    value=float(rule["drawdown"]),
                    step=1.0,
                    key=f"rule_drawdown_{idx}"
                )

            with col2:
                rule["message"] = st.text_input(
                    f"{idx + 1}단계 메시지",
                    value=rule["message"],
                    key=f"rule_message_{idx}"
                )

    if st.sidebar.button("설정 저장", type="primary"):
        save_settings(settings)
        st.sidebar.success("settings.json 저장 완료")


# =========================
# 시장 / 관심 티커 분석
# =========================

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


# =========================
# 메인 UI
# =========================

def main():
    settings = load_settings()
    settings_sidebar(settings)

    st.title("📈 HeliosAI")
    st.caption("AI 기반 장기투자 보조 시스템 · v1.1 UI Prototype")

    st.divider()

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("핵심 판단 기준", display_ticker(settings, settings["signal_ticker"]))

    with c2:
        buy_plan_text = " / ".join(
            f"{ticker} ${amount:g}"
            for ticker, amount in settings["base_buy_plan"].items()
            if ticker in settings["portfolio_tickers"]
        )

        if buy_plan_text == "":
            buy_plan_text = "미설정"

        st.metric("평소 매수", buy_plan_text)

    with c3:
        st.metric(
            "허용 오차",
            f"±{settings.get('rebalance_tolerance_percent', 5):g}%p"
        )

    if st.button("시장 데이터 새로고침 / 분석 실행", type="primary"):
        st.cache_data.clear()

    st.divider()

    # 시장 요약
    st.subheader("시장 요약")
    st.caption("시장 요약은 ATH 대비가 아니라 20일 평균 대비로 표시합니다.")

    with st.spinner("시장 지표를 불러오는 중..."):
        market_status = fetch_market_status(settings)

    if market_status:
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

    st.divider()

    # 핵심 판단
    st.subheader("📌 오늘의 핵심 판단")
    st.caption("핵심 판단은 추매 규칙 적용을 위해 ATH 대비 하락률 기준으로 계산합니다.")

    signal_ticker = settings["signal_ticker"]

    try:
        signal_result = cached_get_drawdown(signal_ticker)
        signal_result["signal"] = get_buy_signal(settings, signal_result["drawdown"])

        k1, k2, k3, k4 = st.columns(4)

        with k1:
            st.metric("기준", display_ticker(settings, signal_result["ticker"]))

        with k2:
            st.metric("현재가", format_market_value(signal_result["ticker"], signal_result["current_price"]))

        with k3:
            st.metric("ATH", format_market_value(signal_result["ticker"], signal_result["ath_price"]))

        with k4:
            st.metric("고점 대비", f"{signal_result['drawdown']:.2f}%")

        st.info(signal_result["signal"])

    except Exception as error:
        st.warning(f"핵심 판단 기준 티커 데이터를 가져오지 못했습니다: {error}")

    st.divider()

    # 관심 티커별 분석
    st.subheader("관심 티커별 하락률")
    st.caption("관심 티커는 ATH 대비 하락률 기준으로 표시합니다.")

    with st.spinner("관심 티커 데이터를 불러오는 중..."):
        watchlist_results = fetch_watchlist_results(settings["watchlist_tickers"], settings)

    watchlist_df = watchlist_results_to_dataframe(watchlist_results, settings)

    st.dataframe(watchlist_df, use_container_width=True)

    st.divider()

    # 포트폴리오 분석
    st.subheader("포트폴리오 분석")

    portfolio_result = analyze_portfolio_data(settings)

    p1, p2, p3, p4 = st.columns(4)

    with p1:
        st.metric("투자 중인 금액", format_won(portfolio_result["total_invested"]))

    with p2:
        st.metric("현금", format_won(portfolio_result["cash"]))

    with p3:
        st.metric("총 자산", format_won(portfolio_result["total_assets"]))

    with p4:
        st.metric("현금 비중", format_percent(portfolio_result["cash_weight"]))

    if not portfolio_result["configured"]:
        st.warning(portfolio_result["reason"])

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

    st.divider()

    st.caption(
        "주의: 이 프로그램은 투자 판단을 돕는 보조 도구이며, "
        "수익을 보장하지 않습니다. 실제 매매는 본인 판단과 책임으로 진행해야 합니다."
    )


if __name__ == "__main__":
    main()