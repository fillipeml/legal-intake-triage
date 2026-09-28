# Installs the sweep in the Windows Task Scheduler (on-premise deployment): every 15 minutes
# on business hours, plus the board sync once an hour. Idempotency makes the cadence safe.
#
# Usage (PowerShell, at the repository root):
#   powershell -ExecutionPolicy Bypass -File scripts\register_scheduled_task.ps1

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $repo "scripts\run_sweep.cmd"
if (-not (Test-Path $runner)) {
    throw "Could not find $runner - run this from the repository root."
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -MultipleInstances IgnoreNew

$sweep = New-ScheduledTaskTrigger -Once -At 08:00 -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Hours 11)
Register-ScheduledTask -TaskName "Legal intake - sweep" -Action (New-ScheduledTaskAction -Execute $runner -Argument "sweep") -Trigger $sweep -Settings $settings -Description "Reads the intake mailbox, triages and sends the cards. Log in logs\intake.log" -Force | Out-Null

$sync = New-ScheduledTaskTrigger -Once -At 08:30 -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Hours 11)
Register-ScheduledTask -TaskName "Legal intake - board sync" -Action (New-ScheduledTaskAction -Execute $runner -Argument "sync-board") -Trigger $sync -Settings $settings -Description "Closes demands whose task was completed on the board" -Force | Out-Null

Write-Host "Tasks installed: sweep every 15 minutes (08:00-19:00), board sync hourly."
Write-Host "Follow:  Get-Content logs\intake.log -Tail 30"
Write-Host "Remove:  Unregister-ScheduledTask -TaskName 'Legal intake - sweep' -Confirm:`$false"
