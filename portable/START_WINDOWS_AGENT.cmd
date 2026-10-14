@echo off
setlocal
cd /d "%~dp0"
if not exist "agent-windows.json" (
  echo Windows agent has not been enrolled yet. Missing agent-windows.json
  echo Do not copy the Android device credential. Register a separate Windows identity in the Site deployment.
  exit /b 2
)
".venv\Scripts\python.exe" -m portable agent --platform windows --config "agent-windows.json" --state "windows-agent-state"
