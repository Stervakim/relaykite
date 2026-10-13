[CmdletBinding()]
param([string]$Destination = (Join-Path $env:LOCALAPPDATA 'CodakiPortableUse'), [string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path -Parent $PSScriptRoot
$Destination = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath (Join-Path $Destination 'portable')) {
    throw 'Existing installation found. Use CODEX_INSTALL.md to back up, stop the exact agent and update without replacing its private configuration.'
}
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceRoot 'src\portable') -Destination $Destination -Recurse
Copy-Item -LiteralPath (Join-Path $sourceRoot 'src\shared') -Destination $Destination -Recurse
foreach ($name in @('START_WINDOWS_AGENT.cmd','agent-windows.example.json','requirements-windows.txt','VERSION')) {
    Copy-Item -LiteralPath (Join-Path $sourceRoot $name) -Destination $Destination
}
& $Python -m venv (Join-Path $Destination '.venv')
if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed' }
$runtime = Join-Path $Destination '.venv\Scripts\python.exe'
& $runtime -m pip install -r (Join-Path $Destination 'requirements-windows.txt')
if ($LASTEXITCODE -ne 0) { throw 'Windows dependency installation failed' }
Push-Location $Destination
try { & $runtime -m portable check --platform windows --state 'install-check-state' }
finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'Windows backend validation failed' }
Write-Output "Installed runtime in $Destination. Enroll your own Windows device before starting the agent; see CODEX_INSTALL.md."
