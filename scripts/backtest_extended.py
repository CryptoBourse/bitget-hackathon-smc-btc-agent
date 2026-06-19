#!/usr/bin/env python3
"""Extended XAUUSDT M15 SMC backtest using Bitget public history-candles API.

Reproducible supplementary evidence for the Bitget Hackathon submission.
Run: python scripts/backtest_extended.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from smc import (  # noqa: E402
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

XAU_LAUNCH_MS = 1765533622558
BITGET_URL = (
    "https://api.bitget.com/api/v2/mix/market/history-candles"
    "?symbol=XAUUSDT&productType=USDT-FUTURES&granularity=15m"
)
LOG_DIR = ROOT / "logs"
MARGIN_BUDGET = 200.0
TRADE_SIZE = 0.05


@dataclass
class Bar:
    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Trade:
    timestamp: str
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl_usd: float
    balance_after: float
    exit_reason: str


def fetch_bars() -> list[Bar]:
    bars: list[Bar] = []
    start = XAU_LAUNCH_MS
    seen: set[int] = set()

    for _ in range(200):
        url = f"{BITGET_URL}&startTime={start}&limit=200"
        with urllib.request.urlopen(url, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
        rows = payload.get("data") or []
        if not rows:
            break

        added = 0
        for row in rows:
            ts = int(row[0])
            if ts in seen:
                continue
            seen.add(ts)
            bars.append(
                Bar(
                    ts_ms=ts,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
            added += 1

        if added == 0:
            break
        start = bars[-1].ts_ms + 1

    bars.sort(key=lambda b: b.ts_ms)
    return bars


def ts_to_iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def recent_structure_break(closes: list[float], highs: list[float], lows: list[float], direction: str) -> bool:
    if len(closes) < 2:
        return False
    if direction == "LONG":
        window = highs[-6:] if len(highs) >= 6 else highs
        return closes[-1] > max(window[:-1]) if len(window) > 1 else True
    window = lows[-6:] if len(lows) >= 6 else lows
    return closes[-1] < min(window[:-1]) if len(window) > 1 else True


def run_simulation(
    bars: list[Bar],
    swing_lookback: int = 3,
    sweep_buffer_pct: float = 0.0004,
    ob_search_bars: int = 10,
    rr_ratio: float = 2.0,
    max_bars_after_sweep: int = 20,
) -> tuple[list[Trade], dict]:
    opens = [b.open for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]

    balance = 10_000.0
    position: str | None = None
    entry_price = 0.0
    stop = 0.0
    target = 0.0

    pending_side: str | None = None
    pending_ob_low = 0.0
    pending_ob_high = 0.0
    pending_stop = 0.0
    pending_target = 0.0
    pending_expiry = 0

    last_swing_high = 0.0
    last_swing_low = 0.0
    range_high = 0.0
    range_low = 0.0
    trades: list[Trade] = []

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

        if position is not None:
            if position == "LONG":
                if bar.low <= stop or bar.close <= stop:
                    pnl = (stop - entry_price) * TRADE_SIZE
                    balance += pnl
                    trades.append(
                        Trade(
                            ts_to_iso(bar.ts_ms), "XAUUSDT", "long",
                            entry_price, stop, TRADE_SIZE, pnl, balance, "stop",
                        )
                    )
                    position = None
                elif bar.high >= target or bar.close >= target:
                    pnl = (target - entry_price) * TRADE_SIZE
                    balance += pnl
                    trades.append(
                        Trade(
                            ts_to_iso(bar.ts_ms), "XAUUSDT", "long",
                            entry_price, target, TRADE_SIZE, pnl, balance, "target",
                        )
                    )
                    position = None
                elif last_swing_low > 0 and bar.close < last_swing_low:
                    pnl = (bar.close - entry_price) * TRADE_SIZE
                    balance += pnl
                    trades.append(
                        Trade(
                            ts_to_iso(bar.ts_ms), "XAUUSDT", "long",
                            entry_price, bar.close, TRADE_SIZE, pnl, balance, "structure",
                        )
                    )
                    position = None
            elif position == "SHORT":
                if bar.high >= stop or bar.close >= stop:
                    pnl = (entry_price - stop) * TRADE_SIZE
                    balance += pnl
                    trades.append(
                        Trade(
                            ts_to_iso(bar.ts_ms), "XAUUSDT", "short",
                            entry_price, stop, TRADE_SIZE, pnl, balance, "stop",
                        )
                    )
                    position = None
                elif bar.low <= target or bar.close <= target:
                    pnl = (entry_price - target) * TRADE_SIZE
                    balance += pnl
                    trades.append(
                        Trade(
                            ts_to_iso(bar.ts_ms), "XAUUSDT", "short",
                            entry_price, target, TRADE_SIZE, pnl, balance, "target",
                        )
                    )
                    position = None
                elif last_swing_high > 0 and bar.close > last_swing_high:
                    pnl = (entry_price - bar.close) * TRADE_SIZE
                    balance += pnl
                    trades.append(
                        Trade(
                            ts_to_iso(bar.ts_ms), "XAUUSDT", "short",
                            entry_price, bar.close, TRADE_SIZE, pnl, balance, "structure",
                        )
                    )
                    position = None
            continue

        if pending_side is not None:
            if idx > pending_expiry:
                pending_side = None
            else:
                touched_ob = price_in_zone(
                    bar.low, bar.high, pending_ob_low, pending_ob_high
                )
                if pending_side == "LONG":
                    in_value = in_discount(bar.close, range_low, range_high) or range_high <= range_low
                    choch_ok = recent_structure_break(closes[: idx + 1], highs[: idx + 1], lows[: idx + 1], "LONG")
                    if (touched_ob or choch_ok) and in_value:
                        position = "LONG"
                        entry_price = bar.close
                        stop = pending_stop
                        target = pending_target
                        pending_side = None
                elif pending_side == "SHORT":
                    in_value = in_premium(bar.close, range_low, range_high) or range_high <= range_low
                    choch_ok = recent_structure_break(closes[: idx + 1], highs[: idx + 1], lows[: idx + 1], "SHORT")
                    if (touched_ob or choch_ok) and in_value:
                        position = "SHORT"
                        entry_price = bar.close
                        stop = pending_stop
                        target = pending_target
                        pending_side = None

        if position is not None or pending_side is not None or idx < warmup:
            continue

        if last_swing_low > 0 and detect_bullish_sweep(
            bar.low, bar.close, last_swing_low, sweep_buffer_pct
        ):
            ob = find_bullish_order_block(opens, highs, lows, closes, idx, ob_search_bars)
            if ob is not None and last_swing_high > last_swing_low:
                stop_px = min(bar.low, last_swing_low) * (1.0 - sweep_buffer_pct)
                risk = bar.close - stop_px
                if risk > 0:
                    pending_side = "LONG"
                    pending_ob_low = ob.low
                    pending_ob_high = ob.high
                    pending_stop = stop_px
                    pending_target = bar.close + risk * rr_ratio
                    pending_expiry = idx + max_bars_after_sweep
            continue

        if last_swing_high > 0 and detect_bearish_sweep(
            bar.high, bar.close, last_swing_high, sweep_buffer_pct
        ):
            ob = find_bearish_order_block(opens, highs, lows, closes, idx, ob_search_bars)
            if ob is not None and last_swing_high > last_swing_low:
                stop_px = max(bar.high, last_swing_high) * (1.0 + sweep_buffer_pct)
                risk = stop_px - bar.close
                if risk > 0:
                    pending_side = "SHORT"
                    pending_ob_low = ob.low
                    pending_ob_high = ob.high
                    pending_stop = stop_px
                    pending_target = bar.close - risk * rr_ratio
                    pending_expiry = idx + max_bars_after_sweep

    net_pnl = sum(t.pnl_usd for t in trades)
    wins = [t for t in trades if t.pnl_usd > 0]
    losses = [t for t in trades if t.pnl_usd <= 0]
    gross_win = sum(t.pnl_usd for t in wins)
    gross_loss = abs(sum(t.pnl_usd for t in losses))
    pf = gross_win / gross_loss if gross_loss > 0 else None

    report = {
        "symbol": "XAUUSDT",
        "interval": "15m",
        "data_source": "bitget_public_history_candles",
        "bar_count": len(bars),
        "period_start": ts_to_iso(bars[0].ts_ms) if bars else None,
        "period_end": ts_to_iso(bars[-1].ts_ms) if bars else None,
        "total_trades": len(trades),
        "win_rate": len(wins) / len(trades) if trades else 0.0,
        "profit_factor": pf,
        "net_pnl_usd": net_pnl,
        "strategy_return_pct": (net_pnl / MARGIN_BUDGET) * 100,
        "margin_budget": MARGIN_BUDGET,
        "trade_size": TRADE_SIZE,
        "params": {
            "swing_lookback": swing_lookback,
            "sweep_buffer_pct": sweep_buffer_pct,
            "ob_search_bars": ob_search_bars,
            "rr_ratio": rr_ratio,
            "max_bars_after_sweep": max_bars_after_sweep,
        },
        "note": "Supplementary extended backtest for hackathon. Primary demo remains GetAgent Playbook cloud run.",
    }
    return trades, report


def write_outputs(bars: list[Bar], trades: list[Trade], report: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    trades_path = LOG_DIR / "backtest_extended_trades.csv"
    with trades_path.open("w", encoding="utf-8") as fh:
        fh.write("timestamp,symbol,direction,entry_price,exit_price,quantity,pnl_usd,balance_after,exit_reason\n")
        for t in trades:
            fh.write(
                f"{t.timestamp},{t.symbol},{t.direction},{t.entry_price:.2f},"
                f"{t.exit_price:.2f},{t.quantity},{t.pnl_usd:.6f},{t.balance_after:.2f},{t.exit_reason}\n"
            )

    report_path = LOG_DIR / "backtest_extended_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"\nWrote {trades_path}")
    print(f"Wrote {report_path}")


def main() -> None:
    print("Fetching Bitget XAUUSDT 15m history...")
    bars = fetch_bars()
    if not bars:
        raise SystemExit("No bars returned from Bitget API")
    print(f"Loaded {len(bars)} bars from {ts_to_iso(bars[0].ts_ms)} to {ts_to_iso(bars[-1].ts_ms)}")
    trades, report = run_simulation(bars)
    write_outputs(bars, trades, report)


if __name__ == "__main__":
    main()