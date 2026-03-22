# options-skill-pack

Options trading toolkit — 7 skills for Claude Code + a self-hosted web chat app with portfolio management. Find spreads, monitor positions, evaluate rolls, and track your portfolio with AI-powered analysis.

**Three ways to use:**

| | Setup | Best for |
|---|---|---|
| **Option 1: Claude Code** | Clone + `setup.sh` | CLI power users, skill triggers in terminal |
| **Option 2: Local web app** | `pip install` + `uvicorn` | Interactive UI, portfolio dashboard |
| **Option 3: Docker** | `docker compose up` | Zero Python setup, containerised |

---

## Quick start

### Option 1: Claude Code (skills)

Skills activate automatically in Claude Code when you're in this project directory.

```bash
git clone https://github.com/sushanthemern/options-skill-pack.git
cd options-skill-pack
pip install yfinance pytz
bash setup.sh   # generates .claude/settings.json for this machine
```

Then just talk to Claude:

```
> bull put spread on AAPL
> check my NVDA $155/$140 spread expiring May 1
> iron condor on SPY
> roll my put spread
```

Skills trigger based on what you say — no special commands needed. See the [Skills reference](#skills) below for trigger phrases and parameters.

**Requirements:** Claude Code CLI, Python 3.10+, `yfinance` + `pytz` packages.

---

### Option 2: Local web app

Run the full web UI locally with your own Anthropic API key.

```bash
git clone https://github.com/sushanthemern/options-skill-pack.git
cd options-skill-pack
pip install -r app/requirements.txt
```

Set your API key and start the server:

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here    # macOS/Linux
# set ANTHROPIC_API_KEY=sk-ant-your-key-here     # Windows

python3 -m uvicorn app.main:app
```

Open **http://localhost:8000**.

**The app has three tabs:**

- **Chat** — AI-powered chat with all 7 skills available as tools. Toggle the AI switch off to run scripts without spending API tokens (Check and Analyze still work).
- **Portfolio** — Add, edit, check, close, and delete option positions. "Check All" runs monitors for every open position and classifies each into a zone (SAFE → ACT NOW). After each check, positions show actionable suggestions — profit-taking at 50%/75% of max profit, gamma risk warnings near expiry, and defensive guidance based on zone.
- **Analyzer** — Run selector scripts directly (no AI tokens). Pick a ticker and strategy, or use "Compare All" to run all 3 selectors in parallel with market context. Auto-suggests the best strategy based on 20-day trend and ATM IV level. After each analysis, click "View Chain" to see the full option chain for that expiry — recommended strikes are highlighted.

**Requirements:** Python 3.10+, an [Anthropic API key](https://console.anthropic.com) with credits.

---

### Option 3: Docker Compose

No Python setup needed — just Docker.

```bash
git clone https://github.com/sushanthemern/options-skill-pack.git
cd options-skill-pack
cp app/.env.example app/.env
```

Edit `app/.env` and add your API key:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Then:

```bash
docker compose up
```

Open **http://localhost:8000**. Same UI as Option 2.

Portfolio data persists via a volume mount to `portfolio.json` in the project root. The container runs as a non-root user and includes a healthcheck on `/api/portfolio`.

To rebuild after pulling updates:

```bash
docker compose up --build
```

**Requirements:** Docker with Compose v2.

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

**Trigger phrases:**
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

---

### bull-put-spread-monitor

Monitors an existing bull put spread and classifies its health into one of five zones.

**Trigger phrases:**
- "check my NVDA $155/$140 spread"
- "how is my put spread doing"
- "is my position safe"
- "should I be worried about my C spread"

**Zones:**

| Zone | Condition |
|---|---|
| SAFE | Stock > 8% above short strike AND loss < 20% of max |
| WATCH | 4–8% buffer OR 20–40% of max loss |
| WARNING | 2–4% buffer OR 40–65% of max loss |
| DANGER | 0–2% buffer OR 65–85% of max loss |
| ACT NOW | Stock at/below short strike OR > 85% of max loss |

**Required inputs:** ticker, short strike, long strike, original net credit, expiry date

---

### iron-condor-monitor

Monitors an existing iron condor and classifies its health using **two-sided buffer logic** — the worse side (put or call) determines the zone.

**Trigger phrases:**
- "check my AAPL iron condor"
- "how is my condor doing"
- "is my iron condor safe"

**Required inputs:** ticker, all 4 strikes, net credit, expiry date

---

### covered-call-selector

Identifies the optimal call strike to sell for a covered call on a stock you own.

**Trigger phrases:**
- "covered call on AAPL"
- "sell calls against my shares"
- "what call should I sell on NVDA"
- "yield on my shares"

**What it does:**
1. Fetches live call option chain data via `fetch_covered_call.py`
2. Selects the call strike near 30Δ (default) in the 30–45 DTE window
3. Calculates premium, static return, annualized return, downside protection, called-away return
4. Runs a risk checklist (earnings, IV rank, ex-dividend, trend)
5. If cost basis provided, shows effective cost basis and called-away P&L

**Parameters** (defaults shown):

| Parameter | Default | Example override |
|---|---|---|
| Expiry | 30–45 DTE | "60 days out", "May expiry" |
| Short call delta | 30Δ | "sell a 15-delta call" |
| Contracts | 1 (100 shares) | "3 contracts" |
| Cost basis | *(optional)* | "I bought at $150" |

---

### covered-call-monitor

Monitors an existing covered call and classifies its health. Answers the key question: "will my shares get called away?"

**Trigger phrases:**
- "check my AAPL covered call"
- "will my shares get called away"
- "is my covered call safe"

**Zones:**

| Zone | Condition |
|---|---|
| SAFE | Stock > 8% below strike AND call value < 1.5× credit |
| WATCH | 4–8% buffer OR call value 1.5–2× credit |
| WARNING | 2–4% buffer OR call value 2–3× credit |
| DANGER | 0–2% buffer OR call value 3–5× credit |
| ACT NOW | Stock at/above strike OR call value > 5× credit |

**Required inputs:** ticker, short call strike, premium received, expiry date, (optional) cost basis

---

### spread-roller

Finds roll targets for bull put spreads and iron condors when a position needs to be rolled out or diagonally adjusted.

**Trigger phrases:**
- "roll my NVDA put spread"
- "roll the put side of my iron condor"
- "my spread is in danger, what can I do?"
- "roll down and out"

**What it does:**
1. Prices the cost to close your current spread
2. Scans 3 future expiries (~2, 4, and 6 weeks out)
3. Evaluates 3 roll types per expiry: calendar, defensive diagonal, aggressive diagonal
4. Ranks all candidates by net roll credit (best first)
5. For iron condors, rolls one side at a time

**Parameters** (defaults shown):

| Parameter | Default | Example override |
|---|---|---|
| Target delta | 0.20 (put spread), 0.16 (condor) | "roll to 15-delta" |
| Roll side (condor) | — | "roll the put side" |

---

## Portfolio monitor setup

The portfolio monitor lets you run scheduled position checks with notifications.

### 1. Configure

```bash
# macOS / Linux
bash setup_monitor.sh

# Windows
setup_monitor.bat
```

This creates `portfolio.json` and `monitor_config.json` from example templates (both gitignored).

### 2. Add positions to portfolio.json

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
| `label` | yes | Human-readable name |
| `strategy` | yes | `bull-put-spread`, `iron-condor`, or `covered-call` |
| `ticker` | yes | Stock symbol |
| `legs` | yes | Array of legs (`type`, `action`, `strike`, optional `price`) |
| `net_credit` | yes | Net credit received per share |
| `expiry` | yes | Expiry date (YYYY-MM-DD) |
| `contracts` | no | Number of contracts (default: 1) |
| `cost_basis` | no | Stock purchase price (covered calls only) |
| `status` | yes | `"open"` or `"closed"` |

Or manage positions via Claude: `"add my AAPL $220/$210 put spread, $1.85 credit, expires June 20"`

### 3. Configure notifications

Edit `monitor_config.json`:

| Channel | What you need |
|---|---|
| `macos` | Nothing — works out of the box |
| `email` | Gmail app password (Google Account → Security → App Passwords) |
| `pushover` | $5 one-time Pushover app + free API account at pushover.net |

For SMS via email: set `to` to your carrier's gateway (e.g. `5551234567@vtext.com`).

### 4. Run the monitor

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
claude -p "..." --allowedTools Bash,Read   # same as above, with --mode summary
```

### 5. Schedule it (optional)

**macOS — launchd:**

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

```bash
launchctl load ~/Library/LaunchAgents/com.options-monitor.plist
launchctl start com.options-monitor    # test immediately
```

**Windows — Task Scheduler:**

1. Open Task Scheduler → Create Basic Task
2. Trigger: Daily at 9:30 AM (add second task for 3:00 PM)
3. Action: Start `cmd.exe` with arguments: `/c cd /d C:\path\to\options-skill-pack && claude -p "..." --allowedTools Bash,Read`
4. Set "Start in" to your project folder

---

## Project structure

```
options-skill-pack/
├── app/                                          # Web chat app (Options 2 & 3)
│   ├── main.py                                   # FastAPI server + Claude API integration
│   ├── tools.py                                  # Tool definitions + script executors
│   ├── prompts.py                                # System prompt + per-skill guidance
│   ├── requirements.txt                          # Python dependencies
│   ├── .env.example                              # API key template
│   └── static/                                   # Chat UI
│       ├── index.html
│       ├── style.css
│       └── app.js
├── Dockerfile                                    # Docker build
├── docker-compose.yml                            # Docker compose
├── .dockerignore                                 # Docker build exclusions
├── setup.sh                                      # One-time Claude Code setup
├── setup_monitor.sh                              # Monitor setup (macOS/Linux)
├── setup_monitor.bat                             # Monitor setup (Windows)
├── notify.py                                     # Notification sender (creds stay in-process)
├── portfolio.example.json                        # Template → portfolio.json
├── monitor_config.example.json                   # Template → monitor_config.json
└── .claude/local-marketplace/plugins/
    ├── bull-put-spread-selector/                  # Find optimal put spread strikes
    ├── bull-put-spread-monitor/                   # Monitor put spread health
    ├── iron-condor-selector/                      # Find optimal iron condor strikes
    ├── iron-condor-monitor/                       # Monitor iron condor health
    ├── covered-call-selector/                     # Find optimal call to sell
    ├── covered-call-monitor/                      # Monitor covered call health
    └── spread-roller/                             # Find roll targets
```

---

## Evals

Each skill has 3 test cases. Benchmark results (with_skill vs without_skill):

| Skill | With skill | Without skill |
|---|---|---|
| bull-put-spread-selector | **100%** | 44% |
| iron-condor-selector | **100%** | 69% |
| iron-condor-monitor | **94%** | 56% |
| spread-roller | **100%** | 25% |
| covered-call-selector | **100%** | 31% |
| covered-call-monitor | **100%** | 13% |
| bull-put-spread-monitor | **100%** | 50% |

---

## Security notes

- **No authentication** — the web app is designed for local/private use. Do not expose to the public internet without adding auth.
- **API key** — stored in `app/.env` (gitignored). Never committed to the repo.
- **Portfolio data** — `portfolio.json` is gitignored. In Docker, it's persisted via volume mount.
- **Monitor credentials** — `monitor_config.json` is gitignored. `notify.py` reads it directly; credentials never reach Claude.
- **Docker** — container runs as non-root user. Healthcheck enabled.
- **Input validation** — ticker format validated (1-5 uppercase letters), numeric fields bounded, chat message roles restricted to user/assistant.
- **Subprocess calls** — all scripts run with `shell=False` (no shell injection). Ticker validated before execution.
- **XSS** — assistant messages sanitized with DOMPurify before rendering.
