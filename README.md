# options-skill-pack

Options trading toolkit — 7 skills for Claude Code + a self-hosted web chat app with portfolio management. Find spreads, monitor positions, evaluate rolls, and track your portfolio with AI-powered analysis.

**Two ways to use:**
- **Claude Code** — skills activate automatically in this project directory
- **Web App** — chat UI + portfolio dashboard, run locally with your own Claude API key

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

### iron-condor-selector

Identifies the optimal strikes for an iron condor (sell put + buy put + sell call + buy call) for any stock.

**Trigger phrases** — Claude will automatically use this skill when you say things like:
- "iron condor on AAPL"
- "neutral options trade on SPY"
- "range-bound strategy on NVDA"
- "sell premium on both sides of TSLA"
- "set up an iron condor with 20-delta strikes"

**What it does:**
1. Fetches live option chain data for both puts and calls via `fetch_iron_condor.py`
2. Supplements with web search for earnings dates and IV Rank
3. Selects short put and short call at 16Δ (default), long wings 10% beyond
4. Calculates total credit, max profit, max loss, profit zone, PoP, and return on risk
5. Runs a risk checklist (earnings, IV rank, trend, dividends, put/call skew)
6. Presents a structured trade card + prose rationale

**Parameters** (defaults shown):

| Parameter | Default | Example override |
|---|---|---|
| Expiry | 35–45 DTE | "30 DTE", "May 16 expiry" |
| Short strike delta | 16Δ each side | "20-delta short strikes" |
| Wing width | 10% beyond short strikes | — |
| Contracts | 1 | "5 contracts" |

**Example output:**
```
╔══════════════════════════════════════════════════════╗
║  IRON CONDOR — AAPL                                  ║
║  Expiry: 2026-05-01  ·  DTE: 41 days                ║
╠══════════════════════════════════════════════════════╣
║  PUT SIDE:                                           ║
║    SELL  $220 Put   @ $2.79 (est.)                   ║
║    BUY   $200 Put   @ $1.15 (est.)                   ║
║    Credit: $1.64  ·  Width: $20                      ║
╠══════════════════════════════════════════════════════╣
║  CALL SIDE:                                          ║
║    SELL  $275 Call  @ $1.43 (est.)                    ║
║    BUY   $300 Call  @ $0.21 (est.)                    ║
║    Credit: $1.22  ·  Width: $25                      ║
╠══════════════════════════════════════════════════════╣
║  Total credit:   $2.86  per share                    ║
║  Max profit:     $286  per contract                  ║
║  Max loss:       $2,214  per contract                ║
║  Profit zone:    $217.14 – $277.86                   ║
║  Prob. profit:   ~71%                                ║
║  Return/risk:    12.9%                               ║
╚══════════════════════════════════════════════════════╝
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

### iron-condor-monitor

Monitors an existing iron condor position and classifies its health into one of five zones. Uses **two-sided buffer logic** — the worse side (put or call) determines the zone.

**Trigger phrases:**
- "check my AAPL iron condor"
- "how is my condor doing"
- "is my iron condor safe"
- "is my SPY condor in trouble"

**What it does:**
1. Fetches current stock price and option prices for all 4 legs via `check_iron_condor.py`
2. Calculates put buffer (above short put) and call buffer (below short call)
3. Uses the **worse buffer** + loss% to classify zone
4. Presents a two-sided status card + zone-appropriate guidance

**Example output:**
```
╔═══════════════════════════════════════════════════════╗
║  IRON CONDOR MONITOR — NVDA                           ║
║  155/140 · 195/215  ·  2026-05-01                     ║
╠═══════════════════════════════════════════════════════╣
║  Status:  🟢 SAFE ZONE                                ║
╠═══════════════════════════════════════════════════════╣
║  Stock now:        $172.70                             ║
║  Put buffer:       10.25% above $155                   ║
║  Call buffer:      12.91% below $195                   ║
║  Worst buffer:     10.25% (put side)                   ║
║  DTE remaining:    41 days                             ║
╠═══════════════════════════════════════════════════════╣
║  Current P&L:      $0.00  per contract                 ║
║  Loss % of max:    0.0%  of $1,652.00                  ║
║  Cost to close:    $3.48  per share                    ║
║  Profit zone:      $151.52 – $198.48                   ║
╚═══════════════════════════════════════════════════════╝
```

---

### covered-call-selector

Identifies the optimal call strike to sell for a covered call on a given stock.

**Trigger phrases** — Claude will automatically use this skill when you say things like:
- "covered call on AAPL"
- "sell calls against my shares"
- "what call should I sell on NVDA"
- "write a call on MSFT"
- "generate income from my stock"
- "yield on my shares"

**What it does:**
1. Fetches live call option chain data via `fetch_covered_call.py` using Yahoo Finance
2. Supplements with web search for earnings dates, IV Rank, and ex-dividend dates
3. Selects the call strike near 30Δ (default) in the 30–45 DTE window
4. Calculates premium, static return, annualized return, downside protection, called-away return, breakeven
5. Runs a risk checklist (earnings, IV rank, ex-dividend, trend)
6. Presents a structured trade card + prose rationale
7. If cost basis provided, shows effective cost basis and called-away P&L

**Parameters** (defaults shown):

| Parameter | Default | Example override |
|---|---|---|
| Expiry | 30–45 DTE | "60 days out", "May expiry" |
| Short call delta | 30Δ | "sell a 15-delta call" |
| Contracts | 1 (100 shares) | "3 contracts" |
| Cost basis | *(optional)* | "I bought at $150" |

**Example output:**
```
╔══════════════════════════════════════════════════════╗
║  COVERED CALL — AAPL                                  ║
║  Expiry: Apr 24, 2026  ·  DTE: 34 days               ║
╠══════════════════════════════════════════════════════╣
║  SELL  $260 Call   @ $3.33                            ║
║  per 100 shares owned                                ║
╠══════════════════════════════════════════════════════╣
║  Premium:              $3.33 per share ($333 total)   ║
║  Static return:        1.34%                          ║
║  Annualized return:    14.4%                          ║
║  Downside protection:  1.34%                          ║
║  Called-away return:   6.19%                          ║
║  Breakeven:            $244.66                        ║
║  Prob. of assignment:  ~30%                           ║
╚══════════════════════════════════════════════════════╝
```

---

### spread-roller

Finds roll targets for bull put spreads and iron condors when a position needs to be rolled out or diagonally adjusted.

**Trigger phrases** — Claude will automatically use this skill when you say things like:
- "roll my NVDA put spread"
- "roll the put side of my iron condor"
- "find roll targets for my spread"
- "my spread is in danger, what can I do?"
- "should I roll or close?"
- "roll down and out"

**What it does:**
1. Prices the cost to close your current spread via `roll_spread.py` using Yahoo Finance
2. Scans 3 future expiries (~2, 4, and 6 weeks out from current expiry)
3. Evaluates 3 roll types per expiry: calendar (same strikes), defensive diagonal (1 strike further OTM), aggressive diagonal (reset to target delta)
4. Ranks all candidates by net roll credit (best first)
5. Presents a comparison card with close cost, roll candidates, and a recommendation
6. For iron condors, rolls one side at a time and flags asymmetry

**Parameters** (defaults shown):

| Parameter | Default | Example override |
|---|---|---|
| Target delta | 0.20 (put spread), 0.16 (condor) | "roll to 15-delta" |
| Roll side (condor) | — | "roll the put side" |

**Example output:**
```
╔════════════════════════════════════════════════════════════════╗
║  ROLL ANALYSIS — NVDA put spread                              ║
║  Current: 155/140 · Expiry 2026-05-01 · 41d remaining         ║
╠════════════════════════════════════════════════════════════════╣
║  Close now:  $1.98 debit  →  P&L: $0.00 (breakeven)           ║
╠════════════════════════════════════════════════════════════════╣
║  #  Type         Expiry      Strikes    Net Roll   PoP   RoR  ║
║  1  Def Diag     2026-06-18  154/138    +$1.37cr   74%   26%  ║
║  2  Calendar     2026-06-18  155/140    +$1.34cr   74%   28%  ║
║  3  Agg Diag     2026-06-18  146/130    +$0.53cr   81%   19%  ║
╚════════════════════════════════════════════════════════════════╝
```

---

### covered-call-monitor

Monitors an existing covered call position and classifies its health into one of five zones. Answers the key question: "will my shares get called away?"

**Trigger phrases:**
- "check my AAPL covered call"
- "how is my call doing"
- "will my shares get called away"
- "is my covered call safe"
- "covered call status"

**What it does:**
1. Fetches current stock price and call option price via `check_covered_call.py`
2. Calculates buffer to strike, call P&L, intrinsic/time value, current delta
3. Classifies zone based on buffer and call value relative to original credit
4. If cost basis provided: shows effective cost basis and called-away P&L
5. Presents a status card + zone-appropriate guidance

**Zones:**

| Zone | Condition |
|---|---|
| 🟢 SAFE | Stock > 8% below strike AND call value < 1.5× credit |
| 🟡 WATCH | 4–8% buffer OR call value 1.5–2× credit |
| 🟠 WARNING | 2–4% buffer OR call value 2–3× credit |
| 🔴 DANGER | 0–2% buffer OR call value 3–5× credit |
| 🚨 ACT NOW | Stock at/above strike OR call value > 5× credit |

**Note:** Unlike put spreads, being called away on a covered call is often a fine outcome — the user keeps the premium plus stock gains up to the strike.

**Required inputs:** ticker, short call strike, premium received, expiry date, (optional) cost basis

**Example output:**
```
╔══════════════════════════════════════════════════════╗
║  COVERED CALL MONITOR — AAPL                          ║
║  SELL $260 Call  ·  2026-04-24                        ║
╠══════════════════════════════════════════════════════╣
║  Status:  🟡 WATCH ZONE                               ║
╠══════════════════════════════════════════════════════╣
║  Stock now:        $247.99                            ║
║  Call strike:      $260  (buffer: 4.84%)              ║
║  Call delta:       0.295                              ║
║  DTE remaining:    34 days                            ║
╠══════════════════════════════════════════════════════╣
║  Current P&L:      $0  per contract (on call)         ║
║  Call value now:   $3.33  (was $3.33 at open)         ║
║  Max profit:       $333  (if expires OTM)             ║
╚══════════════════════════════════════════════════════╝
```

---

## Usage

There are two ways to use the options skill pack:

### Option A: Claude Code (skills)

Use skills directly in Claude Code. Skills trigger automatically based on what you type.

### Option B: Web Chat App

A standalone chat interface powered by Claude API. Run locally with your own API key.

```bash
pip install -r app/requirements.txt
export ANTHROPIC_API_KEY=sk-ant-your-key-here
python3 -m uvicorn app.main:app
```

Open http://localhost:8000. The app has two main areas:

**Chat Sidebar** — AI-powered chat with all 7 skills available. Toggle the **AI switch** off to run scripts without spending API tokens (Check and Analyze still work, just no AI interpretation).

**Portfolio Tab** — Add, edit, check, close, and delete option positions. "Check All" runs monitors for every open position and updates zone status. After each check, positions show **actionable suggestions** — profit-taking hints at 50%/75% of max profit, gamma risk warnings near expiry, and defensive guidance (roll, close) based on zone. Positions use UUID-based IDs.

**Analyzer Tab** — Run selector scripts directly (no AI tokens used):
- Pick a ticker and strategy (bull put spread, iron condor, or covered call)
- View results with bid/ask prices, metrics, and an "Add to Portfolio" button
- **Compare All** mode runs all 3 selectors in parallel, highlights the best return and probability, and **auto-suggests** the best strategy based on trend (20-day price change) and IV level (ATM implied volatility) — no AI tokens needed
- When AI is on, results are also sent to chat for interpretation with enriched market context

**Requires:** Python 3.10+, an [Anthropic API key](https://console.anthropic.com) with credits.

### Option C: Docker (alternative)

```bash
cp app/.env.example app/.env
# Edit app/.env — add your ANTHROPIC_API_KEY
docker compose up
```

Open http://localhost:8000. Same as Option B but no Python setup needed — just Docker.

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

**`portfolio.json`** — add your open positions:

```json
[
  {
    "label": "NVDA May bull put",
    "strategy": "bull-put-spread",
    "ticker": "NVDA",
    "legs": [
      { "type": "put", "action": "sell", "strike": 155, "price": 3.35 },
      { "type": "put", "action": "buy", "strike": 140, "price": 1.37 }
    ],
    "net_credit": 1.98,
    "expiry": "2026-05-01",
    "contracts": 1,
    "opened": "2026-03-21",
    "status": "open"
  }
]
```

| Field | Required | Description |
|---|---|---|
| `label` | yes | Human-readable name for the position |
| `strategy` | yes | Strategy type: `bull-put-spread`, `iron-condor`, `covered-call` |
| `ticker` | yes | Stock symbol |
| `legs` | yes | Array of option legs — works for any number of legs |
| `legs[].type` | yes | `"put"` or `"call"` |
| `legs[].action` | yes | `"buy"` or `"sell"` |
| `legs[].strike` | yes | Strike price |
| `legs[].price` | no | Entry price per leg |
| `net_credit` | yes | Net credit received per share |
| `expiry` | yes | Expiry date (YYYY-MM-DD) |
| `contracts` | no | Number of contracts (default: 1) |
| `opened` | no | Date position was opened |
| `cost_basis` | no | Stock purchase price per share (used by covered-call monitor for P&L) |
| `status` | yes | `"open"` or `"closed"` — closed positions are skipped by the monitor |

**Managing positions** — just ask Claude in an interactive session:
- `"add my AAPL $220/$210 put spread, $1.85 credit, expires June 20"`
- `"close the NVDA position"`
- `"update the C spread — I rolled to July expiry"`
- `"show my portfolio"`

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
Read portfolio.json. Skip any positions where status is "closed".
For each open position, check strategy type and run the appropriate script:
  If strategy is "bull-put-spread": extract sell/buy put strikes from legs, then run:
    python3 .claude/local-marketplace/plugins/bull-put-spread-monitor/skills/bull-put-spread-monitor/check_position.py TICKER SELL_STRIKE BUY_STRIKE NET_CREDIT EXPIRY
  If strategy is "iron-condor": extract all 4 strikes from legs, then run:
    python3 .claude/local-marketplace/plugins/iron-condor-monitor/skills/iron-condor-monitor/check_iron_condor.py TICKER SHORT_PUT LONG_PUT SHORT_CALL LONG_CALL NET_CREDIT EXPIRY

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
Read portfolio.json. Skip any positions where status is "closed".
For each open position, check strategy type and run the appropriate script:
  If strategy is "bull-put-spread": extract sell/buy put strikes from legs, then run:
    python3 .claude/local-marketplace/plugins/bull-put-spread-monitor/skills/bull-put-spread-monitor/check_position.py TICKER SELL_STRIKE BUY_STRIKE NET_CREDIT EXPIRY
  If strategy is "iron-condor": extract all 4 strikes from legs, then run:
    python3 .claude/local-marketplace/plugins/iron-condor-monitor/skills/iron-condor-monitor/check_iron_condor.py TICKER SHORT_PUT LONG_PUT SHORT_CALL LONG_CALL NET_CREDIT EXPIRY

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
├── app/                                          # Web chat app (Option B)
│   ├── main.py                                   # FastAPI server + Claude API integration
│   ├── tools.py                                  # Tool definitions + script executors
│   ├── prompts.py                                # System prompt + per-skill guidance
│   ├── requirements.txt                          # Python dependencies
│   ├── .env.example                              # API key template
│   └── static/                                   # Chat UI
│       ├── index.html
│       ├── style.css
│       └── app.js
├── Dockerfile                                    # Docker build (Option C)
├── docker-compose.yml                            # Docker compose (Option C)
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
            ├── bull-put-spread-monitor/
            │   ├── .claude-plugin/
            │   │   └── plugin.json               # plugin manifest
            │   └── skills/
            │       └── bull-put-spread-monitor/
            │           ├── SKILL.md              # skill instructions
            │           ├── check_position.py     # yfinance position checker
            │           └── evals/
            │               └── evals.json        # test cases & assertions
            ├── iron-condor-selector/
            │   ├── .claude-plugin/
            │   │   └── plugin.json               # plugin manifest
            │   └── skills/
            │       └── iron-condor-selector/
            │           ├── SKILL.md              # skill instructions
            │           ├── fetch_iron_condor.py  # yfinance 4-leg chain fetcher
            │           └── evals/
            │               └── evals.json        # test cases & assertions
            ├── iron-condor-monitor/
            │   ├── .claude-plugin/
            │   │   └── plugin.json               # plugin manifest
            │   └── skills/
            │       └── iron-condor-monitor/
            │           ├── SKILL.md              # skill instructions
            │           ├── check_iron_condor.py  # yfinance 4-leg position checker
            │           └── evals/
            │               └── evals.json        # test cases & assertions
            ├── spread-roller/
            │   ├── .claude-plugin/
            │   │   └── plugin.json               # plugin manifest
            │   └── skills/
            │       └── spread-roller/
            │           ├── SKILL.md              # skill instructions
            │           ├── roll_spread.py        # yfinance roll target scanner
            │           └── evals/
            │               └── evals.json        # test cases & assertions
            ├── covered-call-selector/
            │   ├── .claude-plugin/
            │   │   └── plugin.json               # plugin manifest
            │   └── skills/
            │       └── covered-call-selector/
            │           ├── SKILL.md              # skill instructions
            │           ├── fetch_covered_call.py # yfinance covered call fetcher
            │           └── evals/
            │               └── evals.json        # test cases & assertions
            └── covered-call-monitor/
                ├── .claude-plugin/
                │   └── plugin.json               # plugin manifest
                └── skills/
                    └── covered-call-monitor/
                        ├── SKILL.md              # skill instructions
                        ├── check_covered_call.py # yfinance covered call checker
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

### iron-condor-selector — 3 test cases

| Eval | Tests |
|---|---|
| `standard-aapl` | Default 16Δ, 4-leg trade card, profit zone, risk checklist |
| `custom-delta-nvda` | 20Δ override, PoP ~60%, tighter strikes |
| `range-bound-spy` | Implicit intent triggering ("neutral", "range-bound"), strategy rationale |

**Benchmark results (iteration 1):**

| | with_skill | without_skill |
|---|---|---|
| Pass rate | **100%** | 69% |
| Avg time | 78.4s | 140.3s |

### iron-condor-monitor — 3 test cases

| Eval | Tests |
|---|---|
| `aapl-safe-zone` | SAFE zone, dual buffer display, both sides comfortable |
| `nvda-put-pressure` | Identifies worse side (put closer), correct buffer comparison |
| `spy-in-trouble` | WATCH zone (call buffer 6.5%), addresses user concern, profit zone |

**Benchmark results (iteration 1):**

| | with_skill | without_skill |
|---|---|---|
| Pass rate | **94%** | 56% |

### spread-roller — 3 test cases

| Eval | Tests |
|---|---|
| `bull-put-roll` | Close cost, 6 ranked candidates (calendar + diagonal), net roll credit, recommendation |
| `iron-condor-put-roll` | Put-side-only roll, close cost, asymmetry warning, recommendation |
| `danger-zone-implicit` | Implicit trigger from "danger zone" context, close option alongside rolls, urgency |

**Benchmark results (iteration 1):**

| | with_skill | without_skill |
|---|---|---|
| Pass rate | **100%** | 25% |
| Avg time | 70.4s | 40.4s |

### covered-call-selector — 3 test cases

| Eval | Tests |
|---|---|
| `standard-aapl` | Default 30Δ, 30-45 DTE, trade card with all yield metrics, risk checklist |
| `conservative-msft` | 15Δ override, lower premium, ~15% prob of assignment |
| `with-cost-basis-nvda` | Cost basis adjustment, effective cost basis, called-away P&L |

**Benchmark results (iteration 1):**

| | with_skill | without_skill |
|---|---|---|
| Pass rate | **100%** | 31% |
| Avg time | 56.2s | 36.8s |

### covered-call-monitor — 3 test cases

| Eval | Tests |
|---|---|
| `aapl-safe-zone` | Zone classification, buffer%, call P&L, actionable guidance |
| `nvda-cost-basis` | Zone + cost basis adjustment, effective cost basis, called-away P&L |
| `spy-assignment-question` | Implicit trigger, answers "will I get called away?", buffer + delta |

**Benchmark results (iteration 1):**

| | with_skill | without_skill |
|---|---|---|
| Pass rate | **100%** | 13% |
| Avg time | 51.3s | 33.0s |

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
