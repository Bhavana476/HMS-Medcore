$ErrorActionPreference = 'Stop'
$backendRoot = $PSScriptRoot
$configFile = Join-Path $backendRoot 'services.local.ps1'
if (Test-Path -LiteralPath $configFile) { . $configFile }
Set-Location -LiteralPath $backendRoot
& (Join-Path $backendRoot '.venv/Scripts/python.exe') (Join-Path $backendRoot 'manage.py') send_appointment_reminders --email --sms
exit $LASTEXITCODE
