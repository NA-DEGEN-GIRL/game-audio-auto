param([int]$Port = 8767, [switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$audioRoot = Split-Path $PSScriptRoot -Parent
$audioUrl = "http://127.0.0.1:$Port"
$audioPython = Join-Path $audioRoot '.venv\Scripts\python.exe'
$audioWork = Join-Path $audioRoot '.work'
New-Item -ItemType Directory -Path $audioWork -Force | Out-Null
$audioReady = $false
try {
    $audioResponse = Invoke-RestMethod "$audioUrl/api/catalog" -TimeoutSec 2
    if ($audioResponse.app -ne 'game-audio-comparison') { throw "Port $Port belongs to another application." }
    $audioReady = $true
} catch {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $Port is already in use and did not return the audio-player identity. Choose another -Port."
    }
}
if (-not $audioReady) {
    $audioProcess = Start-Process -FilePath $audioPython -ArgumentList "-X utf8 scripts/serve_comparison.py --port $Port" -WorkingDirectory $audioRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $audioWork "comparison-$Port.log") -RedirectStandardError (Join-Path $audioWork "comparison-$Port.err.log") -PassThru
    $audioProcess.Id | Set-Content (Join-Path $audioWork "comparison-$Port.pid")
    for ($audioAttempt = 0; $audioAttempt -lt 50; $audioAttempt++) {
        try {
            $audioResponse = Invoke-RestMethod "$audioUrl/api/catalog" -TimeoutSec 1
            if ($audioResponse.app -eq 'game-audio-comparison') { $audioReady = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 100
    }
    if (-not $audioReady) { throw "Player failed to start. Inspect .work/comparison-$Port.err.log." }
}
if (-not $NoOpen) { Start-Process $audioUrl }
Write-Output $audioUrl
