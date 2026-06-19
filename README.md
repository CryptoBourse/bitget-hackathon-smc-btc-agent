# SMC ETH Agent M15 — Bitget AI Hackathon S1

Autonomous Smart Money Concepts trading agent for **ETHUSDT** perpetual on **15-minute** bars.

**Published Playbook:** `smc-btc-agent-m15` (display: SMC ETH Agent M15)  
**Strategy ID:** `7cbc53a3-4e7c-441c-96d5-02127459b9dd`  
**Paper trading:** `follow_trade` on ETH, cron `*/15 * * * *` (Asia/Shanghai)

## 策略 / Strategy

ETH often runs liquidity beyond swing highs or lows before reversing. This agent automates a perceive-decide-execute SMC workflow:

1. **Structure** — track confirmed swing highs and swing lows
2. **Liquidity sweep** — wick beyond a swing extreme, close back inside range
3. **Order block** — last opposing candle before the impulsive move
4. **Value filter** — longs prefer discount, shorts prefer premium (dealing range equilibrium)
5. **Entry** — retest of the order block after change of character
6. **Exit** — stop beyond sweep, take profit at reward-to-risk multiple, structure invalidation

## 开仓 / Entry

- **Long**: bullish sweep of swing low → retest bullish order block in discount
- **Short**: bearish sweep of swing high → retest bearish order block in premium

## 平仓 / Exit

- Stop loss beyond the sweep extreme
- Take profit at configured reward-to-risk multiple
- Early exit if market structure flips against the position

## Parameters

| Parameter | Effect |
|-----------|--------|
| `swing_lookback` | Wider = slower structure, fewer swings |
| `sweep_buffer_pct` | Higher = more sweep signals (noisier) |
| `ob_search_bars` | How far back to search for order blocks |
| `rr_ratio` | Profit target as multiple of initial risk |
| `margin_budget` | Capital cap for sizing and return % |
| `leverage` | Amplifies PnL and drawdown |

## 风险 / Risk

- Shallow sweeps in quiet sessions → false signals
- Macro news spikes → stops before retest
- Overlapping ranges → repeated whipsaws
- Backtest ≠ live: slippage and fees reduce edge

## Hackathon evidence (in `evidence/`)

| File | Description |
|------|-------------|
| `playbook_publish.json` | Published Playbook metadata + cloud backtest metrics |
| `optimize_smc_results.json` | Grid-search optimization (BTC/ETH/SOL) |
| `backtest_btc_2y_*` | Extended local BTC backtest (Bitget public API) |
| `backtest_extended_*` | Supplementary XAU backtest |
| `paper_trading_log.csv` | Paper trading log (updates as agent runs) |

Official cloud backtest: 48 trades, WR 54.2%, PF 4.06, DD 4.8% (~1000 M15 bars).

Reproduce extended backtests:

```bash
python scripts/backtest_extended.py
python scripts/backtest_btc_2y.py
python scripts/optimize_smc.py
```

## Local validation

```bash
python C:\Users\USER\.cursor\skills\getagent\scripts\validate.py C:\Users\USER\bitget-hackathon-smc-gold
```

## Upload & backtest (requires Playbook API key)

Use your Bitget Playbook `ACCESS-KEY` only in the terminal session — never commit it.

```bash
# From project root after validation passes
# Follow references/api/upload.md in the getagent skill
```

## Hackathon track

**Trading Agent** — autonomous SMC BTC agent with perception layer, backtest + paper trading.

- Symbol: `BTCUSDT` (Bitget USDT perpetual)
- Timeframe: M15
- Bitget UID: `7365246417`

## Project structure

```text
bitget-hackathon-smc-gold/
├── README.md
├── manifest.yaml
├── backtest.yaml
└── src/
    ├── main.py
    ├── strategy.py
    ├── smc.py
    └── perception.py
├── scripts/
│   ├── optimize_smc.py
│   ├── backtest_btc_2y.py
│   └── backtest_extended.py
└── evidence/
```