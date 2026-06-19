"""SMC Gold M15 Playbook entry point."""
import math
from typing import Any

import pandas as pd

from getagent import backtest, data, runtime

from perception import atr_percent, structure_bias, volatility_regime

XAU_LAUNCH_MS = 1765533622558


def _sanitize(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _sanitize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: _sanitize(val) for key, val in metrics.items()}


def _frame_start_ms(frame: pd.DataFrame) -> int | None:
    if frame.empty:
        return None
    first = frame.index[0]
    if hasattr(first, "timestamp"):
        return int(first.timestamp() * 1000)
    return int(first)


def _frame_end_ms(frame: pd.DataFrame) -> int | None:
    if frame.empty:
        return None
    last = frame.index[-1]
    if hasattr(last, "timestamp"):
        return int(last.timestamp() * 1000)
    return int(last)


def _fetch_replay_frame(symbol: str, interval: str, exchange: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    start_time = XAU_LAUNCH_MS
    max_pages = 12

    for _ in range(max_pages):
        bars = data.crypto.futures.kline(
            symbol=symbol,
            interval=interval,
            exchange=exchange,
            limit=1000,
            start_time=start_time,
        )
        frame = backtest.prepare_frame(bars, datetime_index="time")
        if frame.empty:
            break

        frames.append(frame)
        end_ms = _frame_end_ms(frame)
        if end_ms is None or end_ms <= start_time:
            break
        start_time = end_ms + 1

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames)
    combined = combined[~combined.index.duplicated(keep="last")]
    return combined.sort_index()


def run() -> None:
    cfg = runtime.manifest.get("strategy_config", {}) or {}
    symbols = cfg.get("trading_symbols") or ["XAUUSDT"]
    symbol = symbols[0]
    interval = cfg.get("bar_interval", "15m")

    replay_frame = _fetch_replay_frame(symbol, interval, "bitget")

    if replay_frame.empty:
        runtime.emit_signal(
            action="watch",
            symbol=symbol,
            confidence=0.0,
            metrics={"rows": 0},
            meta={"reason": "no historical bars returned", "timeframe": interval},
        )
        return

    instrument_key = f"{symbol}.BINANCE"
    result = backtest.run(
        ohlcv_data={instrument_key: replay_frame},
        spec=runtime.backtest_spec,
    )

    chart_path = backtest.generate_chart(result)
    summary = result.summary or {}
    net_pnl_raw = summary.get("net_pnl", 0)
    try:
        net_pnl = float(net_pnl_raw or 0)
    except (TypeError, ValueError):
        net_pnl = 0.0

    last_close = float(replay_frame["close"].iloc[-1]) if "close" in replay_frame.columns else 0.0
    highs = replay_frame["high"].tolist() if "high" in replay_frame.columns else []
    lows = replay_frame["low"].tolist() if "low" in replay_frame.columns else []
    closes = replay_frame["close"].tolist() if "close" in replay_frame.columns else []
    atr_val = atr_percent(highs, lows, closes, cfg.get("atr_period", 14), len(closes) - 1)
    regime = volatility_regime(atr_val, cfg.get("min_atr_pct", 0.0018), cfg.get("max_atr_pct", 0.0))
    bias = structure_bias(
        float(replay_frame["high"].max()) if "high" in replay_frame.columns else 0.0,
        float(replay_frame["low"].min()) if "low" in replay_frame.columns else 0.0,
        last_close,
    )

    action = "long" if net_pnl > 0 else "watch"
    if regime != "active":
        action = "watch"
    metrics = _sanitize_metrics(
        {
            "total_return_pct": result.total_return_pct,
            "net_pnl": net_pnl,
            "starting_balance": summary.get("starting_balance"),
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown_pct": result.max_drawdown_pct,
            "win_rate": result.win_rate,
            "total_trades": result.total_trades,
            "profit_factor": result.profit_factor,
            "rows": len(replay_frame),
        }
    )

    runtime.emit_signal(
        action=action,
        symbol=symbol,
        confidence=_sanitize(result.win_rate) or 0.0,
        metrics=metrics,
        meta={
            "chart_path": chart_path,
            "agent": "smc_btc_autonomous_m15",
            "bar_interval": interval,
            "perception": {
                "volatility_regime": regime,
                "structure_bias": bias,
                "atr_pct": atr_val,
            },
            "decision": "smc_liquidity_sweep_orderblock",
            "execution": "follow_trade" if runtime.manifest.get("execution_mode") == "follow_trade" else "signal_only",
            "swing_lookback": cfg.get("swing_lookback"),
            "rr_ratio": cfg.get("rr_ratio"),
            "history_start_ms": _frame_start_ms(replay_frame),
            "history_end_ms": _frame_end_ms(replay_frame),
        },
    )


if __name__ == "__main__":
    run()