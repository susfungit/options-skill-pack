@echo off
REM Run once after cloning: setup.bat
REM Generates .claude\settings.json with the correct absolute path for this machine.

setlocal

set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

set "MARKETPLACE_PATH=%PROJECT_ROOT%\.claude\local-marketplace"
set "SETTINGS_FILE=%PROJECT_ROOT%\.claude\settings.json"

REM JSON requires forward slashes or escaped backslashes. Escape backslashes.
set "MARKETPLACE_JSON=%MARKETPLACE_PATH:\=\\%"

if not exist "%PROJECT_ROOT%\.claude" mkdir "%PROJECT_ROOT%\.claude"

(
  echo {
  echo   "enabledPlugins": {
  echo     "bull-put-spread-selector@options-skill-pack": true,
  echo     "bull-put-spread-monitor@options-skill-pack": true,
  echo     "bear-call-spread-selector@options-skill-pack": true,
  echo     "bear-call-spread-monitor@options-skill-pack": true,
  echo     "iron-condor-selector@options-skill-pack": true,
  echo     "iron-condor-monitor@options-skill-pack": true,
  echo     "spread-roller@options-skill-pack": true,
  echo     "covered-call-selector@options-skill-pack": true,
  echo     "covered-call-monitor@options-skill-pack": true,
  echo     "cash-secured-put-selector@options-skill-pack": true,
  echo     "cash-secured-put-monitor@options-skill-pack": true,
  echo     "options-trade-plan@options-skill-pack": true
  echo   },
  echo   "extraKnownMarketplaces": {
  echo     "options-skill-pack": {
  echo       "source": {
  echo         "source": "directory",
  echo         "path": "%MARKETPLACE_JSON%"
  echo       }
  echo     }
  echo   }
  echo }
) > "%SETTINGS_FILE%"

echo [OK] Written: %SETTINGS_FILE%
echo      Marketplace path: %MARKETPLACE_PATH%

endlocal
