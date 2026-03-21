@echo off
REM First-time setup for the options portfolio monitor.
REM Run once after cloning: setup_monitor.bat

echo.
echo === Options Portfolio Monitor - First-Time Setup ===
echo.

REM ── portfolio.json ────────────────────────────────────────────────────────────

if exist portfolio.json (
  echo [OK] portfolio.json already exists - skipping
) else (
  copy portfolio.example.json portfolio.json >nul
  echo [OK] Created portfolio.json from template
  echo.
  echo   Edit portfolio.json to add your open bull put spread positions.
  echo   Each entry needs: ticker, short_strike, long_strike, net_credit, expiry
  echo.
)

REM ── monitor_config.json ───────────────────────────────────────────────────────

if exist monitor_config.json (
  echo [OK] monitor_config.json already exists - skipping
) else (
  copy monitor_config.example.json monitor_config.json >nul
  echo [OK] Created monitor_config.json from template
  echo.
  echo   Configure your notification channels in monitor_config.json:
  echo.
  echo   Email    ^> set enabled=true, fill in smtp credentials
  echo            ^> Tip: use a Gmail App Password ^(not your main password^)
  echo            ^> Google Account -^> Security -^> App Passwords
  echo   Pushover ^> set enabled=true, sign up at pushover.net ^($5 one-time^)
  echo            ^> for push notifications on iPhone/Android
  echo   SMS      ^> use email channel, set "to" to your carrier gateway
  echo            ^> e.g. 5551234567@vtext.com ^(Verizon^)
  echo                    5551234567@txt.att.net ^(AT^&T^)
  echo                    5551234567@tmomail.net ^(T-Mobile^)
  echo.
)

REM ── summary ───────────────────────────────────────────────────────────────────

echo.
echo === Setup complete ===
echo.
echo Next steps:
echo   1. Edit portfolio.json      - add your positions
echo   2. Edit monitor_config.json - configure notification channels
echo   3. Run the monitor ^(see README.md for the full command^):
echo.
echo   The monitor uses "claude -p" to check positions and "notify.py"
echo   to send notifications. Credentials in monitor_config.json are
echo   handled by notify.py only - they never reach Claude.
echo.
echo   See README.md for:
echo     - The exact claude -p commands ^(alert + summary mode^)
echo     - Scheduling instructions ^(macOS launchd / Windows Task Scheduler^)
echo.
pause
