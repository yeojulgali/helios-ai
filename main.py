import json
from datetime import datetime

import yfinance as yf

from config import DEFAULT_SETTINGS, SETTINGS_FILE


def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
            saved_settings = json.load(file)

        return deep_merge(DEFAULT_SETTINGS, saved_settings)

    except FileNotFoundError:
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS

    except Exception:
        return DEFAULT_SETTINGS


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump(settings, file, ensure_ascii=False, indent=4)


def deep_merge(default, saved):
    result = default.copy()

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


def normalize_target_weights(target_weights):
    total = sum(float(value) for value in target_weights.values())

    if total == 0:
        return {
            ticker: 0
            for ticker in target_weights
        }

    return {
        ticker: float(value) / total
        for ticker, value in target_weights.items()
    }


def get_latest_price_info(ticker):
    ticker_obj = yf.Ticker(ticker)

    intraday_data = ticker_obj.history(period="1d", interval="1m", auto_adjust=True)

    if not intraday_data.empty:
        close = intraday_data["Close"].dropna()

        if not close.empty:
            latest_price = float(close.iloc[-1])
            latest_time = close.index[-1]

            return {
                "price": latest_price,
                "latest_time": latest_time,
                "price_source": "1분봉 최신가"
            }

    daily_data = ticker_obj.history(period="5d", interval="1d", auto_adjust=True)

    if daily_data.empty:
        raise ValueError(f"{ticker} 가격 데이터를 가져오지 못했습니다.")

    close = daily_data["Close"].dropna()

    if close.empty:
        raise ValueError(f"{ticker} 유효한 종가 데이터가 없습니다.")

    latest_price = float(close.iloc[-1])
    latest_time = close.index[-1]

    return {
        "price": latest_price,
        "latest_time": latest_time,
        "price_source": "일봉 최신가"
    }


def get_drawdown(ticker):
    ticker_obj = yf.Ticker(ticker)

    price_info = get_latest_price_info(ticker)

    history = ticker_obj.history(period="max", auto_adjust=True)

    if history.empty:
        raise ValueError(f"{ticker} 장기 가격 데이터를 가져오지 못했습니다.")

    close = history["Close"].dropna()

    if close.empty:
        raise ValueError(f"{ticker} 유효한 장기 종가 데이터가 없습니다.")

    ath_price = float(close.max())
    current_price = float(price_info["price"])

    if ath_price == 0:
        raise ValueError(f"{ticker} ATH 가격이 0입니다.")

    drawdown = (current_price / ath_price - 1) * 100

    return {
        "ticker": ticker,
        "price_source": price_info["price_source"],
        "latest_time": str(price_info["latest_time"]),
        "current_price": current_price,
        "ath_price": ath_price,
        "drawdown": drawdown,
    }


def get_buy_signal(settings, drawdown):
    buy_rules = settings.get("buy_rules", [])

    if not buy_rules:
        return "✅ 평소 적립만 유지"

    # 실제 판단은 가장 큰 하락률 조건부터 확인해야 함.
    # 예: -25%, -20%, -15%, -10%, -8%, -5%
    sorted_rules = sorted(
        buy_rules,
        key=lambda rule: float(rule.get("drawdown", 0))
    )

    for rule in sorted_rules:
        rule_drawdown = float(rule.get("drawdown", 0))

        if drawdown <= rule_drawdown:
            return rule.get("message", "추매 구간")

    return "✅ 평소 적립만 유지"


def analyze_market(settings):
    results = []

    for ticker in settings.get("analysis_tickers", []):
        try:
            result = get_drawdown(ticker)
            result["signal"] = get_buy_signal(settings, result["drawdown"])
            results.append(result)

        except Exception as error:
            results.append({
                "ticker": ticker,
                "error": str(error)
            })

    return results


def print_report(settings):
    print("=" * 40)
    print(f"📈 {settings.get('project_name', 'HeliosAI')}")
    print("=" * 40)

    results = analyze_market(settings)

    for result in results:
        print()

        if "error" in result:
            print(f"{result['ticker']} 오류: {result['error']}")
            continue

        print(f"티커: {result['ticker']}")
        print(f"가격 기준: {result['price_source']}")
        print(f"최근 데이터 시간: {result['latest_time']}")
        print(f"현재가: {result['current_price']:.2f}")
        print(f"ATH: {result['ath_price']:.2f}")
        print(f"고점 대비 하락률: {result['drawdown']:.2f}%")
        print(f"판단: {result['signal']}")

    print()
    print("=" * 40)
    print("📌 오늘의 핵심 판단")
    print("=" * 40)

    signal_ticker = settings.get("signal_ticker", "SPY")

    try:
        signal_result = get_drawdown(signal_ticker)
        signal = get_buy_signal(settings, signal_result["drawdown"])

        print(f"기준 티커: {signal_ticker}")
        print(f"현재 하락률: {signal_result['drawdown']:.2f}%")
        print(f"오늘 판단: {signal}")

    except Exception as error:
        print(f"핵심 판단 오류: {error}")

    print()
    print("평소 매수 계획:")

    for ticker, amount in settings.get("base_buy_plan", {}).items():
        print(f"- {ticker}: {amount}달러")


def main():
    settings = load_settings()
    print_report(settings)


if __name__ == "__main__":
    main()