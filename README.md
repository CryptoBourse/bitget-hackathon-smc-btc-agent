# SMC BTC Agent M15 — Bitget AI Hackathon S1

Autonomous Smart Money Concepts trading agent for **BTCUSDT** perpetual on **15-minute** bars.

| Item | Value |
|------|-------|
| **Track** | Trading Agent |
| **Playbook** | `smc-btc-agent-m15` |
| **Submission version** | `0.0.4` (BTC, cloud-window tuned) |
| **Strategy ID** | `7cbc53a3-4e7c-441c-96d5-02127459b9dd` |
| **Bitget UID** | `7365246417` |
| **Schedule** | `*/15 * * * *` (Asia/Shanghai) |

## Thesis

BTC often runs liquidity beyond swing highs or lows before reversing. This agent automates a full **perceive → decide → execute** loop without discretionary chart reading:

1. **Perception** — volatility regime (ATR filter) + swing structure (premium/discount)
2. **Liquidity sweep** — wick beyond a swing extreme, close back inside range
3. **Order block** — last opposing candle before the impulsive move
4. **Value filter** — longs in discount, shorts in premium
5. **Entry** — order-block retest after change of character
6. **Exit** — stop beyond sweep, R:R target, structure invalidation

Past performance is not a guarantee of live profitability. Cloud card ROI reflects the official GetAgent Nautilus replay (~1000 M15 bars), not extended local simulations.

## Quick start (local)

**Requirements:** Python 3.11+

```bash
# Clone and enter project
git clone https://github.com/CryptoBourse/bitget-hackathon-smc-btc-agent.git
cd bitget-hackathon-smc-btc-agent

# Validate Playbook package (getagent skill)
python path/to/getagent/scripts/validate.py .
```

Reproduce supplementary backtests (optional evidence):

```bash
python scripts/backtest_extended.py      # XAU extended
python scripts/backtest_btc_2y.py        # BTC long window
python scripts/optimize_smc.py           # grid-search BTC/ETH/SOL
python scripts/compare_assets.py         # fair default-params comparison
```

## Official cloud metrics (v0.0.4 publish)

| Metric | Value |
|--------|-------|
| ROI (strategy basis) | ~0.01% |
| Win rate | ~56.5% |
| Profit factor | ~3.82 |
| Trades | 46 |
| Max drawdown | ~4.3% |
| Margin budget | 100 USDT |

> Local optimized simulations (e.g. +18% on cloud-window grid search) use a simplified Python replay and **do not** match the official Nautilus card. See `evidence/backtest_multi_asset_review.json`.

## Hackathon evidence (`evidence/`)

| File | Description |
|------|-------------|
| `playbook_publish.json` | Published Playbook metadata + cloud metrics |
| `optimize_cloud_window.json` | Cloud-window param search (local reference) |
| `optimize_smc_results.json` | Long-window grid-search (BTC/ETH/SOL) |
| `backtest_multi_asset_review.json` | Honest multi-asset summary for judges |
| `backtest_btc_2y_*` | Extended BTC backtest (Bitget public API) |
| `backtest_extended_*` | Supplementary XAU backtest |
| `paper_trading_log.csv` | Paper trading log |

## Upload & paper trading (Playbook API)

Use your Bitget Playbook `ACCESS-KEY` only in the terminal session — **never commit it**.

Follow the [GetAgent skill](https://www.npmjs.com/package/@bitget-ai/getagent-skill) workflow: validate → upload → cloud backtest → publish → enable `follow_trade`.

## Project structure

```text
bitget-hackathon-smc-gold/
├── manifest.yaml
├── backtest.yaml
├── src/
│   ├── main.py
│   ├── strategy.py
│   ├── smc.py
│   └── perception.py
├── scripts/
│   ├── optimize_smc.py
│   ├── optimize_cloud_window.py
│   ├── compare_assets.py
│   ├── backtest_btc_2y.py
│   └── backtest_extended.py
└── evidence/
```

## License

Submitted for Bitget AI Base Camp Hackathon S1. Strategy code for evaluation and reproduction by judges.