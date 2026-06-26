import csv
import os
from datetime import datetime

import yfinance as yf

from config import (
    TICKERS,
    SIGNAL_TICKER,
    PORTFOLIO_TICKERS,
    BASE_BUY_PLAN,
    BUY_RULES,
    REBALANCE_TOLERANCE,
)


def get_daily_close(ticker: str):
    """
    ATH 계산용 일봉 데이터
    """
    data = yf.download(
        ticker,
        period="max",
        interval="1d",
        progress=False,
        auto_adjust=True
    )

    if data.empty:
        raise ValueError(f"{ticker} 일봉 데이터를 가져오지 못했습니다.")

    close = data["Close"]

    # yfinance가 가끔 DataFrame 형태로 주는 경우 처리
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]

    return close


def get_latest_price(ticker: str):
    """
    현재가 계산용.
    1분봉을 먼저 시도하고, 실패하면 일봉 최신 종가로 대체.
    """
    intraday = yf.download(
        ticker,
        period="1d",
        interval="1m",
        progress=False,
        auto_adjust=True
    )

    if not intraday.empty:
        close = intraday["Close"]

        if hasattr(close, "columns"):
            close = close.iloc[:, 0]

        latest_price = close.iloc[-1].item()
        latest_time = close.index[-1]
        return latest_price, latest_time, "1분봉 최신가"

    # 1분봉 실패 시 일봉으로 대체
    daily_close = get_daily_close(ticker)
    latest_price = daily_close.iloc[-1].item()
    latest_time = daily_close.index[-1]
    return latest_price, latest_time, "일봉 종가"


def get_drawdown(ticker: str):
    """
    ATH는 전체 일봉 데이터 기준.
    현재가는 가능한 최신 분봉 기준.
    """
    daily_close = get_daily_close(ticker)

    ath_price = daily_close.max().item()
    latest_price, latest_time, price_source = get_latest_price(ticker)

    drawdown = (latest_price / ath_price - 1) * 100

    return {
        "ticker": ticker,
        "current_price": latest_price,
        "ath_price": ath_price,
        "drawdown": drawdown,
        "latest_time": latest_time,
        "price_source": price_source,
    }


def get_buy_signal(drawdown: float):
    """
    config.py에 저장된 사용자 추매 규칙을 기준으로 판단.
    drawdown 예시:
    -3.2  -> 평소 적립
    -8.4  -> -8% 규칙 해당
    -12.0 -> -10% 규칙 해당
    """
    for rule in BUY_RULES:
        if drawdown <= rule["drawdown"]:
            return rule["message"]

    return "✅ 평소 적립만 유지"


def get_user_number(prompt: str):
    """
    사용자에게 숫자를 입력받는 함수.
    쉼표가 있어도 처리 가능.
    예: 1,260,000 -> 1260000
    """
    while True:
        user_input = input(prompt).strip().replace(",", "")

        if user_input == "":
            return 0

        try:
            return float(user_input)
        except ValueError:
            print("숫자로 입력해주세요. 예: 1260000 또는 1,260,000")


def get_user_target_weights():
    """
    사용자가 직접 목표 비중을 입력.
    합계가 100이 아니어도 자동으로 비율 조정.
    """
    print("\n" + "=" * 40)
    print("🎯 목표 비중 입력")
    print("각 자산의 목표 비중을 %로 입력하세요.")
    print("예: VOO 50, QQQM 50")
    print("합계가 100이 아니어도 자동으로 비율 조정됩니다.")
    print("둘 다 엔터를 누르면 기본값 50:50으로 설정됩니다.\n")

    raw_weights = {}

    for ticker in PORTFOLIO_TICKERS:
        weight = get_user_number(f"{ticker} 목표 비중(%): ")
        raw_weights[ticker] = weight

    total_weight = sum(raw_weights.values())

    if total_weight == 0:
        print("\n목표 비중 입력이 없어 기본값 50:50으로 설정합니다.")
        equal_weight = 1 / len(PORTFOLIO_TICKERS)
        return {
            ticker: equal_weight
            for ticker in PORTFOLIO_TICKERS
        }

    target_weights = {
        ticker: weight / total_weight
        for ticker, weight in raw_weights.items()
    }

    print("\n적용된 목표 비중:")
    for ticker, weight in target_weights.items():
        print(f"- {ticker}: {weight * 100:.2f}%")

    return target_weights


def get_user_portfolio():
    """
    사용자가 직접 보유금액을 입력.
    단위는 원화 기준.
    """
    print("\n" + "=" * 40)
    print("💼 포트폴리오 입력")
    print("보유금액을 원화 기준으로 입력하세요.")
    print("없으면 그냥 엔터를 누르면 0원으로 처리됩니다.\n")

    portfolio = {}

    for ticker in PORTFOLIO_TICKERS:
        amount = get_user_number(f"{ticker} 보유금액: ")
        portfolio[ticker] = amount

    cash = get_user_number("현금 보유금액: ")
    portfolio["CASH"] = cash

    return portfolio


def print_market_report():
    """
    SPY, VOO, QQQM 하락률 출력
    """
    print("=== HeliosAI v0.7 ===")
    print("ETF 고점 대비 하락률 분석")
    print("※ ATH는 일봉 전체 데이터 기준")
    print("※ 현재가는 가능한 경우 1분봉 최신가 기준")
    print("※ 사용자 추매 규칙은 config.py에서 불러옵니다.\n")

    results = []

    for ticker in TICKERS:
        result = get_drawdown(ticker)
        signal = get_buy_signal(result["drawdown"])
        result["signal"] = signal
        results.append(result)

        print(f"\n[{result['ticker']}]")
        print(f"가격 기준: {result['price_source']}")
        print(f"최근 데이터 시간: {result['latest_time']}")
        print(f"현재가: {result['current_price']:.2f}")
        print(f"ATH: {result['ath_price']:.2f}")
        print(f"고점 대비 하락률: {result['drawdown']:.2f}%")
        print(f"판단: {signal}")

    return results


def print_main_signal(results):
    """
    대표 지수 기준으로 오늘 행동 판단
    """
    print("\n" + "=" * 40)
    print("📌 오늘의 핵심 판단")

    signal_result = None

    for result in results:
        if result["ticker"] == SIGNAL_TICKER:
            signal_result = result
            break

    if signal_result is None:
        print(f"{SIGNAL_TICKER} 데이터를 찾지 못했습니다.")
        return

    print(f"기준 티커: {SIGNAL_TICKER}")
    print(f"현재 하락률: {signal_result['drawdown']:.2f}%")
    print(f"오늘 판단: {signal_result['signal']}")

    print("\n평소 매수 계획:")
    for ticker, amount in BASE_BUY_PLAN.items():
        print(f"- {ticker}: {amount}달러")


def analyze_portfolio(portfolio: dict, target_weights: dict):
    """
    사용자가 입력한 포트폴리오를 기준으로 목표 비중 분석.
    목표 비중과의 차이가 ±REBALANCE_TOLERANCE 이내면 정상 범위로 판단.
    """
    print("\n" + "=" * 40)
    print("📊 포트폴리오 비중 분석")

    invest_assets = {
        ticker: amount
        for ticker, amount in portfolio.items()
        if ticker != "CASH"
    }

    total_invested = sum(invest_assets.values())
    cash = portfolio.get("CASH", 0)
    total_assets = total_invested + cash

    if total_invested == 0:
        print("투자 자산이 없습니다.")
        return

    print(f"투자 중인 금액: {total_invested:,.0f}원")
    print(f"현금: {cash:,.0f}원")
    print(f"총 자산: {total_assets:,.0f}원")

    if total_assets > 0:
        cash_weight = cash / total_assets * 100
        print(f"현금 비중: {cash_weight:.2f}%")

    gaps = {}

    print("\n목표 비중 비교:")
    print(f"허용 오차: ±{REBALANCE_TOLERANCE * 100:.0f}%p")

    for ticker, target_weight in target_weights.items():
        current_value = invest_assets.get(ticker, 0)
        current_weight = current_value / total_invested
        gap = target_weight - current_weight
        gaps[ticker] = gap

        status = "정상 범위"
        if gap > REBALANCE_TOLERANCE:
            status = "부족"
        elif gap < -REBALANCE_TOLERANCE:
            status = "초과"

        print(f"\n{ticker}")
        print(f"- 현재 금액: {current_value:,.0f}원")
        print(f"- 현재 비중: {current_weight * 100:.2f}%")
        print(f"- 목표 비중: {target_weight * 100:.2f}%")
        print(f"- 차이: {gap * 100:.2f}%p")
        print(f"- 상태: {status}")

    recommended = max(gaps, key=gaps.get)
    biggest_gap = gaps[recommended]

    print("\n다음 매수 추천:")

    if biggest_gap <= REBALANCE_TOLERANCE:
        print(
            f"➡️ 목표 비중과의 차이가 모두 ±{REBALANCE_TOLERANCE * 100:.0f}%p 이내입니다."
        )
        print("➡️ 현재는 리밸런싱 필요 없음. 기본 매수 계획대로 진행.")
    else:
        print(
            f"➡️ {recommended} 비중이 목표보다 {biggest_gap * 100:.2f}%p 낮습니다."
        )
        print(f"➡️ 다음 매수는 {recommended} 우선 추천.")


def save_report(results):
    """
    실행 결과를 logs/report.csv에 저장
    """
    os.makedirs("logs", exist_ok=True)

    file_path = "logs/report.csv"
    file_exists = os.path.exists(file_path)

    with open(file_path, "a", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "run_time",
                "ticker",
                "latest_time",
                "price_source",
                "current_price",
                "ath_price",
                "drawdown",
                "signal",
            ])

        run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for result in results:
            writer.writerow([
                run_time,
                result["ticker"],
                result["latest_time"],
                result["price_source"],
                round(result["current_price"], 2),
                round(result["ath_price"], 2),
                round(result["drawdown"], 2),
                result["signal"],
            ])

    print("\n" + "=" * 40)
    print(f"📝 리포트 저장 완료: {file_path}")


def main():
    results = print_market_report()
    print_main_signal(results)

    target_weights = get_user_target_weights()
    portfolio = get_user_portfolio()

    analyze_portfolio(portfolio, target_weights)
    save_report(results)


if __name__ == "__main__":
    main()