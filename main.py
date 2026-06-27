import copy
import csv
import json
import os
from datetime import datetime

import yfinance as yf

from config import DEFAULT_SETTINGS, SETTINGS_FILE


def save_settings(settings: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump(settings, file, ensure_ascii=False, indent=4)


def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        settings = copy.deepcopy(DEFAULT_SETTINGS)
        save_settings(settings)

        print("settings.json 파일이 없어 기본 설정으로 새로 만들었습니다.")
        print("처음 실행이므로 기본 설정을 불러옵니다.\n")

        return settings

    with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
        settings = json.load(file)

    return settings


def get_user_yes_no(prompt: str, default: str = "n"):
    user_input = input(prompt).strip().lower()

    if user_input == "":
        user_input = default

    return user_input in ["y", "yes", "ㅇ", "응"]


def get_user_number(prompt: str, default=None):
    while True:
        if default is not None:
            user_input = input(f"{prompt} [현재: {default}]: ").strip().replace(",", "")
        else:
            user_input = input(prompt).strip().replace(",", "")

        if user_input == "":
            if default is not None:
                return default
            return 0

        try:
            return float(user_input)
        except ValueError:
            print("숫자로 입력해주세요. 예: 1260000 또는 1,260,000")


def update_settings_by_prompt(settings: dict):
    print("\n" + "=" * 40)
    print("⚙️ 설정 수정")
    print("그냥 엔터를 누르면 기존 값이 유지됩니다.\n")

    portfolio_tickers = settings["portfolio_tickers"]

    print("1. 평소 매수 계획")
    for ticker in portfolio_tickers:
        current = settings["base_buy_plan"].get(ticker, 0)
        new_value = get_user_number(f"{ticker} 평소 매수금액(달러)", current)
        settings["base_buy_plan"][ticker] = new_value

    print("\n2. 목표 비중")
    print("예: VOO 50, QQQM 50")
    for ticker in portfolio_tickers:
        current = settings["target_weights"].get(ticker, 0)
        new_value = get_user_number(f"{ticker} 목표 비중(%)", current)
        settings["target_weights"][ticker] = new_value

    print("\n3. 현재 포트폴리오")
    print("원화 기준으로 입력하세요.")
    for ticker in portfolio_tickers:
        current = settings["portfolio"].get(ticker, 0)
        new_value = get_user_number(f"{ticker} 보유금액(원)", current)
        settings["portfolio"][ticker] = new_value

    current_cash = settings["portfolio"].get("CASH", 0)
    new_cash = get_user_number("현금 보유금액(원)", current_cash)
    settings["portfolio"]["CASH"] = new_cash

    print("\n4. 리밸런싱 허용 오차")
    current_tolerance = settings.get("rebalance_tolerance_percent", 5)
    new_tolerance = get_user_number("목표 비중 허용 오차(%)", current_tolerance)
    settings["rebalance_tolerance_percent"] = new_tolerance

    save_settings(settings)

    print("\n✅ 설정이 settings.json에 저장되었습니다.")

    return settings


def normalize_target_weights(target_weights: dict):
    total = sum(target_weights.values())

    if total == 0:
        equal_weight = 1 / len(target_weights)
        return {
            ticker: equal_weight
            for ticker in target_weights
        }

    return {
        ticker: weight / total
        for ticker, weight in target_weights.items()
    }


def get_daily_close(ticker: str):
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

    if hasattr(close, "columns"):
        close = close.iloc[:, 0]

    return close


def get_latest_price(ticker: str):
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

    daily_close = get_daily_close(ticker)
    latest_price = daily_close.iloc[-1].item()
    latest_time = daily_close.index[-1]
    return latest_price, latest_time, "일봉 종가"


def get_drawdown(ticker: str):
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


def get_buy_signal(settings: dict, drawdown: float):
    buy_rules = settings["buy_rules"]

    sorted_rules = sorted(
        buy_rules,
        key=lambda rule: rule["drawdown"]
    )

    for rule in sorted_rules:
        if drawdown <= rule["drawdown"]:
            return rule["message"]

    return "✅ 평소 적립만 유지"


def print_market_report(settings: dict):
    print("=== HeliosAI v0.8 ===")
    print("ETF 고점 대비 하락률 분석")
    print("※ ATH는 일봉 전체 데이터 기준")
    print("※ 현재가는 가능한 경우 1분봉 최신가 기준")
    print("※ 사용자 설정은 settings.json에서 불러옵니다.\n")

    results = []

    for ticker in settings["analysis_tickers"]:
        result = get_drawdown(ticker)
        signal = get_buy_signal(settings, result["drawdown"])
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


def print_main_signal(settings: dict, results: list):
    print("\n" + "=" * 40)
    print("📌 오늘의 핵심 판단")

    signal_ticker = settings["signal_ticker"]
    signal_result = None

    for result in results:
        if result["ticker"] == signal_ticker:
            signal_result = result
            break

    if signal_result is None:
        print(f"{signal_ticker} 데이터를 찾지 못했습니다.")
        return

    print(f"기준 티커: {signal_ticker}")
    print(f"현재 하락률: {signal_result['drawdown']:.2f}%")
    print(f"오늘 판단: {signal_result['signal']}")

    print("\n평소 매수 계획:")
    for ticker, amount in settings["base_buy_plan"].items():
        print(f"- {ticker}: {amount:g}달러")


def analyze_portfolio(settings: dict):
    print("\n" + "=" * 40)
    print("📊 포트폴리오 비중 분석")

    portfolio = settings["portfolio"]
    target_weights = normalize_target_weights(settings["target_weights"])
    tolerance = settings.get("rebalance_tolerance_percent", 5) / 100

    portfolio_tickers = settings["portfolio_tickers"]

    invest_assets = {
        ticker: portfolio.get(ticker, 0)
        for ticker in portfolio_tickers
    }

    total_invested = sum(invest_assets.values())
    cash = portfolio.get("CASH", 0)
    total_assets = total_invested + cash

    if total_invested == 0:
        print("투자 자산이 없습니다.")
        print("settings.json에서 보유금액을 입력하거나, 다음 실행 때 설정을 수정하세요.")
        return

    print(f"투자 중인 금액: {total_invested:,.0f}원")
    print(f"현금: {cash:,.0f}원")
    print(f"총 자산: {total_assets:,.0f}원")

    if total_assets > 0:
        cash_weight = cash / total_assets * 100
        print(f"현금 비중: {cash_weight:.2f}%")

    gaps = {}

    print("\n목표 비중 비교:")
    print(f"허용 오차: ±{tolerance * 100:.0f}%p")

    for ticker in portfolio_tickers:
        target_weight = target_weights.get(ticker, 0)
        current_value = invest_assets.get(ticker, 0)
        current_weight = current_value / total_invested
        gap = target_weight - current_weight
        gaps[ticker] = gap

        status = "정상 범위"

        if gap > tolerance:
            status = "부족"
        elif gap < -tolerance:
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

    if biggest_gap <= tolerance:
        print(f"➡️ 목표 비중과의 차이가 모두 ±{tolerance * 100:.0f}%p 이내입니다.")
        print("➡️ 현재는 리밸런싱 필요 없음. 기본 매수 계획대로 진행.")
    else:
        print(f"➡️ {recommended} 비중이 목표보다 {biggest_gap * 100:.2f}%p 낮습니다.")
        print(f"➡️ 다음 매수는 {recommended} 우선 추천.")


def save_report(settings: dict, results: list):
    os.makedirs("logs", exist_ok=True)

    file_path = "logs/report.csv"
    file_exists = os.path.exists(file_path)

    with open(file_path, "a", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "run_time",
                "signal_ticker",
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
                settings["signal_ticker"],
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
    settings = load_settings()

    print("현재 설정 파일: settings.json")

    should_update = get_user_yes_no("설정을 수정할까요? (y/N): ", default="n")

    if should_update:
        settings = update_settings_by_prompt(settings)

    results = print_market_report(settings)
    print_main_signal(settings, results)
    analyze_portfolio(settings)
    save_report(settings, results)


if __name__ == "__main__":
    main()