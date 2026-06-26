# 분석할 티커들
TICKERS = ["SPY", "VOO", "QQQM"]

# 추매 기준으로 볼 대표 지수
SIGNAL_TICKER = "SPY"

# 사용자가 비중을 관리할 투자 자산
PORTFOLIO_TICKERS = ["VOO", "QQQM"]

# 평소 매수 계획
BASE_BUY_PLAN = {
    "VOO": 20,
    "QQQM": 20
}

# 목표 비중에서 이 정도까지는 봐주는 범위
# 0.05 = ±5%p
REBALANCE_TOLERANCE = 0.05

# 사용자 추매 규칙
BUY_RULES = [
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
    },
]