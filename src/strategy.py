from decimal import Decimal
from typing import Optional

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy

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


class SmcGoldStrategyConfig(StrategyConfig):
    instrument_id: Optional[InstrumentId] = None
    bar_type: Optional[BarType] = None
    instrument_ids: tuple[InstrumentId, ...] = ()
    bar_types: tuple[BarType, ...] = ()
    trade_size: str = "0.01"
    swing_lookback: int = 6
    sweep_buffer_pct: float = 0.0008
    ob_search_bars: int = 6
    rr_ratio: float = 2.5
    max_bars_after_sweep: int = 8
    atr_period: int = 14
    min_atr_pct: float = 0.0018
    max_atr_pct: float = 0.0


class SmcGoldStrategy(Strategy):
    def __init__(self, config: SmcGoldStrategyConfig) -> None:
        super().__init__(config)
        self.cfg = config
        self._instrument: Optional[Instrument] = None
        self._opens: list[float] = []
        self._highs: list[float] = []
        self._lows: list[float] = []
        self._closes: list[float] = []
        self._last_swing_high: float = 0.0
        self._last_swing_low: float = 0.0
        self._range_high: float = 0.0
        self._range_low: float = 0.0
        self._position: str = "NONE"
        self._pending_side: Optional[str] = None
        self._pending_ob_low: float = 0.0
        self._pending_ob_high: float = 0.0
        self._pending_stop: float = 0.0
        self._pending_target: float = 0.0
        self._pending_expiry: int = 0
        self._entry_price: float = 0.0

    def on_start(self) -> None:
        bar_type = self.cfg.bar_type or (
            self.cfg.bar_types[0] if self.cfg.bar_types else None
        )
        instrument_id = self.cfg.instrument_id or (
            self.cfg.instrument_ids[0] if self.cfg.instrument_ids else None
        )
        if bar_type is None or instrument_id is None:
            raise RuntimeError("bar_type and instrument_id must be set")
        self._instrument = self.cache.instrument(instrument_id)
        self.subscribe_bars(bar_type)

    def on_bar(self, bar: Bar) -> None:
        open_px = float(bar.open)
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)

        self._opens.append(open_px)
        self._highs.append(high)
        self._lows.append(low)
        self._closes.append(close)
        idx = len(self._closes) - 1

        confirm_index = idx - self.cfg.swing_lookback
        if confirm_index >= self.cfg.swing_lookback:
            swing_high = confirm_swing_high(
                self._highs, confirm_index, self.cfg.swing_lookback
            )
            swing_low = confirm_swing_low(
                self._lows, confirm_index, self.cfg.swing_lookback
            )
            if swing_high is not None:
                self._last_swing_high = swing_high.price
                self._range_high = swing_high.price
            if swing_low is not None:
                self._last_swing_low = swing_low.price
                self._range_low = swing_low.price

        instrument = self._instrument
        if instrument is None:
            return

        if self._position in ("LONG", "SHORT"):
            self._manage_open_position(instrument, high, low, close)
            return

        if self._pending_side is not None:
            if idx > self._pending_expiry:
                self._clear_pending()
            else:
                self._try_pending_entry(instrument, low, high, close)

        if self._position != "NONE" or self._pending_side is not None:
            return

        warmup = self.cfg.swing_lookback * 3 + self.cfg.ob_search_bars + 5
        if idx < warmup:
            return

        atr_val = atr_percent(
            self._highs, self._lows, self._closes, self.cfg.atr_period, idx
        )
        regime = volatility_regime(atr_val, self.cfg.min_atr_pct, self.cfg.max_atr_pct)
        if regime != "active":
            return

        if self._last_swing_low > 0 and detect_bullish_sweep(
            low, close, self._last_swing_low, self.cfg.sweep_buffer_pct
        ):
            ob = find_bullish_order_block(
                self._opens,
                self._highs,
                self._lows,
                self._closes,
                idx,
                self.cfg.ob_search_bars,
            )
            if ob is not None and self._last_swing_high > self._last_swing_low:
                stop = min(low, self._last_swing_low) * (1.0 - self.cfg.sweep_buffer_pct)
                risk = close - stop
                if risk > 0:
                    target = close + risk * self.cfg.rr_ratio
                    self._pending_side = "LONG"
                    self._pending_ob_low = ob.low
                    self._pending_ob_high = ob.high
                    self._pending_stop = stop
                    self._pending_target = target
                    self._pending_expiry = idx + self.cfg.max_bars_after_sweep
            return

        if self._last_swing_high > 0 and detect_bearish_sweep(
            high, close, self._last_swing_high, self.cfg.sweep_buffer_pct
        ):
            ob = find_bearish_order_block(
                self._opens,
                self._highs,
                self._lows,
                self._closes,
                idx,
                self.cfg.ob_search_bars,
            )
            if ob is not None and self._last_swing_high > self._last_swing_low:
                stop = max(high, self._last_swing_high) * (1.0 + self.cfg.sweep_buffer_pct)
                risk = stop - close
                if risk > 0:
                    target = close - risk * self.cfg.rr_ratio
                    self._pending_side = "SHORT"
                    self._pending_ob_low = ob.low
                    self._pending_ob_high = ob.high
                    self._pending_stop = stop
                    self._pending_target = target
                    self._pending_expiry = idx + self.cfg.max_bars_after_sweep

    def _recent_structure_break(self, direction: str) -> bool:
        window = self._highs[-6:] if len(self._highs) >= 6 else self._highs
        if not window:
            return False
        if direction == "LONG":
            return self._closes[-1] > max(window[:-1]) if len(window) > 1 else True
        lows = self._lows[-6:] if len(self._lows) >= 6 else self._lows
        if not lows:
            return False
        return self._closes[-1] < min(lows[:-1]) if len(lows) > 1 else True

    def _try_pending_entry(
        self,
        instrument: Instrument,
        low: float,
        high: float,
        close: float,
    ) -> None:
        if self._pending_side == "LONG":
            touched_ob = price_in_zone(
                low, high, self._pending_ob_low, self._pending_ob_high
            )
            in_value = in_discount(
                close, self._range_low, self._range_high
            ) or self._range_high <= self._range_low
            choch_ok = self._recent_structure_break("LONG")
            if (touched_ob or choch_ok) and in_value:
                qty = Quantity(Decimal(self.cfg.trade_size), instrument.size_precision)
                self._submit(instrument.id, OrderSide.BUY, qty)
                self._position = "LONG"
                self._entry_price = close
                self._clear_pending()
        elif self._pending_side == "SHORT":
            touched_ob = price_in_zone(
                low, high, self._pending_ob_low, self._pending_ob_high
            )
            in_value = in_premium(
                close, self._range_low, self._range_high
            ) or self._range_high <= self._range_low
            choch_ok = self._recent_structure_break("SHORT")
            if (touched_ob or choch_ok) and in_value:
                qty = Quantity(Decimal(self.cfg.trade_size), instrument.size_precision)
                self._submit(instrument.id, OrderSide.SELL, qty)
                self._position = "SHORT"
                self._entry_price = close
                self._clear_pending()

    def _manage_open_position(
        self,
        instrument: Instrument,
        high: float,
        low: float,
        close: float,
    ) -> None:
        if self._position == "LONG":
            if low <= self._pending_stop or close <= self._pending_stop:
                self._close_open(instrument.id, OrderSide.SELL)
                self._position = "NONE"
                return
            if high >= self._pending_target or close >= self._pending_target:
                self._close_open(instrument.id, OrderSide.SELL)
                self._position = "NONE"
                return
            if self._last_swing_high > 0 and close < self._last_swing_low:
                self._close_open(instrument.id, OrderSide.SELL)
                self._position = "NONE"
        elif self._position == "SHORT":
            if high >= self._pending_stop or close >= self._pending_stop:
                self._close_open(instrument.id, OrderSide.BUY)
                self._position = "NONE"
                return
            if low <= self._pending_target or close <= self._pending_target:
                self._close_open(instrument.id, OrderSide.BUY)
                self._position = "NONE"
                return
            if self._last_swing_low > 0 and close > self._last_swing_high:
                self._close_open(instrument.id, OrderSide.BUY)
                self._position = "NONE"

    def _clear_pending(self) -> None:
        self._pending_side = None
        self._pending_ob_low = 0.0
        self._pending_ob_high = 0.0
        if self._position == "NONE":
            self._pending_stop = 0.0
            self._pending_target = 0.0
        self._pending_expiry = 0

    def _submit(
        self,
        instrument_id: InstrumentId,
        side: OrderSide,
        quantity: Quantity,
    ) -> None:
        order = self.order_factory.market(
            instrument_id=instrument_id,
            order_side=side,
            quantity=quantity,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

    def _close_open(self, instrument_id: InstrumentId, side: OrderSide) -> None:
        for position in self.cache.positions_open(instrument_id=instrument_id):
            self._submit(instrument_id, side, position.quantity)

    def on_stop(self) -> None:
        if self._instrument is not None:
            self.cancel_all_orders(self._instrument.id)
            self.close_all_positions(self._instrument.id)