$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$npmPath = (Get-Command npm.cmd -ErrorAction Stop).Source
if (!(Test-Path -LiteralPath $pythonPath)) {
    throw 'Backend environment is missing. Follow the backend setup in README.md first.'
}
if (!(Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\node_modules'))) {
    throw 'Frontend dependencies are missing. Run npm install in the frontend folder first.'
}
function Test-LocalPage([string]$Url) {
    try { return (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 }
    catch { return $false }
}
if (!(Test-LocalPage 'http://127.0.0.1:8000/api/public-directory/')) {
    Start-Process -FilePath $pythonPath -ArgumentList 'manage.py','runserver','127.0.0.1:8000','--noreload' -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot 'backend-active.log') -RedirectStandardError (Join-Path $projectRoot 'backend-active.err.log')
}
if (!(Test-LocalPage 'http://localhost:5173/')) {
    Start-Process -FilePath $npmPath -ArgumentList 'run','dev','--','--host','127.0.0.1','--port','5173','--strictPort' -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot 'frontend-active.log') -RedirectStandardError (Join-Path $projectRoot 'frontend-active.err.log')
}
for ($attempt = 0; $attempt -lt 15; $attempt++) {
    if ((Test-LocalPage 'http://127.0.0.1:8000/api/public-directory/') -and (Test-LocalPage 'http://localhost:5173/')) {
        Write-Host 'MedCore is ready: http://localhost:5173/'
        Start-Process 'http://localhost:5173/'
        exit 0
    }
    Start-Sleep -Seconds 1
}
throw 'Servers did not become ready. Check backend-active.err.log and frontend-active.err.log in the project folder.'
