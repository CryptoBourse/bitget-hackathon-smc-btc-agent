# SMC Gold M15 — Archive v0.1.0 (original)

Restauration du **premier Playbook** du projet hackathon Bitget : stratégie SMC sur **XAUUSDT** (or tokenisé), timeframe **M15**.

> Ce dossier est une archive figée. Le projet actif (BTC) reste à la racine du repo.

## 策略 / Strategy

L'or chasse souvent la liquidité au-delà des swing highs/lows avant de revenir. Ce Playbook automatise un workflow SMC classique :

1. **Structure** — swing highs et swing lows confirmés
2. **Liquidity sweep** — mèche au-delà d'un extrême, clôture à l'intérieur du range
3. **Order block** — dernière bougie opposée avant le mouvement impulsif
4. **Value filter** — longs en discount, shorts en premium (équilibre du dealing range)
5. **Entry** — retest de l'order block après change of character (CHoCH)
6. **Exit** — stop au-delà du sweep, take profit au multiple R:R, sortie structurelle

## 开仓 / Entry

- **Long** : sweep haussier du swing low → retest du bullish order block en discount
- **Short** : sweep baissier du swing high → retest du bearish order block en premium

## 平仓 / Exit

- Stop loss au-delà de l'extrême du sweep
- Take profit au multiple reward-to-risk configuré
- Sortie anticipée si la structure de marché se retourne contre la position

## 风险 / Risk

- Sweeps peu profonds en session calme → faux signaux
- Spikes macro → stop avant le retest
- Ranges qui se chevauchent → whipsaws répétés
- Backtest ≠ live : slippage et frais réduisent l'edge

---

## Thesis / Explication complète SMC

Texte officiel (`manifest.yaml` → `long_description`) :

This Playbook trades tokenized gold perpetual futures using Smart Money Concepts on a medium-term intraday timeframe. The thesis is that gold frequently hunts resting liquidity beyond obvious swing extremes before reversing toward institutional order blocks. Rather than chasing breakouts blindly, the strategy waits for a liquidity sweep, a shift in market structure, and a disciplined retest inside a favorable value zone before committing capital. It is built for subscribers who want a rules-based SMC workflow instead of discretionary chart reading.

**Entries** begin after price sweeps a recent swing extreme and closes back inside the prior range, signaling a stop-run rather than a true breakout. The Playbook then looks for a change of character in the direction of the intended reversal and waits for price to retest the last opposing order block while price remains in discount for longs or premium for shorts. Only when structure, liquidity, and value alignment agree does it enter long or enter short with a directional position.

**Exits** are managed with a fixed reward-to-risk framework plus structural invalidation. If price violates the sweep extreme again, the trade is closed as a failed setup. If price reaches the projected target derived from the initial risk budget, the position is closed to bank gains. An additional structure-based exit closes the trade when market character flips against the open position, preventing a winner from turning into a full reversal loss.

**Tuning** — subscribers may tune how aggressively the model labels liquidity sweeps, how far it searches for order blocks, the reward multiple applied to each setup, position size, leverage, and margin budget. Tighter sweep sensitivity produces fewer but cleaner signals, while wider sensitivity increases trade count at the cost of noisier entries. A higher reward multiple stretches profit targets and can reduce hit rate, while a lower multiple banks gains sooner.

**Limitations** — the strategy underperforms in low-volatility sessions where sweeps are shallow and order blocks are repeatedly violated without follow-through. Fast news-driven spikes around macro releases can also stop out valid structural setups before the retest completes. Choppy overlapping ranges on gold can create repeated false sweeps and whipsaw losses. Past backtest performance is not a guarantee of live profitability.

---

## Paramètres par défaut (v0.1.0)

| Paramètre | Valeur | Effet |
|-----------|--------|-------|
| `trading_symbols` | `XAUUSDT` | Or tokenisé Bitget RWA |
| `bar_interval` | `15m` | Bougies 15 minutes |
| `swing_lookback` | `5` | Structure plus lente = moins de swings |
| `sweep_buffer_pct` | `0.0008` | Sensibilité au sweep de liquidité |
| `ob_search_bars` | `8` | Profondeur de recherche des order blocks |
| `rr_ratio` | `2.0` | Take profit = 2× le risque initial |
| `max_bars_after_sweep` | `12` | Expiration du setup en attente |
| `trade_size` | `0.05` | Taille de position |
| `margin_budget` | `200` USDT | Capital cap pour sizing et ROI |
| `leverage` | `3` | Amplifie PnL et drawdown |

## Structure du package

```text
archive/smc-gold-m15-v0.1/
├── README.md          ← ce fichier (explication SMC)
├── manifest.yaml      ← long_description officielle + config Playbook
├── backtest.yaml      ← spec Nautilus backtest XAUUSDT
└── src/
    ├── main.py        ← point d'entrée GetAgent
    ├── strategy.py    ← SmcGoldStrategy (logique SMC)
    └── smc.py         ← helpers structure / sweep / order block
```

## Validation locale

```bash
python C:\Users\USER\.cursor\skills\getagent\scripts\validate.py C:\Users\USER\bitget-hackathon-smc-gold\archive\smc-gold-m15-v0.1
```

## Historique

| Date | Événement |
|------|-----------|
| 2026-06-19 ~10:24 | Création originale `smc-gold-m15` sur XAUUSDT |
| 2026-06-19 ~13:55 | Pivot vers `smc-btc-agent-m15` (BTC/ETH) |
| 2026-06-19 | Archive restaurée depuis snapshots + tar.gz |

**Strategy ID original (cloud)** : `871bb062-e31c-43ca-bb6b-e77ec3e9dcd9`