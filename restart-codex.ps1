# Restart the Codex desktop app so it reloads ~/.codex/config.toml.
# Run after setup completes: powershell -ExecutionPolicy Bypass -File .\restart-codex.ps1

$ErrorActionPreference = "Stop"
$main = Get-CimInstance Win32_Process -Filter "Name='ChatGPT.exe'" |
    Where-Object { $_.CommandLine -notmatch '--type=' } |
    Select-Object -First 1

if (-not $main) {
    throw "The Codex desktop app is not running. Start it from the Start menu."
}

$exe = $main.ExecutablePath
if (-not $exe -or $exe -notmatch '\\OpenAI\.Codex_.*\\app\\ChatGPT\.exe$') {
    throw "Refusing to stop an unrecognized ChatGPT.exe process: $exe"
}

Write-Host "Restarting Codex so it reloads MCP configuration..." -ForegroundColor Cyan
Get-Process -Name ChatGPT -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Start-Process -FilePath $exe
Write-Host "Codex restarted." -ForegroundColor Green

