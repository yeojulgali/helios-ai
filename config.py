SETTINGS_FILE = "settings.json"


DEFAULT_SETTINGS = {
    "project_name": "HeliosAI",

    # 시장 전체 분위기를 보는 지표들
    # key = 화면 표시 이름, value = Yahoo Finance 티커
    "market_tickers": {
        "S&P500": "^GSPC",
        "Nasdaq100": "^NDX",
        "Nasdaq Composite": "^IXIC",
        "KOSPI": "^KS11",
        "KOSDAQ": "^KQ11",
        "VIX": "^VIX",
        "USD/KRW": "USDKRW=X"
    },

    # 사용자가 관심 있게 보는 종목/ETF
    "watchlist_tickers": ["SPY", "VOO", "QQQM"],

    # 추매 판단 기준으로 볼 티커
    # 기본은 S&P500 지수
    "signal_ticker": "^GSPC",

    # 실제 포트폴리오 비중 관리를 할 자산
    "portfolio_tickers": ["VOO", "QQQM"],

    # 평소 매수 계획
    # 기본값은 0. 사용자가 설정에서 입력
    "base_buy_plan": {
        "VOO": 0,
        "QQQM": 0
    },

    # 목표 비중
    # 기본값은 0. 사용자가 설정에서 입력
    "target_weights": {
        "VOO": 0,
        "QQQM": 0
    },

    # 목표 비중 허용 오차
    # 5 = ±5%p
    "rebalance_tolerance_percent": 5,

    # 현재 포트폴리오
    # 기본값은 0. 사용자가 설정에서 입력
    "portfolio": {
        "VOO": 0,
        "QQQM": 0,
        "CASH": 0
    },

    # 사용자 추매 규칙
    "buy_rules": [
        {
            "drawdown": -25,
            "message": "🔥 -25% 이상 하락: 75만 원 추매 구간"
        },
        {
            "drawdown": -20,
            "message": "🔥 -20% 이상 하락: 75만 원 추매 구간"
        },
        {
            "drawdown": -15,
            "message": "📉 -15% 이상 하락: 50만 원 추매 구간"
        },
        {
            "drawdown": -10,
            "message": "📉 -10% 이상 하락: 50만 원 추매 구간"
        },
        {
            "drawdown": -8,
            "message": "🟡 -8% 이상 하락: 소액 추가매수 고민 구간"
        },
        {
            "drawdown": -5,
            "message": "🟢 -5% 이상 하락: 20달러 추가매수 가능 구간"
        }
    ]
}