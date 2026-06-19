# SMC BTC Agent M15 — Bitget AI Hackathon S1

Autonomous Smart Money Concepts trading agent for **BTCUSDT** perpetual on **15-minute** bars.

| Item | Value |
|------|-------|
| **Track** | Trading Agent |
| **Playbook** | `smc-btc-agent-m15` |
| **Published version (submit this)** | `0.0.6` (full SMC thesis in Strategy details) |
| **Package version (`manifest.yaml`)** | `0.2.0` (local semver — not the cloud publish tag) |
| **Strategy ID** | `7cbc53a3-4e7c-441c-96d5-02127459b9dd` |
| **Bitget UID** | `7365246417` |
| **Schedule** | `*/15 * * * *` (Asia/Shanghai) |
| **Playbook hub** | [Bitget GetAgent Playbook](https://www.bitget.com/activity/ai-get-agent/playbook) — search `smc-btc-agent-m15` or Strategy ID |

> **Version note:** GetAgent assigns publish tags (`0.0.1`–`0.0.6`). `manifest.yaml` `version: 0.2.0` is the local package revision only. **Submit v0.0.6** in the hackathon form.

## Thesis

This Playbook trades tokenized gold perpetual futures using Smart Money Concepts on a medium-term intraday timeframe. The thesis is that gold frequently hunts resting liquidity beyond obvious swing extremes before reversing toward institutional order blocks. Rather than chasing breakouts blindly, the strategy waits for a liquidity sweep, a shift in market structure, and a disciplined retest inside a favorable value zone before committing capital. It is built for subscribers who want a rules-based SMC workflow instead of discretionary chart reading.

**Entries** begin after price sweeps a recent swing extreme and closes back inside the prior range, signaling a stop-run rather than a true breakout. The Playbook then looks for a change of character in the direction of the intended reversal and waits for price to retest the last opposing order block while price remains in discount for longs or premium for shorts. Only when structure, liquidity, and value alignment agree does it enter long or enter short with a directional position.

**Exits** are managed with a fixed reward-to-risk framework plus structural invalidation. If price violates the sweep extreme again, the trade is closed as a failed setup. If price reaches the projected target derived from the initial risk budget, the position is closed to bank gains. An additional structure-based exit closes the trade when market character flips against the open position, preventing a winner from turning into a full reversal loss.

**Tuning** — subscribers may tune how aggressively the model labels liquidity sweeps, how far it searches for order blocks, the reward multiple applied to each setup, position size, leverage, and margin budget. Tighter sweep sensitivity produces fewer but cleaner signals, while wider sensitivity increases trade count at the cost of noisier entries. A higher reward multiple stretches profit targets and can reduce hit rate, while a lower multiple banks gains sooner.

**Multi-asset validation** — the same SMC framework has been backtested on **BTCUSDT**, **ETHUSDT**, and **SOLUSDT** USDT perpetual futures in addition to tokenized gold. Reproducible scripts (`scripts/optimize_smc.py`, `scripts/compare_assets.py`) confirm trades across all four markets. Select one pair at a time via Custom configuration.

**Limitations** — the strategy underperforms in low-volatility sessions where sweeps are shallow and order blocks are repeatedly violated without follow-through. Fast news-driven spikes around macro releases can also stop out valid structural setups before the retest completes. Choppy overlapping ranges on gold can create repeated false sweeps and whipsaw losses. Past backtest performance is not a guarantee of live profitability.

Cloud card ROI reflects the official GetAgent Nautilus replay (~1000 M15 bars), not extended local simulations. **Submission asset is BTCUSDT v0.0.6**; class names (`SmcGoldStrategy`) and folder name (`smc-gold`) reflect the original XAU SMC prototype.

## 策略 / Strategy

BTC M15 Smart Money Concepts agent: structure → liquidity sweep → order block retest → rule-based execution.

## 开仓 / Entry

- **Long:** bullish sweep of swing low → retest bullish order block in discount
- **Short:** bearish sweep of swing high → retest bearish order block in premium

## 平仓 / Exit

- Stop beyond the sweep extreme
- Take profit at configured reward-to-risk multiple
- Early exit on structure invalidation

## 风险 / Risk

- Quiet sessions and news spikes → false sweeps or missed retests
- Cloud card ROI (~0.01%) ≠ extended local backtests
- Paper trading log must show real executed signals before final submission
- Slippage and fees reduce edge in live execution

## Quick start (local)

**Requirements:** Python 3.11+

```bash
# Clone and enter project
git clone https://github.com/CryptoBourse/bitget-hackathon-smc-btc-agent.git
cd bitget-hackathon-smc-btc-agent

# Validate Playbook package (getagent skill v0.3.3)
python C:\Users\USER\AppData\Roaming\npm\node_modules\@bitget-ai\getagent-skill\skills\getagent\scripts\validate.py .
```

Reproduce supplementary backtests (optional evidence):

```bash
python scripts/backtest_extended.py      # XAU extended
python scripts/backtest_btc_2y.py        # BTC long window
python scripts/optimize_smc.py           # grid-search BTC/ETH/SOL
python scripts/compare_assets.py         # fair default-params comparison
```

## Official cloud metrics (v0.0.6 publish)

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