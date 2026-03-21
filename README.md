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

### bull-put-spread-monitor

Monitors an existing bull put spread position and classifies its current health into one of five zones.

**Trigger phrases** — Claude will automatically use this skill when you say things like:
- "check my NVDA $155/$140 spread"
- "how is my put spread doing"
- "is my position safe"
- "should I be worried about my C spread"
- "check status of my bull put spread"

**What it does:**
1. Fetches current stock price and live option prices via `check_position.py` using Yahoo Finance
2. Calculates current P&L, cost-to-close, buffer to short strike, and % of max loss incurred
3. Classifies the position into one of five zones based on the worst signal (price or P&L)
4. Presents a structured status card + zone-appropriate action recommendation

**Zones:**

| Zone | Condition |
|---|---|
| 🟢 SAFE | Stock > 8% above short strike AND loss < 20% of max |
| 🟡 WATCH | 4–8% buffer OR 20–40% of max loss |
| 🟠 WARNING | 2–4% buffer OR 40–65% of max loss |
| 🔴 DANGER | 0–2% buffer OR 65–85% of max loss |
| 🚨 ACT NOW | Stock at/below short strike OR > 85% of max loss |

**Required inputs:** ticker, short strike, long strike, original net credit, expiry date

**Example output:**
```
╔══════════════════════════════════════════════╗
║  SPREAD MONITOR — NVDA                       ║
║  155/140 Put  ·  2026-05-01                  ║
╠══════════════════════════════════════════════╣
║  Status:  🟢 SAFE ZONE                       ║
╠══════════════════════════════════════════════╣
║  Stock now:     $172.70                      ║
║  Short strike:  $155.00  (buffer: 10.25%)    ║
║  Breakeven:     $153.02  (buffer: 11.40%)    ║
║  DTE remaining: 41 days                      ║
╠══════════════════════════════════════════════╣
║  Current P&L:   $0.00  per contract          ║
║  Loss % of max: 0.0%  of $1,302.00           ║
║  Cost to close: $1.98  per share             ║
╚══════════════════════════════════════════════╝
```

---

## Setup

### 1. Install dependencies and initialise

```bash
pip install yfinance pytz
bash setup.sh   # generates .claude/settings.json with the correct path for this machine
```

### 2. Configure the portfolio monitor

Run the setup script — it creates your local config files and prints instructions for each notification channel:

```bash
# macOS / Linux
bash setup_monitor.sh

# Windows
setup_monitor.bat
```

This copies `portfolio.example.json` → `portfolio.json` and `monitor_config.example.json` → `monitor_config.json` (both gitignored — your trades and credentials are never committed).

**`portfolio.json`** — add your open bull put spreads:

```json
[
  {
    "label": "NVDA May spread",
    "ticker": "NVDA",
    "short_strike": 155,
    "long_strike": 140,
    "net_credit": 1.98,
    "expiry": "2026-05-01",
    "contracts": 1
  }
]
```

**`monitor_config.json`** — enable and configure notification channels:

| Channel | What you need |
|---|---|
| `macos` | Nothing — works out of the box on macOS |
| `email` | Gmail app password (Google Account → Security → App Passwords) |
| `pushover` | $5 one-time Pushover app + free API account at pushover.net |

For SMS via email: set `to` to your carrier's email-to-SMS gateway (e.g. `5551234567@vtext.com` for Verizon).

### 3. Run the monitor

```bash
# Alert mode — notifies only WATCH zone or worse
claude -p "$(cat <<'EOF'
Read portfolio.json and check each bull put spread position.
For each position run:
  python3 check_position.py TICKER SHORT_STRIKE LONG_STRIKE NET_CREDIT EXPIRY

The check_position.py script is at:
  .claude/local-marketplace/plugins/bull-put-spread-monitor/skills/bull-put-spread-monitor/check_position.py

Classify each into a zone:
  SAFE: buffer > 8% AND loss < 20%
  WATCH: buffer 4-8% OR loss 20-40%
  WARNING: buffer 2-4% OR loss 40-65%
  DANGER: buffer 0-2% OR loss 65-85%
  ACT NOW: buffer <= 0 OR loss > 85%

Collect all results into a JSON array with fields:
  label, ticker, zone, stock_price, buffer_pct, pnl_per_contract, loss_pct_of_max, dte, cost_to_close

Then run:
  python3 notify.py --mode alert --results '<the JSON array>'

IMPORTANT: Do NOT read monitor_config.json — the notification script handles credentials internally.
EOF
)" --allowedTools Bash,Read

# Summary mode — full daily summary of all positions
claude -p "$(cat <<'EOF'
Read portfolio.json and check each bull put spread position.
For each position run:
  python3 check_position.py TICKER SHORT_STRIKE LONG_STRIKE NET_CREDIT EXPIRY

The check_position.py script is at:
  .claude/local-marketplace/plugins/bull-put-spread-monitor/skills/bull-put-spread-monitor/check_position.py

Classify each into a zone:
  SAFE: buffer > 8% AND loss < 20%
  WATCH: buffer 4-8% OR loss 20-40%
  WARNING: buffer 2-4% OR loss 40-65%
  DANGER: buffer 0-2% OR loss 65-85%
  ACT NOW: buffer <= 0 OR loss > 85%

Collect all results into a JSON array with fields:
  label, ticker, zone, stock_price, buffer_pct, pnl_per_contract, loss_pct_of_max, dte, cost_to_close

Then run:
  python3 notify.py --mode summary --results '<the JSON array>'

IMPORTANT: Do NOT read monitor_config.json — the notification script handles credentials internally.
EOF
)" --allowedTools Bash,Read
```

### 4. Schedule it (optional)

The commands above can be scheduled to run automatically. Run them from the project root directory.

**macOS — launchd (runs even when terminal is closed)**

Create `~/Library/LaunchAgents/com.options-monitor.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.options-monitor</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>cd /ABSOLUTE/PATH/TO/options-skill-pack && claude -p "Read portfolio.json, run check_position.py for each position, classify zones, then run: python3 notify.py --mode alert --results JSON. Do NOT read monitor_config.json." --allowedTools Bash,Read</string>
  </array>

  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
  </array>

  <key>StandardOutPath</key><string>/tmp/options-monitor.log</string>
  <key>StandardErrorPath</key><string>/tmp/options-monitor.log</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
```

Replace `/ABSOLUTE/PATH/TO/options-skill-pack` with your actual path, then:

```bash
launchctl load ~/Library/LaunchAgents/com.options-monitor.plist

# Test immediately (without waiting for scheduled time):
launchctl start com.options-monitor

# Remove:
launchctl unload ~/Library/LaunchAgents/com.options-monitor.plist
```

**Windows — Task Scheduler**

1. Open Task Scheduler → Create Basic Task
2. Trigger: Daily, repeat every day at 9:30 AM (add a second task for 3:00 PM)
3. Action: Start a program
   - Program: `cmd.exe`
   - Arguments: `/c cd /d C:\path\to\options-skill-pack && claude -p "Read portfolio.json, run check_position.py for each position, classify zones, then run: python3 notify.py --mode alert --results JSON. Do NOT read monitor_config.json." --allowedTools Bash,Read`
4. Set "Start in" to your project folder path

---

## Project structure

```
options-skill-pack/
├── setup.sh                                      # one-time Claude Code setup (skills path)
├── setup_monitor.sh                              # first-time monitor setup (macOS/Linux)
├── setup_monitor.bat                             # first-time monitor setup (Windows)
├── notify.py                                     # notification sender (credentials stay in-process)
├── portfolio.example.json                        # template — copied to portfolio.json by setup_monitor
├── monitor_config.example.json                   # template — copied to monitor_config.json by setup_monitor
├── portfolio.json                                # your positions — gitignored, never committed
├── monitor_config.json                           # your notification credentials — gitignored
├── monitor.log                                   # run log — gitignored
└── .claude/
    ├── settings.json                             # activates skills for this project
    └── local-marketplace/
        ├── .claude-plugin/
        │   └── marketplace.json                  # local marketplace registry
        └── plugins/
            ├── bull-put-spread-selector/
            │   ├── .claude-plugin/
            │   │   └── plugin.json               # plugin manifest
            │   └── skills/
            │       └── bull-put-spread-selector/
            │           ├── SKILL.md              # skill instructions
            │           ├── fetch_chain.py        # yfinance option chain fetcher
            │           └── evals/
            │               └── evals.json        # test cases & assertions
            └── bull-put-spread-monitor/
                ├── .claude-plugin/
                │   └── plugin.json               # plugin manifest
                └── skills/
                    └── bull-put-spread-monitor/
                        ├── SKILL.md              # skill instructions
                        ├── check_position.py     # yfinance position checker
                        └── evals/
                            └── evals.json        # test cases & assertions
```

---

## Evals

### bull-put-spread-selector — 3 test cases

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

### bull-put-spread-monitor — 3 test cases

| Eval | Tests |
|---|---|
| `nvda-safe-zone` | SAFE ZONE classification, live P&L, buffer%, theta guidance |
| `c-earnings-risk` | Earnings event flagging within expiry window, action plan |
| `aapl-safe-zone` | Large buffer, profit-already-accrued P&L display |

**Benchmark results (iteration 1):**

| | with_skill | without_skill |
|---|---|---|
| Pass rate | **100%** | 50% |
| Avg time | 70.7s | 100.7s |

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
