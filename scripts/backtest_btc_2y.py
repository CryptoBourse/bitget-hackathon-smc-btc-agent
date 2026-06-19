#!/usr/bin/env python3
"""SMC M15 backtest on BTCUSDT — target 2 years via Bitget history-candles."""
from __future__ import annotations

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

SYMBOL = "BTCUSDT"
INTERVAL = "15m"
START_MS = int(datetime(2024, 6, 19, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 6, 19, tzinfo=timezone.utc).timestamp() * 1000)
LOG_DIR = ROOT / "logs"
MARGIN_BUDGET = 200.0
TRADE_SIZE = 0.01


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


def ts_to_iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def fetch_bars(symbol: str, start_ms: int, end_ms: int) -> list[Bar]:
    bars: list[Bar] = []
    seen: set[int] = set()
    cursor = start_ms
    base = (
        "https://api.bitget.com/api/v2/mix/market/history-candles"
        f"?symbol={symbol}&productType=USDT-FUTURES&granularity=15m"
    )

    for page in range(500):
        url = f"{base}&startTime={cursor}&limit=200"
        with urllib.request.urlopen(url, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
        rows = payload.get("data") or []
        if not rows:
            break

        added = 0
        last_ts = cursor
        for row in rows:
            ts = int(row[0])
            if ts < start_ms or ts > end_ms or ts in seen:
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
            last_ts = max(last_ts, ts)

        if added == 0:
            break
        cursor = last_ts + 1
        if cursor >= end_ms:
            break
        if page % 20 == 0:
            print(f"  page {page}: {len(bars)} bars, up to {ts_to_iso(last_ts)}")

    bars.sort(key=lambda b: b.ts_ms)
    return bars


def recent_structure_break(
    closes: list[float], highs: list[float], lows: list[float], direction: str
) -> bool:
    if len(closes) < 2:
        return False
    if direction == "LONG":
        window = highs[-6:] if len(highs) >= 6 else highs
        return closes[-1] > max(window[:-1]) if len(window) > 1 else True
    window = lows[-6:] if len(lows) >= 6 else lows
    return closes[-1] < min(window[:-1]) if len(window) > 1 else True


def run_simulation(bars: list[Bar]) -> tuple[list[Trade], dict]:
    swing_lookback = 3
    sweep_buffer_pct = 0.0004
    ob_search_bars = 10
    rr_ratio = 2.0
    max_bars_after_sweep = 20

    opens = [b.open for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]

    balance = 10_000.0
    position = None
    entry_price = 0.0
    stop = 0.0
    target = 0.0

    pending_side = None
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
    equity = [balance]

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
            closed = False
            if position == "LONG":
                if bar.low <= stop or bar.close <= stop:
                    pnl = (stop - entry_price) * TRADE_SIZE
                    reason = "stop"
                    exit_px = stop
                elif bar.high >= target or bar.close >= target:
                    pnl = (target - entry_price) * TRADE_SIZE
                    reason = "target"
                    exit_px = target
                elif last_swing_low > 0 and bar.close < last_swing_low:
                    pnl = (bar.close - entry_price) * TRADE_SIZE
                    reason = "structure"
                    exit_px = bar.close
                else:
                    pnl = None
                if pnl is not None:
                    balance += pnl
                    trades.append(
                        Trade(
                            ts_to_iso(bar.ts_ms), SYMBOL, "long",
                            entry_price, exit_px, TRADE_SIZE, pnl, balance, reason,
                        )
                    )
                    position = None
                    closed = True
            elif position == "SHORT":
                if bar.high >= stop or bar.close >= stop:
                    pnl = (entry_price - stop) * TRADE_SIZE
                    reason = "stop"
                    exit_px = stop
                elif bar.low <= target or bar.close <= target:
                    pnl = (entry_price - target) * TRADE_SIZE
                    reason = "target"
                    exit_px = target
                elif last_swing_high > 0 and bar.close > last_swing_high:
                    pnl = (entry_price - bar.close) * TRADE_SIZE
                    reason = "structure"
                    exit_px = bar.close
                else:
                    pnl = None
                if pnl is not None:
                    balance += pnl
                    trades.append(
                        Trade(
                            ts_to_iso(bar.ts_ms), SYMBOL, "short",
                            entry_price, exit_px, TRADE_SIZE, pnl, balance, reason,
                        )
                    )
                    position = None
                    closed = True
            if closed:
                equity.append(balance)
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
                    choch_ok = recent_structure_break(
                        closes[: idx + 1], highs[: idx + 1], lows[: idx + 1], "LONG"
                    )
                    if (touched_ob or choch_ok) and in_value:
                        position = "LONG"
                        entry_price = bar.close
                        stop = pending_stop
                        target = pending_target
                        pending_side = None
                elif pending_side == "SHORT":
                    in_value = in_premium(bar.close, range_low, range_high) or range_high <= range_low
                    choch_ok = recent_structure_break(
                        closes[: idx + 1], highs[: idx + 1], lows[: idx + 1], "SHORT"
                    )
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

    peak = equity[0]
    max_dd = 0.0
    for eq in equity:
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak * 100)

    calendar_days = (bars[-1].ts_ms - bars[0].ts_ms) / 1000 / 86400 if bars else 0

    report = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "target_period": "2 years (2024-06-19 to 2026-06-19)",
        "data_source": "bitget_public_history_candles",
        "bar_count": len(bars),
        "calendar_days": round(calendar_days, 1),
        "period_start": ts_to_iso(bars[0].ts_ms) if bars else None,
        "period_end": ts_to_iso(bars[-1].ts_ms) if bars else None,
        "total_trades": len(trades),
        "win_rate": len(wins) / len(trades) if trades else 0.0,
        "profit_factor": pf,
        "net_pnl_usd": net_pnl,
        "strategy_return_pct": (net_pnl / MARGIN_BUDGET) * 100,
        "max_drawdown_pct": max_dd,
        "margin_budget": MARGIN_BUDGET,
        "trade_size_btc": TRADE_SIZE,
        "params": {
            "swing_lookback": 3,
            "sweep_buffer_pct": 0.0004,
            "ob_search_bars": 10,
            "rr_ratio": 2.0,
            "max_bars_after_sweep": 20,
        },
    }
    return trades, report


def main() -> None:
    print(f"Fetching {SYMBOL} {INTERVAL} from {ts_to_iso(START_MS)} to {ts_to_iso(END_MS)}...")
    bars = fetch_bars(SYMBOL, START_MS, END_MS)
    if not bars:
        raise SystemExit("No bars returned")
    print(f"Loaded {len(bars)} bars | {ts_to_iso(bars[0].ts_ms)} -> {ts_to_iso(bars[-1].ts_ms)}")

    trades, report = run_simulation(bars)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    trades_path = LOG_DIR / "backtest_btc_2y_trades.csv"
    with trades_path.open("w", encoding="utf-8") as fh:
        fh.write("timestamp,symbol,direction,entry_price,exit_price,quantity,pnl_usd,balance_after,exit_reason\n")
        for t in trades:
            fh.write(
                f"{t.timestamp},{t.symbol},{t.direction},{t.entry_price:.2f},"
                f"{t.exit_price:.2f},{t.quantity},{t.pnl_usd:.6f},{t.balance_after:.2f},{t.exit_reason}\n"
            )

    report_path = LOG_DIR / "backtest_btc_2y_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"\nWrote {trades_path}")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()