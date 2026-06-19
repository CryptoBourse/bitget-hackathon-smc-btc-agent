# Bitget Hackathon S1 — Audit Request

Use this document to ask Claude (or another AI reviewer) to verify our submission.

## Official references

- Hackathon rules: https://bitget-ai.gitbook.io/hackathon
- Submission form: https://forms.gle/CEGB6fRtuobD3bCj8
- Deadline: June 25, 2026 (UTC+8)
- GetAgent skill: https://www.npmjs.com/package/@bitget-ai/getagent-skill (v0.3.3)

## Project links

| Item | Value |
|------|-------|
| GitHub (public) | https://github.com/CryptoBourse/bitget-hackathon-smc-btc-agent |
| Playbook name | `smc-btc-agent-m15` |
| Strategy ID | `7cbc53a3-4e7c-441c-96d5-02127459b9dd` |
| Submission version | `0.0.4` (BTC, cloud-window tuned) |
| Bitget UID | `7365246417` |
| Track | Trading Agent |

## Thesis (summary)

Autonomous SMC agent on BTCUSDT M15. The agent runs a perceive → decide → execute loop:
volatility filter (ATR), swing structure, liquidity sweep, order-block retest, R:R exits.
Published on GetAgent Playbook with `follow_trade` paper trading support.

## Honest context (do not ignore)

1. Versions 0.0.1–0.0.4 remain on server; delete API returns 403.
2. Cloud card ROI ~0.01% (official Nautilus ~1000 M15 bars). Local optimized sims are higher but NOT shown on Bitget card.
3. `evidence/paper_trading_log.csv` may be sparse if paper instance was disabled.
4. README was rewritten in English for GitHub; GetAgent `validate.py` may fail on missing Chinese sections (策略, 开仓, 平仓, 风险).
5. No further publish/enable without explicit user approval.

## Files to review in repo

- `README.md` — project overview
- `manifest.yaml` — Playbook config
- `backtest.yaml` — Nautilus replay spec
- `src/main.py`, `src/strategy.py`, `src/perception.py`, `src/smc.py`
- `evidence/playbook_publish.json`
- `evidence/paper_trading_log.csv`
- `evidence/backtest_multi_asset_review.json`
- `evidence/optimize_cloud_window.json`

## Review prompt (paste below into Claude)

```
You are an independent reviewer for Bitget AI Hackathon S1 (Trading Agent track).

Audit our submission and say if we did things "normally" per official Bitget rules —
not per our optimistic local backtests.

References:
- https://bitget-ai.gitbook.io/hackathon
- Repo: https://github.com/CryptoBourse/bitget-hackathon-smc-btc-agent
- Playbook: smc-btc-agent-m15 v0.0.4, strategy_id 7cbc53a3-4e7c-441c-96d5-02127459b9dd
- UID: 7365246417

Tasks:
1) Check hackathon compliance (required vs optional materials)
2) Check consistency: repo ↔ Playbook ↔ evidence
3) Check technical credibility (no unrealistic ROI claims)
4) List disqualification risks
5) List top priority fixes before June 25
6) Verdict: READY / ALMOST READY / NOT READY

Response format:
A) Scorecard table (OK / PARTIAL / MISSING)
B) Top 5 jury risks
C) Top 5 concrete actions (priority order + effort)
D) Final verdict in 3 lines

Explicit checks:
- Local vs cloud backtest gap (card ROI ~0.01%)
- paper_trading_log.csv real content
- GetAgent validate.py README requirements
- Public links without login
- Clear thesis (not feature list only)
- BTC v0.0.4 consistency vs old ETH traces

Be strict, factual, and actionable.
```