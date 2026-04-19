# Installation Guide

Step-by-step instructions to get **options-skill-pack** running on macOS, Linux, or Windows. Pick one of three install paths depending on how you want to use it.

| Path | Setup time | Needs API key? | Best for |
|---|---|---|---|
| **A. Claude Code skills** | ~2 min | No (uses your Claude Code subscription) | CLI users who already run Claude Code |
| **B. Local web app** | ~5 min | Yes (Anthropic API) | Interactive UI, portfolio dashboard |
| **C. Docker** | ~3 min | Yes (Anthropic API) | Zero Python setup |

---

## Prerequisites

| Tool | Version | All paths? | Install |
|---|---|---|---|
| **git** | any recent | Yes | [git-scm.com/downloads](https://git-scm.com/downloads) |
| **Python** | 3.10+ | A, B | [python.org/downloads](https://www.python.org/downloads/) — on Windows, check **"Add Python to PATH"** during install |
| **pip** | bundled with Python | A, B | — |
| **Claude Code CLI** | latest | A only | [claude.com/claude-code](https://claude.com/claude-code) |
| **Anthropic API key** | — | B, C | [console.anthropic.com](https://console.anthropic.com) → create key with credits |
| **Docker + Compose v2** | latest | C only | [docs.docker.com/get-docker](https://docs.docker.com/get-docker/) |

Check versions:

```bash
python3 --version    # should print 3.10+
pip --version
git --version
```

On Windows, replace `python3` with `python` everywhere below.

---

## Clone the repo (all paths)

```bash
git clone https://github.com/sushanthemern/options-skill-pack.git
cd options-skill-pack
```

All subsequent commands run from the `options-skill-pack/` directory.

---

## Path A — Claude Code skills

Skills activate automatically when you run Claude Code inside this directory. Triggers are natural-language ("bull put spread on AAPL", "options trade plan for TSLA next week", etc.).

### macOS / Linux

```bash
pip install yfinance pytz
bash setup.sh
```

### Windows

Pick one of:

```bat
REM Command Prompt or double-click in Explorer
pip install yfinance pytz
setup.bat
```

```powershell
# PowerShell
pip install yfinance pytz
.\setup.bat
```

Or if you prefer Git Bash / WSL:

```bash
pip install yfinance pytz
bash setup.sh
```

### Verify

Open Claude Code in this directory and type:

```
> bull put spread on AAPL
```

You should see a trade card within ~10 seconds. If not, see **Troubleshooting** below.

### What `setup.sh` / `setup.bat` does

Generates `.claude/settings.json` with (a) the 12 plugins enabled and (b) the absolute path to `.claude/local-marketplace` on your machine. That file is gitignored because the path is machine-specific — that's why you re-run this on every clone.

---

## Path B — Local web app

Full web UI with chat, portfolio, analyzer, and profile tabs. Runs at `http://localhost:8000`.

### Step 1 — Install dependencies

```bash
pip install -r app/requirements.txt
```

### Step 2 — Set your API key

**macOS / Linux:**

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Add that line to `~/.zshrc` (macOS) or `~/.bashrc` (Linux) to persist across terminal sessions.

**Windows (PowerShell):**

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-your-key-here"
```

Or set it permanently: `System Properties → Environment Variables → New → ANTHROPIC_API_KEY`.

**Windows (cmd):**

```bat
set ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### Step 3 — Start the server

```bash
python3 -m uvicorn app.main:app
```

On Windows: `python -m uvicorn app.main:app`.

Open **http://localhost:8000**.

### Step 4 — (Optional) enable API-key protection

If you're running on a machine accessible to others, set a shared secret:

```bash
export APP_API_KEY=some-random-string
```

The UI will then require login with that key.

### Running in the background

```bash
# macOS / Linux
nohup python3 -m uvicorn app.main:app > app.log 2>&1 &
```

```bat
REM Windows
start /b python -m uvicorn app.main:app > app.log 2>&1
```

---

## Path C — Docker

Zero Python setup — everything runs in a container.

### Step 1 — Configure the API key

```bash
cp app/.env.example app/.env
```

Edit `app/.env`:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### Step 2 — Create persistent data files

Docker needs these as real files before mounting them as volumes:

**macOS / Linux:**

```bash
echo '[]' > portfolio.json
echo '{}' > profile.json
echo '[]' > watchlist.json
```

**Windows (PowerShell):**

```powershell
'[]' | Out-File -Encoding ascii portfolio.json
'{}' | Out-File -Encoding ascii profile.json
'[]' | Out-File -Encoding ascii watchlist.json
```

### Step 3 — Start

```bash
docker compose up
```

Open **http://localhost:8000**. Data persists in `portfolio.json`, `profile.json`, `watchlist.json` in your project root.

### Rebuild after updates

```bash
git pull
docker compose up --build
```

---

## Optional — Portfolio monitor (background alerts)

If you want automated monitoring of open positions with email/Pushover/SMS alerts, run the monitor setup **after** Path A or B is working:

**macOS / Linux:**

```bash
bash setup_monitor.sh
```

**Windows:**

```bat
setup_monitor.bat
```

Then edit `portfolio.json` (your positions) and `monitor_config.json` (notification channels). See README §Portfolio monitor for the exact `claude -p` commands and how to schedule them via `cron` / `launchd` / Task Scheduler.

---

## Updating to a newer version

```bash
git pull
pip install -r app/requirements.txt --upgrade   # web app only
```

If new skills were added, re-run `setup.sh` / `setup.bat` so the settings file gets the new plugin entries.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'yfinance'`**
→ `pip install yfinance pytz`. If you have multiple Pythons, use `python3 -m pip install ...` (or `python -m pip install ...` on Windows) to install to the right one.

**Skills don't trigger in Claude Code**
→ You ran `setup.sh` in one directory but opened Claude Code in another. Settings are per-project. `cd` into the repo first, then `claude`.

**`setup.sh: Permission denied` (macOS/Linux)**
→ `chmod +x setup.sh` or run it as `bash setup.sh`.

**Windows: `'setup.bat' is not recognized`**
→ You're not in the project directory. `cd options-skill-pack` first. Or use `.\setup.bat` in PowerShell.

**`port 8000 already in use`**
→ Another process is using it. Start on a different port: `python3 -m uvicorn app.main:app --port 8001`.

**`ANTHROPIC_API_KEY not set`**
→ You set it in a different terminal session. Env vars don't cross terminals. Re-export, or use a `.env` file (Path C does this).

**Docker: `failed to populate volume: not a directory`**
→ You didn't run Step 2. `portfolio.json` / `profile.json` / `watchlist.json` must exist as files before `docker compose up`.

**`yfinance` throws `possibly delisted`**
→ Yahoo Finance rate-limited you. Wait a few minutes and retry, or switch network.

---

## Uninstall

```bash
# remove generated settings and data (keep the repo)
rm -rf .claude/settings.json .claude/settings.local.json portfolio.json profile.json watchlist.json monitor_config.json

# or remove everything
cd ..
rm -rf options-skill-pack
```

On Windows, replace `rm -rf` with `rmdir /s /q` (directories) or `del` (files).

---

## Next steps

- **Skills reference** — see [README.md](README.md#skills) for the full list of trigger phrases and parameters.
- **Adding a strategy** — see the `/add-strategy` command defined in `.claude/commands/add-strategy.md`.
- **Issues** — [github.com/sushanthemern/options-skill-pack/issues](https://github.com/sushanthemern/options-skill-pack/issues).
