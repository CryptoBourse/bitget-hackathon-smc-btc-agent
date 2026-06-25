"""SMC BTC Agent M15 Playbook entry point."""
import math
from typing import Any

import pandas as pd

from getagent import backtest, data, runtime, trade

from live_smc import evaluate_smc_live
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


def _fetch_live_frame(symbol: str, interval: str, exchange: str, limit: int = 300) -> pd.DataFrame:
    bars = data.crypto.futures.kline(
        symbol=symbol,
        interval=interval,
        exchange=exchange,
        limit=limit,
    )
    return backtest.prepare_frame(bars, datetime_index="time")


def _execute_open(symbol: str, side: str, cfg: dict[str, Any]) -> None:
    if not runtime.is_follow_trade():
        return

    leverage = int(cfg.get("leverage", 3))
    margin_budget = str(cfg.get("margin_budget", "100"))
    normalized = trade.helpers.normalize_trading_symbol(symbol)

    qty_plan = trade.helpers.compute_qty(
        symbol=normalized,
        market="contract",
        budget_amount=margin_budget,
        leverage=leverage,
    )
    tpsl_plan = trade.helpers.resolve_contract_tpsl(
        symbol=normalized,
        side=side,
        leverage=leverage,
    )

    if side == "long":
        result = trade.contract.open_long_market(
            symbol=normalized,
            qty=qty_plan.qty,
            leverage=leverage,
            tp_trigger_price=tpsl_plan.tp_trigger_price,
            sl_trigger_price=tpsl_plan.sl_trigger_price,
        )
    else:
        result = trade.contract.open_short_market(
            symbol=normalized,
            qty=qty_plan.qty,
            leverage=leverage,
            tp_trigger_price=tpsl_plan.tp_trigger_price,
            sl_trigger_price=tpsl_plan.sl_trigger_price,
        )

    if not trade.is_success(result):
        raise RuntimeError(f"contract open failed: {result}")


def _execute_close(symbol: str, side: str) -> None:
    if not runtime.is_follow_trade():
        return

    normalized = trade.helpers.normalize_trading_symbol(symbol)
    hold_side = "long" if side == "close_long" else "short"
    pos_result = trade.contract.current_position(symbol=normalized)
    position = trade.helpers.find_contract_position(
        pos_result, normalized, hold_side=hold_side
    )
    if position is None:
        return

    close_side = "sell" if hold_side == "long" else "buy"
    result = trade.contract.place_order(
        symbol=normalized,
        side=close_side,
        order_type="market",
        qty=position.size,
        trade_side="close",
    )
    if not trade.is_success(result):
        raise RuntimeError(f"contract close failed: {result}")


def _emit_live_signal(
    action: str,
    symbol: str,
    confidence: float,
    metrics: dict[str, Any],
    meta: dict[str, Any],
    cfg: dict[str, Any],
) -> None:
    def execute_trade() -> None:
        if action == "long":
            _execute_open(symbol, "long", cfg)
        elif action == "short":
            _execute_open(symbol, "short", cfg)
        elif action in ("close_long", "close_short"):
            _execute_close(symbol, action)

    if runtime.is_follow_trade() and runtime.is_actionable_signal(action):
        runtime.emit_signal_or_follow(
            action=action,
            symbol=symbol,
            confidence=confidence,
            metrics=metrics,
            meta=meta,
            execute_trade=execute_trade,
        )
    else:
        runtime.emit_signal(
            action=action,
            symbol=symbol,
            confidence=confidence,
            metrics=metrics,
            meta=meta,
        )


def run_historical() -> None:
    cfg = runtime.manifest.get("strategy_config", {}) or {}
    symbols = cfg.get("trading_symbols") or ["BTCUSDT"]
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
            "mode": "historical",
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


def run_live() -> None:
    cfg = runtime.manifest.get("strategy_config", {}) or {}
    symbols = cfg.get("trading_symbols") or ["BTCUSDT"]
    symbol = symbols[0]
    interval = cfg.get("bar_interval", "15m")

    live_frame = _fetch_live_frame(symbol, interval, "bitget", limit=300)
    if live_frame.empty:
        runtime.emit_signal(
            action="watch",
            symbol=symbol,
            confidence=0.0,
            metrics={"rows": 0},
            meta={"reason": "no live bars returned", "mode": "live"},
        )
        return

    opens = live_frame["open"].tolist()
    highs = live_frame["high"].tolist()
    lows = live_frame["low"].tolist()
    closes = live_frame["close"].tolist()

    decision = evaluate_smc_live(opens, highs, lows, closes, cfg)
    action = decision.action
    reason = decision.reason

    force_probe = bool(cfg.get("force_probe_trade", False))
    if force_probe and action == "watch":
        action = "long"
        reason = "force_probe_trade_validation"

    metrics = _sanitize_metrics(
        {
            "rows": len(live_frame),
            "last_close": closes[-1] if closes else None,
            "atr_pct": decision.meta.get("atr_pct"),
            "volatility_regime": decision.meta.get("volatility_regime"),
        }
    )

    meta = {
        "agent": "smc_btc_autonomous_m15",
        "mode": "live",
        "bar_interval": interval,
        "decision": "smc_liquidity_sweep_orderblock",
        "reason": reason,
        "force_probe_trade": force_probe,
        "perception": {
            "volatility_regime": decision.meta.get("volatility_regime"),
            "structure_bias": decision.meta.get("structure_bias"),
            "atr_pct": decision.meta.get("atr_pct"),
        },
        "smc": decision.meta,
        "execution": "follow_trade" if runtime.is_follow_trade() else "signal_only",
        "history_end_ms": _frame_end_ms(live_frame),
    }

    _emit_live_signal(
        action=action,
        symbol=symbol,
        confidence=decision.confidence if reason != "force_probe_trade_validation" else 0.5,
        metrics=metrics,
        meta=meta,
        cfg=cfg,
    )


def run() -> None:
    if runtime.is_live():
        run_live()
    else:
        run_historical()


if __name__ == "__main__":
    run()