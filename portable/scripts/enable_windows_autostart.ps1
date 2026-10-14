[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Installation, [string]$TaskName='CodakiPortableUseWindows')
$ErrorActionPreference='Stop'
$Installation=[IO.Path]::GetFullPath($Installation)
$exe=Join-Path $Installation '.venv\Scripts\pythonw.exe'
if (!(Test-Path -LiteralPath $exe) -or !(Test-Path -LiteralPath (Join-Path $Installation 'agent-windows.json'))) {
    throw 'Install and enroll the Windows agent first'
}
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { throw 'Task already exists; inspect it before updating' }
$user="$env:USERDOMAIN\$env:USERNAME"
$action=New-ScheduledTaskAction -Execute $exe -Argument '-m portable agent --platform windows --config agent-windows.json --state windows-agent-state' -WorkingDirectory $Installation
$trigger=New-ScheduledTaskTrigger -AtLogOn -User $user
$principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Authorized Windows agent for Codaki Portable Use'
Start-ScheduledTask -TaskName $TaskName
