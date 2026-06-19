#!/usr/bin/env python3
"""Grid-search SMC parameters on Bitget historical data."""
from __future__ import annotations

import itertools
import json
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

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

MARGIN_BUDGET = 200.0


@dataclass
class Bar:
    ts_ms: int
    open: float
    high: float
    low: float
    close: float


def fetch_bars(symbol: str, start_ms: int, end_ms: int) -> list[Bar]:
    bars: list[Bar] = []
    seen: set[int] = set()
    cursor = start_ms
    base = (
        "https://api.bitget.com/api/v2/mix/market/history-candles"
        f"?symbol={symbol}&productType=USDT-FUTURES&granularity=15m"
    )
    for _ in range(500):
        url = f"{base}&startTime={cursor}&limit=200"
        with urllib.request.urlopen(url, timeout=30) as resp:
            rows = json.loads(resp.read().decode()).get("data") or []
        if not rows:
            break
        added = 0
        last_ts = cursor
        for row in rows:
            ts = int(row[0])
            if ts < start_ms or ts > end_ms or ts in seen:
                continue
            seen.add(ts)
            bars.append(Bar(ts, float(row[1]), float(row[2]), float(row[3]), float(row[4])))
            added += 1
            last_ts = max(last_ts, ts)
        if added == 0:
            break
        cursor = last_ts + 1
        if cursor >= end_ms:
            break
    bars.sort(key=lambda b: b.ts_ms)
    return bars


def atr_pct(highs: list[float], lows: list[float], closes: list[float], period: int, idx: int) -> float:
    if idx < period:
        return 0.0
    trs = []
    for i in range(idx - period + 1, idx + 1):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return (sum(trs) / len(trs)) / closes[idx] if closes[idx] else 0.0


def recent_structure_break(closes, highs, lows, direction: str) -> bool:
    if len(closes) < 2:
        return False
    if direction == "LONG":
        window = highs[-6:] if len(highs) >= 6 else highs
        return closes[-1] > max(window[:-1]) if len(window) > 1 else True
    window = lows[-6:] if len(lows) >= 6 else lows
    return closes[-1] < min(window[:-1]) if len(window) > 1 else True


def simulate(
    bars: list[Bar],
    trade_size: float,
    swing_lookback: int,
    sweep_buffer_pct: float,
    ob_search_bars: int,
    rr_ratio: float,
    max_bars_after_sweep: int,
    min_atr_pct: float,
    max_atr_pct: float,
) -> dict:
    opens = [b.open for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]

    position = None
    entry_price = stop = target = 0.0
    pending_side = None
    pending_ob_low = pending_ob_high = pending_stop = pending_target = 0.0
    pending_expiry = 0
    last_swing_high = last_swing_low = 0.0
    range_high = range_low = 0.0
    trades_pnl: list[float] = []
    warmup = swing_lookback * 3 + ob_search_bars + 5

    for idx, bar in enumerate(bars):
        confirm_index = idx - swing_lookback
        if confirm_index >= swing_lookback:
            sh = confirm_swing_high(highs, confirm_index, swing_lookback)
            sl = confirm_swing_low(lows, confirm_index, swing_lookback)
            if sh is not None:
                last_swing_high = sh.price
                range_high = sh.price
            if sl is not None:
                last_swing_low = sl.price
                range_low = sl.price

        vol = atr_pct(highs, lows, closes, 14, idx)

        if position == "LONG":
            if bar.low <= stop or bar.close <= stop:
                trades_pnl.append((stop - entry_price) * trade_size)
                position = None
            elif bar.high >= target or bar.close >= target:
                trades_pnl.append((target - entry_price) * trade_size)
                position = None
            elif last_swing_low > 0 and bar.close < last_swing_low:
                trades_pnl.append((bar.close - entry_price) * trade_size)
                position = None
            continue
        if position == "SHORT":
            if bar.high >= stop or bar.close >= stop:
                trades_pnl.append((entry_price - stop) * trade_size)
                position = None
            elif bar.low <= target or bar.close <= target:
                trades_pnl.append((entry_price - target) * trade_size)
                position = None
            elif last_swing_high > 0 and bar.close > last_swing_high:
                trades_pnl.append((entry_price - bar.close) * trade_size)
                position = None
            continue

        if pending_side and idx > pending_expiry:
            pending_side = None
        elif pending_side:
            touched = price_in_zone(bar.low, bar.high, pending_ob_low, pending_ob_high)
            if pending_side == "LONG":
                in_val = in_discount(bar.close, range_low, range_high) or range_high <= range_low
                choch = recent_structure_break(closes[: idx + 1], highs[: idx + 1], lows[: idx + 1], "LONG")
                if (touched or choch) and in_val:
                    position, entry_price, stop, target = "LONG", bar.close, pending_stop, pending_target
                    pending_side = None
            else:
                in_val = in_premium(bar.close, range_low, range_high) or range_high <= range_low
                choch = recent_structure_break(closes[: idx + 1], highs[: idx + 1], lows[: idx + 1], "SHORT")
                if (touched or choch) and in_val:
                    position, entry_price, stop, target = "SHORT", bar.close, pending_stop, pending_target
                    pending_side = None

        if position or pending_side or idx < warmup:
            continue
        if vol < min_atr_pct or (max_atr_pct > 0 and vol > max_atr_pct):
            continue

        if last_swing_low > 0 and detect_bullish_sweep(bar.low, bar.close, last_swing_low, sweep_buffer_pct):
            ob = find_bullish_order_block(opens, highs, lows, closes, idx, ob_search_bars)
            if ob and last_swing_high > last_swing_low:
                stop_px = min(bar.low, last_swing_low) * (1.0 - sweep_buffer_pct)
                risk = bar.close - stop_px
                if risk > 0:
                    pending_side = "LONG"
                    pending_ob_low, pending_ob_high = ob.low, ob.high
                    pending_stop, pending_target = stop_px, bar.close + risk * rr_ratio
                    pending_expiry = idx + max_bars_after_sweep
            continue

        if last_swing_high > 0 and detect_bearish_sweep(bar.high, bar.close, last_swing_high, sweep_buffer_pct):
            ob = find_bearish_order_block(opens, highs, lows, closes, idx, ob_search_bars)
            if ob and last_swing_high > last_swing_low:
                stop_px = max(bar.high, last_swing_high) * (1.0 + sweep_buffer_pct)
                risk = stop_px - bar.close
                if risk > 0:
                    pending_side = "SHORT"
                    pending_ob_low, pending_ob_high = ob.low, ob.high
                    pending_stop, pending_target = stop_px, bar.close - risk * rr_ratio
                    pending_expiry = idx + max_bars_after_sweep

    net = sum(trades_pnl)
    wins = [p for p in trades_pnl if p > 0]
    losses = [p for p in trades_pnl if p <= 0]
    gw = sum(wins)
    gl = abs(sum(losses))
    pf = gw / gl if gl > 0 else 0.0
    wr = len(wins) / len(trades_pnl) if trades_pnl else 0.0
    return {
        "trades": len(trades_pnl),
        "net_pnl": net,
        "return_pct": net / MARGIN_BUDGET * 100,
        "win_rate": wr,
        "profit_factor": pf,
    }


def main() -> None:
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XAUUSDT"]
    start_ms = int(datetime(2024, 6, 19, tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime(2026, 6, 19, tzinfo=timezone.utc).timestamp() * 1000)

    grid = {
        "swing_lookback": [4, 5, 6, 8],
        "sweep_buffer_pct": [0.0002, 0.0003, 0.0005, 0.0008],
        "ob_search_bars": [6, 8, 12],
        "rr_ratio": [1.5, 2.0, 2.5, 3.0],
        "max_bars_after_sweep": [8, 12, 16, 24],
        "min_atr_pct": [0.0008, 0.0012, 0.0018],
        "max_atr_pct": [0.0, 0.008, 0.012],
    }

    trade_sizes = {"BTCUSDT": 0.01, "ETHUSDT": 0.2, "SOLUSDT": 1.0, "XAUUSDT": 0.05}
    best_all: dict = {}

    for symbol in symbols:
        print(f"\n=== {symbol} ===")
        bars = fetch_bars(symbol, start_ms, end_ms)
        print(f"bars={len(bars)}")
        if len(bars) < 200:
            continue

        best = None
        best_score = -1e18
        count = 0
        for combo in itertools.product(
            grid["swing_lookback"],
            grid["sweep_buffer_pct"],
            grid["ob_search_bars"],
            grid["rr_ratio"],
            grid["max_bars_after_sweep"],
            grid["min_atr_pct"],
            grid["max_atr_pct"],
        ):
            count += 1
            sl, buf, ob, rr, mx, min_atr, max_atr = combo
            r = simulate(
                bars, trade_sizes[symbol], sl, buf, ob, rr, mx, min_atr, max_atr
            )
            if r["trades"] < 15:
                continue
            score = r["return_pct"] + r["profit_factor"] * 2 + r["win_rate"] * 5
            if r["profit_factor"] < 1.0:
                score -= 10
            if score > best_score:
                best_score = score
                best = {
                    "symbol": symbol,
                    "swing_lookback": sl,
                    "sweep_buffer_pct": buf,
                    "ob_search_bars": ob,
                    "rr_ratio": rr,
                    "max_bars_after_sweep": mx,
                    "min_atr_pct": min_atr,
                    "max_atr_pct": max_atr,
                    **r,
                }

        best_all[symbol] = best
        print(json.dumps(best, indent=2))

    out = ROOT / "logs" / "optimize_smc_results.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(best_all, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()