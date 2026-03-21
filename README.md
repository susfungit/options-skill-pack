# options-skill-pack

A collection of Claude Code skills for options trading strategy. Skills are scoped to this project — they activate automatically when Claude Code is launched from this directory.

---

## Skills

### bull-put-spread-selector

Identifies the optimal short put and long put strikes for a bull put spread on any stock ticker.

**Trigger phrases** — Claude will automatically use this skill when you say things like:
- "bull put spread on AAPL"
- "find me a put spread on TSLA"
- "sell a 20-delta put on NVDA"
- "what strikes for my spread on AMD"
- "set up a credit spread on SPY"

**What it does:**
1. Fetches live option chain data (price, strikes, bid/ask, IV, delta) via `fetch_chain.py` using Yahoo Finance
2. Supplements with web search for earnings dates, IV Rank, and price trend
3. Locates the target expiry (35–45 DTE by default)
4. Selects the short put strike near 20Δ and long put 10% below
5. Calculates max profit, max loss, breakeven, PoP, and return on risk
6. Runs a risk checklist (earnings, IV rank, trend, dividends, spread width)
7. Presents a structured trade card + prose rationale
8. Offers to plot an interactive P&L curve

**Parameters** (defaults shown):

| Parameter | Default | Example override |
|---|---|---|
| Expiry | 35–45 DTE | "30 DTE", "May 16 expiry" |
| Short put delta | 20Δ | "sell a 15-delta put" |
| Spread width | Long put = 10% below short | — |
| Contracts | 1 | "5 contracts" |

**Example output:**
```
╔══════════════════════════════════════════╗
║  BULL PUT SPREAD — AAPL                  ║
║  Expiry: Apr 24, 2026  ·  DTE: 36 days  ║
╠══════════════════════════════════════════╣
║  SELL  $224 Put   @ $1.78 (est.)        ║
║  BUY   $200 Put   @ $0.62 (est.)        ║
║  Net credit:  $1.16  per share          ║
╠══════════════════════════════════════════╣
║  Max profit:  $116  per contract        ║
║  Max loss:    $2,284  per contract      ║
║  Breakeven:   $222.84                   ║
║  Prob. profit: ~80%                     ║
║  Return/risk:  5.1%                     ║
╚══════════════════════════════════════════╝
```

---

## Setup

```bash
# 1. Install Python dependencies
pip install yfinance pytz

# 2. Generate .claude/settings.json with the correct absolute path for this machine
bash setup.sh
```

`setup.sh` must be run once after cloning — it writes the marketplace path into `.claude/settings.json` so Claude Code can locate the skill.

---

## Project structure

```
options-skill-pack/
├── setup.sh                                      # one-time setup script
└── .claude/
    ├── settings.json                             # activates skills for this project
    └── local-marketplace/
        ├── .claude-plugin/
        │   └── marketplace.json                  # local marketplace registry
        └── plugins/
            └── bull-put-spread-selector/
                ├── .claude-plugin/
                │   └── plugin.json               # plugin manifest
                └── skills/
                    └── bull-put-spread-selector/
                        ├── SKILL.md              # skill instructions
                        ├── fetch_chain.py        # yfinance option chain fetcher
                        └── evals/
                            └── evals.json        # test cases & assertions
```

---

## Evals

The skill ships with 3 test cases covering:

| Eval | Tests |
|---|---|
| `standard-aapl` | Default parameters, 20Δ, 35–45 DTE, earnings detection |
| `custom-delta-nvda` | 15Δ override, adjusted OTM%, ~85% PoP |
| `risk-flags-tsla` | Low IV rank warning, earnings-straddling expiry avoidance |

**Benchmark results (iteration 1):**

| | with_skill | without_skill |
|---|---|---|
| Pass rate | **100%** | 44% |
| Avg time | 119.6s | 129.3s |

---

## Adding more skills

To add a new skill to this pack:

1. Create the skill folder:
   ```
   .claude/local-marketplace/plugins/<skill-name>/
   ├── .claude-plugin/plugin.json
   └── skills/<skill-name>/SKILL.md
   ```

2. Register it in `.claude/local-marketplace/.claude-plugin/marketplace.json`

3. Install it:
   ```bash
   claude plugin install <skill-name>@options-skill-pack --scope project
   ```
