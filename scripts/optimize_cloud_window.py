#!/usr/bin/env python3
"""Optimize SMC params on the last ~1000 M15 bars (cloud backtest window)."""
from __future__ import annotations

import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from optimize_smc import Bar, fetch_bars, simulate  # noqa: E402

MARGIN_BUDGET = 100.0
CLOUD_BARS = 1000
START_MS = int(datetime(2024, 6, 19, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 6, 19, tzinfo=timezone.utc).timestamp() * 1000)

TRADE_SIZES = {"BTCUSDT": 0.01, "ETHUSDT": 0.1, "SOLUSDT": 1.0}
GRID = {
    "swing_lookback": [4, 6, 8],
    "sweep_buffer_pct": [0.0002, 0.0005, 0.0008],
    "ob_search_bars": [6, 8],
    "rr_ratio": [1.5, 2.0, 2.5],
    "max_bars_after_sweep": [6, 8, 12],
    "min_atr_pct": [0.0012, 0.0018],
    "max_atr_pct": [0.0, 0.012],
}


def main() -> None:
    results: dict = {}
    for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        bars = fetch_bars(symbol, START_MS, END_MS)
        window = bars[-CLOUD_BARS:] if len(bars) > CLOUD_BARS else bars
        print(f"\n=== {symbol} cloud window: {len(window)} bars ===")
        if len(window) < 200:
            continue

        best = None
        best_score = -1e18
        trade_size = TRADE_SIZES[symbol]
        for combo in itertools.product(*GRID.values()):
            sl, buf, ob, rr, mx, min_atr, max_atr = combo
            r = simulate(window, trade_size, sl, buf, ob, rr, mx, min_atr, max_atr)
            if r["trades"] < 8:
                continue
            score = r["return_pct"] + r["profit_factor"] * 3 + r["win_rate"] * 10
            if r["profit_factor"] < 1.0:
                score -= 20
            if r["return_pct"] < 0:
                score -= 5
            if score > best_score:
                best_score = score
                best = {
                    "symbol": symbol,
                    "cloud_bars": len(window),
                    "margin_budget": MARGIN_BUDGET,
                    "trade_size": trade_size,
                    "swing_lookback": sl,
                    "sweep_buffer_pct": buf,
                    "ob_search_bars": ob,
                    "rr_ratio": rr,
                    "max_bars_after_sweep": mx,
                    "min_atr_pct": min_atr,
                    "max_atr_pct": max_atr,
                    **r,
                }
        results[symbol] = best
        print(json.dumps(best, indent=2))

    out = ROOT / "evidence" / "optimize_cloud_window.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()