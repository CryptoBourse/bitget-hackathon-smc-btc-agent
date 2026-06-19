#!/usr/bin/env python3
"""Fair multi-asset SMC comparison (default params, no publish)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from optimize_smc import MARGIN_BUDGET, fetch_bars, simulate  # noqa: E402

XAU_LAUNCH_MS = 1765533622558
START_MS = int(datetime(2024, 6, 19, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2026, 6, 19, tzinfo=timezone.utc).timestamp() * 1000)
CLOUD_BARS = 1000

DEFAULT = dict(
    swing_lookback=3,
    sweep_buffer_pct=0.0004,
    ob_search_bars=10,
    rr_ratio=2.0,
    max_bars_after_sweep=20,
    min_atr_pct=0.0,
    max_atr_pct=0.0,
)
TRADE_SIZES = {"BTCUSDT": 0.01, "ETHUSDT": 0.2, "SOLUSDT": 1.0, "XAUUSDT": 0.05}


def main() -> None:
    results = []
    for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XAUUSDT"]:
        start = XAU_LAUNCH_MS if symbol == "XAUUSDT" else START_MS
        bars = fetch_bars(symbol, start, END_MS)
        window = bars[-CLOUD_BARS:] if len(bars) > CLOUD_BARS else bars
        if len(window) < 50:
            results.append({"symbol": symbol, "bars": len(window), "error": "insufficient data"})
            continue
        r = simulate(window, TRADE_SIZES[symbol], **DEFAULT)
        results.append(
            {
                "symbol": symbol,
                "bars": len(window),
                "window": "last_1000_or_all",
                "params": "default",
                "margin_budget": MARGIN_BUDGET,
                **r,
            }
        )

    opt_long = json.loads((ROOT / "evidence" / "optimize_smc_results.json").read_text())
    opt_cloud = json.loads((ROOT / "evidence" / "optimize_cloud_window.json").read_text())

    print("=== FAIR COMPARISON: DEFAULT PARAMS, ~1000 BARS ===")
    for row in sorted(results, key=lambda x: x.get("return_pct", -999), reverse=True):
        if "error" in row:
            print(f"{row['symbol']}: {row['error']} ({row['bars']} bars)")
        else:
            print(
                f"{row['symbol']}: ROI {row['return_pct']:.2f}% | "
                f"trades {row['trades']} | WR {row['win_rate']*100:.1f}% | "
                f"PF {row['profit_factor']:.2f} | bars {row['bars']}"
            )

    print("\n=== OPTIMIZED: LONG WINDOW (~1744 bars sparse) ===")
    for sym in ["ETHUSDT", "BTCUSDT", "SOLUSDT"]:
        o = opt_long[sym]
        print(
            f"{sym}: ROI {o['return_pct']:.2f}% | trades {o['trades']} | PF {o['profit_factor']:.2f}"
        )

    print("\n=== OPTIMIZED: CLOUD WINDOW (1000 bars) ===")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        o = opt_cloud[sym]
        print(
            f"{sym}: ROI {o['return_pct']:.2f}% | trades {o['trades']} | PF {o['profit_factor']:.2f}"
        )


if __name__ == "__main__":
    main()