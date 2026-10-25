# Run once to schedule reminders every 15 minutes while this Windows user is logged in.
$ErrorActionPreference = 'Stop'
$taskPython = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '.venv/Scripts/python.exe')).Path
$taskManage = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'manage.py')).Path
$taskName = 'MedCore-HMS-Calendar-Reminders'
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and $existing.Actions.Arguments -notlike ('*' + $taskManage + '*')) { throw 'An unrelated task has this name. Choose a different task name.' }
$taskAction = New-ScheduledTaskAction -Execute $taskPython -Argument ('"' + $taskManage + '" send_appointment_reminders --email --sms') -WorkingDirectory $PSScriptRoot
$taskTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(15) -RepetitionInterval (New-TimeSpan -Minutes 15)
$taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$taskPrincipal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $taskTrigger -Settings $taskSettings -Principal $taskPrincipal -Description 'Idempotent MedCore appointment reminders. External delivery requires configured providers and opt-in.' -Force | Select-Object TaskName,State
