"""Market perception helpers for the SMC agent."""


def atr_percent(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int,
    index: int,
) -> float:
    if index < period or index <= 0:
        return 0.0
    trs: list[float] = []
    for i in range(index - period + 1, index + 1):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    close = closes[index]
    if close <= 0:
        return 0.0
    return (sum(trs) / len(trs)) / close


def volatility_regime(
    atr_pct: float,
    min_atr_pct: float,
    max_atr_pct: float,
) -> str:
    if atr_pct < min_atr_pct:
        return "quiet"
    if max_atr_pct > 0 and atr_pct > max_atr_pct:
        return "extreme"
    return "active"


def structure_bias(last_swing_high: float, last_swing_low: float, close: float) -> str:
    if last_swing_high <= 0 or last_swing_low <= 0 or last_swing_high <= last_swing_low:
        return "neutral"
    mid = (last_swing_high + last_swing_low) / 2.0
    if close >= mid:
        return "bullish_structure"
    return "bearish_structure"