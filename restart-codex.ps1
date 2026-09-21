# Restart the Codex desktop app so it reloads ~/.codex/config.toml.
# Run after setup completes: powershell -ExecutionPolicy Bypass -File .\restart-codex.ps1

$ErrorActionPreference = "Stop"
$main = Get-CimInstance Win32_Process -Filter "Name='ChatGPT.exe'" |
    Where-Object { $_.CommandLine -notmatch '--type=' } |
    Select-Object -First 1

if (-not $main) {
    throw "The Codex desktop app is not running. Start it from the Start menu."
}

$appId = Get-StartApps |
    Where-Object { $_.AppID -match '^OpenAI\.Codex_.*!App$' } |
    Select-Object -First 1 -ExpandProperty AppID
if (-not $appId) {
    throw "Could not find the installed Codex app identifier."
}

Write-Host "Restarting Codex so it reloads MCP configuration..." -ForegroundColor Cyan
& taskkill.exe /PID $main.ProcessId /T /F | Out-Null
Start-Sleep -Seconds 2
Start-Process -FilePath explorer.exe -ArgumentList "shell:AppsFolder\$appId"
Write-Host "Codex restarted." -ForegroundColor Green
