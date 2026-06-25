"""Live SMC decision engine — mirrors strategy.py state machine on OHLC arrays."""
from dataclasses import dataclass
from typing import Any

from perception import atr_percent, structure_bias, volatility_regime
from smc import (
    confirm_swing_high,
    confirm_swing_low,
    detect_bearish_sweep,
    detect_bullish_sweep,
    find_bearish_order_block,
    find_bullish_order_block,
    in_discount,
    in_premium,
    price_in_zone,
)


@dataclass
class LiveDecision:
    action: str
    confidence: float
    reason: str
    meta: dict[str, Any]


def _recent_structure_break(closes: list[float], highs: list[float], lows: list[float], direction: str) -> bool:
    if direction == "LONG":
        window = highs[-6:] if len(highs) >= 6 else highs
        if not window or len(window) <= 1:
            return False
        return closes[-1] > max(window[:-1])
    window = lows[-6:] if len(lows) >= 6 else lows
    if not window or len(window) <= 1:
        return False
    return closes[-1] < min(window[:-1])


def evaluate_smc_live(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    cfg: dict[str, Any],
) -> LiveDecision:
    swing_lookback = int(cfg.get("swing_lookback", 6))
    sweep_buffer_pct = float(cfg.get("sweep_buffer_pct", 0.0008))
    ob_search_bars = int(cfg.get("ob_search_bars", 6))
    rr_ratio = float(cfg.get("rr_ratio", 2.5))
    max_bars_after_sweep = int(cfg.get("max_bars_after_sweep", 6))
    atr_period = int(cfg.get("atr_period", 14))
    min_atr_pct = float(cfg.get("min_atr_pct", 0.0018))
    max_atr_pct = float(cfg.get("max_atr_pct", 0.0))

    last_swing_high = 0.0
    last_swing_low = 0.0
    range_high = 0.0
    range_low = 0.0
    position = "NONE"
    pending_side: str | None = None
    pending_ob_low = 0.0
    pending_ob_high = 0.0
    pending_stop = 0.0
    pending_target = 0.0
    pending_expiry = 0
    signal_action = "watch"
    signal_reason = "no_smc_setup"

    warmup = swing_lookback * 3 + ob_search_bars + 5
    if len(closes) < warmup + 1:
        return LiveDecision(
            action="watch",
            confidence=0.0,
            reason="warmup_insufficient",
            meta={"bars": len(closes), "warmup_required": warmup + 1},
        )

    for idx in range(len(closes)):
        open_px = opens[idx]
        high = highs[idx]
        low = lows[idx]
        close = closes[idx]

        confirm_index = idx - swing_lookback
        if confirm_index >= swing_lookback:
            swing_high = confirm_swing_high(highs, confirm_index, swing_lookback)
            swing_low = confirm_swing_low(lows, confirm_index, swing_lookback)
            if swing_high is not None:
                last_swing_high = swing_high.price
                range_high = swing_high.price
            if swing_low is not None:
                last_swing_low = swing_low.price
                range_low = swing_low.price

        if position in ("LONG", "SHORT"):
            if position == "LONG":
                if low <= pending_stop or close <= pending_stop:
                    if idx == len(closes) - 1:
                        signal_action = "close_long"
                        signal_reason = "stop_hit"
                    position = "NONE"
                elif high >= pending_target or close >= pending_target:
                    if idx == len(closes) - 1:
                        signal_action = "close_long"
                        signal_reason = "target_hit"
                    position = "NONE"
                elif last_swing_high > 0 and close < last_swing_low:
                    if idx == len(closes) - 1:
                        signal_action = "close_long"
                        signal_reason = "structure_invalidation"
                    position = "NONE"
            elif position == "SHORT":
                if high >= pending_stop or close >= pending_stop:
                    if idx == len(closes) - 1:
                        signal_action = "close_short"
                        signal_reason = "stop_hit"
                    position = "NONE"
                elif low <= pending_target or close <= pending_target:
                    if idx == len(closes) - 1:
                        signal_action = "close_short"
                        signal_reason = "target_hit"
                    position = "NONE"
                elif last_swing_low > 0 and close > last_swing_high:
                    if idx == len(closes) - 1:
                        signal_action = "close_short"
                        signal_reason = "structure_invalidation"
                    position = "NONE"
            continue

        if pending_side is not None:
            if idx > pending_expiry:
                pending_side = None
            else:
                if pending_side == "LONG":
                    touched_ob = price_in_zone(low, high, pending_ob_low, pending_ob_high)
                    in_value = in_discount(close, range_low, range_high) or range_high <= range_low
                    choch_ok = _recent_structure_break(closes[: idx + 1], highs[: idx + 1], lows[: idx + 1], "LONG")
                    if (touched_ob or choch_ok) and in_value:
                        if idx == len(closes) - 1:
                            signal_action = "long"
                            signal_reason = "bullish_ob_retest"
                        position = "LONG"
                        pending_side = None
                elif pending_side == "SHORT":
                    touched_ob = price_in_zone(low, high, pending_ob_low, pending_ob_high)
                    in_value = in_premium(close, range_low, range_high) or range_high <= range_low
                    choch_ok = _recent_structure_break(closes[: idx + 1], highs[: idx + 1], lows[: idx + 1], "SHORT")
                    if (touched_ob or choch_ok) and in_value:
                        if idx == len(closes) - 1:
                            signal_action = "short"
                            signal_reason = "bearish_ob_retest"
                        position = "SHORT"
                        pending_side = None

        if position != "NONE" or pending_side is not None:
            continue

        if idx < warmup:
            continue

        atr_val = atr_percent(highs[: idx + 1], lows[: idx + 1], closes[: idx + 1], atr_period, idx)
        regime = volatility_regime(atr_val, min_atr_pct, max_atr_pct)
        if regime != "active":
            continue

        if last_swing_low > 0 and detect_bullish_sweep(low, close, last_swing_low, sweep_buffer_pct):
            ob = find_bullish_order_block(opens, highs, lows, closes, idx, ob_search_bars)
            if ob is not None and last_swing_high > last_swing_low:
                stop = min(low, last_swing_low) * (1.0 - sweep_buffer_pct)
                risk = close - stop
                if risk > 0:
                    pending_side = "LONG"
                    pending_ob_low = ob.low
                    pending_ob_high = ob.high
                    pending_stop = stop
                    pending_target = close + risk * rr_ratio
                    pending_expiry = idx + max_bars_after_sweep
            continue

        if last_swing_high > 0 and detect_bearish_sweep(high, close, last_swing_high, sweep_buffer_pct):
            ob = find_bearish_order_block(opens, highs, lows, closes, idx, ob_search_bars)
            if ob is not None and last_swing_high > last_swing_low:
                stop = max(high, last_swing_high) * (1.0 + sweep_buffer_pct)
                risk = stop - close
                if risk > 0:
                    pending_side = "SHORT"
                    pending_ob_low = ob.low
                    pending_ob_high = ob.high
                    pending_stop = stop
                    pending_target = close - risk * rr_ratio
                    pending_expiry = idx + max_bars_after_sweep

    idx = len(closes) - 1
    atr_val = atr_percent(highs, lows, closes, atr_period, idx)
    regime = volatility_regime(atr_val, min_atr_pct, max_atr_pct)
    bias = structure_bias(last_swing_high, last_swing_low, closes[-1])

    confidence = 0.55 if signal_action in ("long", "short") else 0.0
    if signal_action.startswith("close"):
        confidence = 0.65

    return LiveDecision(
        action=signal_action,
        confidence=confidence,
        reason=signal_reason,
        meta={
            "volatility_regime": regime,
            "structure_bias": bias,
            "atr_pct": atr_val,
            "last_swing_high": last_swing_high,
            "last_swing_low": last_swing_low,
            "pending_side": pending_side,
            "position": position,
            "bars_evaluated": len(closes),
        },
    )