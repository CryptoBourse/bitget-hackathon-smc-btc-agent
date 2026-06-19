"""Smart Money Concepts helpers for structure, liquidity, and order blocks."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class SwingPoint:
    index: int
    price: float


@dataclass
class OrderBlock:
    low: float
    high: float
    is_bullish: bool


@dataclass
class SweepEvent:
    direction: str
    sweep_price: float
    swing_price: float
    bar_index: int


def confirm_swing_high(highs: list[float], index: int, lookback: int) -> Optional[SwingPoint]:
    if index < lookback or index + lookback >= len(highs):
        return None
    pivot = highs[index]
    left = highs[index - lookback : index]
    right = highs[index + 1 : index + lookback + 1]
    if pivot > max(left) and pivot > max(right):
        return SwingPoint(index=index, price=pivot)
    return None


def confirm_swing_low(lows: list[float], index: int, lookback: int) -> Optional[SwingPoint]:
    if index < lookback or index + lookback >= len(lows):
        return None
    pivot = lows[index]
    left = lows[index - lookback : index]
    right = lows[index + 1 : index + lookback + 1]
    if pivot < min(left) and pivot < min(right):
        return SwingPoint(index=index, price=pivot)
    return None


def detect_bullish_sweep(
    low: float,
    close: float,
    swing_low: float,
    buffer_pct: float,
) -> bool:
    if swing_low <= 0:
        return False
    sweep_level = swing_low * (1.0 - buffer_pct)
    return low < sweep_level and close > swing_low


def detect_bearish_sweep(
    high: float,
    close: float,
    swing_high: float,
    buffer_pct: float,
) -> bool:
    if swing_high <= 0:
        return False
    sweep_level = swing_high * (1.0 + buffer_pct)
    return high > sweep_level and close < swing_high


def find_bullish_order_block(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    end_index: int,
    search_bars: int,
) -> Optional[OrderBlock]:
    start = max(0, end_index - search_bars)
    for i in range(end_index, start - 1, -1):
        if closes[i] < opens[i]:
            return OrderBlock(low=lows[i], high=highs[i], is_bullish=True)
    return None


def find_bearish_order_block(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    end_index: int,
    search_bars: int,
) -> Optional[OrderBlock]:
    start = max(0, end_index - search_bars)
    for i in range(end_index, start - 1, -1):
        if closes[i] > opens[i]:
            return OrderBlock(low=lows[i], high=highs[i], is_bullish=False)
    return None


def in_discount(price: float, range_low: float, range_high: float) -> bool:
    if range_high <= range_low:
        return False
    equilibrium = (range_high + range_low) / 2.0
    return price <= equilibrium


def in_premium(price: float, range_low: float, range_high: float) -> bool:
    if range_high <= range_low:
        return False
    equilibrium = (range_high + range_low) / 2.0
    return price >= equilibrium


def price_in_zone(low: float, high: float, zone_low: float, zone_high: float) -> bool:
    return low <= zone_high and high >= zone_low