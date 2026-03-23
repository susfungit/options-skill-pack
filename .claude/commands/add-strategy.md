# Add Strategy

Walk the user through adding a new options strategy to the skill pack. This is a multi-step process — complete each step, confirm it works, then move to the next.

## Step 0 — Gather details

Ask the user for:

| Input | Example |
|---|---|
| Strategy name (kebab-case) | `cash-secured-put` |
| Short description | "Sells a put backed by cash to buy shares at a discount" |
| Leg structure | What options are bought/sold (e.g., "sell 1 put") |
| Key parameters | What inputs the user configures (delta, DTE, width, etc.) |
| Is a selector needed? | Almost always yes — finds optimal strikes |
| Is a monitor needed? | Yes if the user will hold the position |
| Does the shared roller work? | Or does this strategy need custom roll logic? |

Use existing strategies as reference patterns:
- **Bull put spread** (2-leg credit spread): selector + monitor + roller
- **Iron condor** (4-leg credit spread): selector + monitor + roller
- **Covered call** (stock + 1 call): selector + monitor (no roller yet)

---

## Step 1 — Create the selector plugin

Create the plugin directory structure:

```
.claude/local-marketplace/plugins/{STRATEGY}-selector/
├── .claude-plugin/
│   └── plugin.json
└── skills/
    └── {STRATEGY}-selector/
        ├── SKILL.md
        ├── fetch_{script_name}.py
        └── evals/
            └── evals.json
```

### 1a. plugin.json

```json
{
  "name": "{STRATEGY}-selector",
  "version": "1.0.0",
  "description": "Short description of what the selector does.",
  "author": { "name": "sushant" }
}
```

### 1b. SKILL.md

Follow the 7-step pattern from existing selectors. Read one of these as a template:
- `.claude/local-marketplace/plugins/bull-put-spread-selector/skills/bull-put-spread-selector/SKILL.md`
- `.claude/local-marketplace/plugins/covered-call-selector/skills/covered-call-selector/SKILL.md`

The 7 steps are:
1. Gather inputs (ticker, delta, DTE, strategy-specific params)
2. Fetch live option chain data via the Python script
3. Fallback estimation when live data is unavailable
4. Risk/reward calculations (formulas)
5. Risk signal checklist (earnings, IV rank, trend, dividend)
6. Output format (structured trade card)
7. Interactive widget (optional P&L chart)

### 1c. Python fetch script

The script must:
- Accept CLI args: `TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX] [STRATEGY_SPECIFIC_PARAMS...]`
- Use yfinance to fetch the option chain
- Find the optimal strikes based on the parameters
- Output a single JSON object to stdout with all computed fields
- Handle errors gracefully (print JSON with an `error` field)

Use `fetch_chain.py` (bull put spread) or `fetch_covered_call.py` as reference implementations.

### 1d. evals/evals.json

Create a minimal eval set:
```json
{
  "skill_name": "{STRATEGY}-selector",
  "evals": [
    { "id": 1, "prompt": "Find a {strategy} on AAPL", "expected_output": "Trade card with strikes and metrics" }
  ]
}
```

---

## Step 2 — Create the monitor plugin (if needed)

```
.claude/local-marketplace/plugins/{STRATEGY}-monitor/
├── .claude-plugin/
│   └── plugin.json
└── skills/
    └── {STRATEGY}-monitor/
        ├── SKILL.md
        ├── check_{script_name}.py
        └── evals/
            └── evals.json
```

### 2a. Monitor SKILL.md

Follow the 5-step pattern from existing monitors. Read one as a template:
- `.claude/local-marketplace/plugins/bull-put-spread-monitor/skills/bull-put-spread-monitor/SKILL.md`

Steps:
1. Gather position details (ticker, strikes, credit, expiry)
2. Fetch current position data via the Python script
3. Classify the zone (SAFE / WATCH / WARNING / DANGER / ACT NOW)
4. Output the status card
5. Zone-specific guidance (what to do in each zone)

### 2b. Monitor Python script

The script must:
- Accept CLI args with the position details
- Fetch current stock and option prices via yfinance
- Compute: buffer_pct, current spread value, pnl_per_contract, loss_pct_of_max
- Output JSON to stdout

### 2c. Zone classification

Decide whether the existing zone logic works. Two patterns exist:

**Spread-based zones** (bull put spread, iron condor) — uses buffer_pct + loss_pct_of_max:
- See `_classify_zone_spread()` in `app/main.py` (~line 604)

**Covered-call zones** — uses buffer_pct + call_value_ratio:
- See `_classify_zone_covered_call()` in `app/main.py` (~line 627)

If the new strategy needs different zone logic, add a new `_classify_zone_{strategy}()` function.

---

## Step 3 — Register in the API layer

These files wire the new strategy into the FastAPI app.

### 3a. `app/tools.py` — 4 changes

1. **Add selector tool to `TOOLS[]`** — Claude API tool definition with input_schema
2. **Add monitor tool to `TOOLS[]`** (if applicable)
3. **Add both to `SCRIPT_MAP`** — maps tool name to the Python script path
4. **Add arg builders in `_build_args()`** — converts tool_input dict to CLI args

### 3b. `app/prompts.py` — 2 changes

Add entries to `SKILL_GUIDANCE` dict for:
1. The selector tool — strike selection context, risk checklist, key formulas, output hints
2. The monitor tool — zone interpretation, action guidance per zone

### 3c. `app/main.py` — 5 changes

1. **`StrategyType` enum** (~line 153) — add the new strategy value
2. **`_STRATEGY_TO_TOOL` mapping** — map strategy name to selector tool name
3. **`DEFAULT_PROFILE`** (~line 28) — add strategy defaults under `strategy_defaults`
4. **Portfolio check endpoint** (~line 697) — add an `elif` branch for the new strategy in the position check handler that:
   - Builds the correct tool_input from the position's legs
   - Calls the monitor tool
   - Calls the appropriate zone classifier
5. **Compare mode** (`/api/analyze/compare`) — if the strategy should appear in side-by-side comparison:
   - Add a `run_tool("find_{tool}", "{strategy-key}")` call to the `asyncio.gather()` block
   - Each strategy gets its own profile defaults via `_build_input(strategy_key)` — do NOT share one strategy's defaults across tools

---

## Step 4 — Update the UI

### 4a. `app/static/index.html`

- Add the strategy to the analyzer dropdown (`<select id="az-strategy">`)
- Add the strategy to the portfolio form's strategy dropdown

### 4b. `app/static/app.js`

- **`updateLegFields(strategy)`** (~line 409) — add leg input fields for the new strategy
- **`savePosition()`** (~line 454) — add leg extraction logic
- **`prefillEditForm()`** (~line 363) — add pre-fill logic for edit mode
- **`renderPositionLegs()`** (~line 327) — add display logic for position cards
- **`buildAnalysisChatPrompt()`** (~line 728) — add chat prompt builder for analyzer results
- **`renderAnalysisResult()`** — add result rendering for the analyzer tab
- **`renderCompareResult()`** — add a compare card for the new strategy (legs, metrics, actions), update `returns`/`probs` arrays and `strategyToKey` map
- **`buildCompareChatPrompt()`** — add the new strategy's data to the compare chat prompt
- **`addCompareToPortfolio()`** — ensure `lastAnalysis.data` includes the new strategy key

### 4c. `app/static/style.css`

- The compare grid uses `auto-fit` with `minmax(280px, 1fr)` so it adapts automatically to any number of cards — no CSS changes needed when adding strategies

---

## Step 5 — Register the skills in settings

### 5a. `.claude/settings.json`

Add to `enabledPlugins`:
```json
"{STRATEGY}-selector@options-skill-pack": true,
"{STRATEGY}-monitor@options-skill-pack": true
```

---

## Step 6 — Update portfolio & monitoring support

### 6a. `portfolio.example.json`

Add an example position entry with the new strategy's leg structure.

### 6b. `setup_monitor.sh` and `setup_monitor.bat`

Update the echo messages that list supported strategies to include the new one.

### 6c. `profile.example.json`

Add default parameters for the new strategy under `strategy_defaults`.

---

## Step 7 — Update README.md

The README has strategy-specific documentation in several sections. Update all of them:

1. **Skill descriptions** — Add a section for the new selector and monitor skills with:
   - Skill name and description
   - Example trigger phrases
   - What it does and what data it returns

2. **Portfolio schema** — Update the valid `strategy` values list (look for the existing table that lists `bull-put-spread`, `iron-condor`, `covered-call`)

3. **Automated monitoring commands** — Add a `claude -p` command example for the new strategy's monitor, showing how to extract leg data and run the check script

4. **Directory tree** — Add the new plugin directories to the project structure listing

5. **Benchmark table** — Add placeholder rows for the new skills (fill in after running evals)

Use the existing strategy sections as templates for formatting and level of detail.

Note: Docker/Dockerfile do NOT need changes — the Dockerfile copies the entire plugins directory, so new plugins are automatically included.

---

## Step 8 — Test end-to-end

Run through this checklist:

- [ ] Selector script works standalone: `python3 fetch_{script}.py AAPL`
- [ ] Monitor script works standalone: `python3 check_{script}.py AAPL [args...]`
- [ ] Claude Code skill triggers on natural language (e.g., "find a {strategy} on NVDA")
- [ ] Analyzer tab runs the strategy
- [ ] Compare mode includes it (if applicable)
- [ ] Adding a position to portfolio works with correct legs
- [ ] Portfolio check runs the monitor and classifies the zone
- [ ] Profile defaults are applied correctly
- [ ] `docker-compose up` starts without errors

---

## Step 9 — Run evals

Run evals for both the selector and monitor skills to measure with-skill vs without-skill performance.

### 9a. Prepare eval prompts

Each skill already has `evals/evals.json` from Step 1/2. Review the prompts and add more if needed — aim for 3–5 diverse prompts per skill covering:
- Direct requests ("cash-secured put on AAPL")
- Indirect requests ("I want to buy MSFT at a discount")
- Edge cases ("sell a 40-delta put, I want to be assigned")

### 9b. Run with-skill and without-skill

For each eval prompt, run two tests:
1. **With skill** — Claude Code with the skill enabled, in the project directory
2. **Without skill** — Claude Code without the skill (or a fresh session outside the project)

### 9c. Grade results

Grade each run on these criteria:
- Did it use the correct script / fetch live data?
- Did it present a structured trade card?
- Were all key metrics present and correct?
- Were risk flags checked?
- Was the output actionable?

### 9d. Update README benchmark table

Replace the placeholder `—` entries in the README benchmark table with actual pass rates.

### 9e. Update evals.json

Save the final assertions and results back to the skill's `evals/evals.json` for future regression testing.

---

## File checklist

When done, every new strategy should have touched these files:

**New files created:**
- [ ] `.claude/local-marketplace/plugins/{STRATEGY}-selector/.claude-plugin/plugin.json`
- [ ] `.claude/local-marketplace/plugins/{STRATEGY}-selector/skills/{STRATEGY}-selector/SKILL.md`
- [ ] `.claude/local-marketplace/plugins/{STRATEGY}-selector/skills/{STRATEGY}-selector/fetch_{script}.py`
- [ ] `.claude/local-marketplace/plugins/{STRATEGY}-selector/skills/{STRATEGY}-selector/evals/evals.json`
- [ ] `.claude/local-marketplace/plugins/{STRATEGY}-monitor/.claude-plugin/plugin.json` (if monitor needed)
- [ ] `.claude/local-marketplace/plugins/{STRATEGY}-monitor/skills/{STRATEGY}-monitor/SKILL.md`
- [ ] `.claude/local-marketplace/plugins/{STRATEGY}-monitor/skills/{STRATEGY}-monitor/check_{script}.py`
- [ ] `.claude/local-marketplace/plugins/{STRATEGY}-monitor/skills/{STRATEGY}-monitor/evals/evals.json`

**Existing files modified:**
- [ ] `app/tools.py` — TOOLS[], SCRIPT_MAP, _build_args()
- [ ] `app/prompts.py` — SKILL_GUIDANCE entries
- [ ] `app/main.py` — StrategyType, _STRATEGY_TO_TOOL, DEFAULT_PROFILE, portfolio check, zone logic
- [ ] `app/static/index.html` — dropdowns
- [ ] `app/static/app.js` — leg fields, save, edit, render, analysis, compare mode
- [ ] `.claude/settings.json` — enabledPlugins
- [ ] `portfolio.example.json` — example entry
- [ ] `profile.example.json` — strategy defaults
- [ ] `setup_monitor.sh` — echo messages
- [ ] `setup_monitor.bat` — echo messages
- [ ] `README.md` — skill docs, portfolio schema, monitor commands, directory tree, benchmarks

**Verification:**
- [ ] Evals run for selector and monitor, benchmark table updated with results
