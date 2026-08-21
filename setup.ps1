# SolidWorks MCP — Auto Setup Script
# Detects Python & SolidWorks, installs deps, configures Claude Desktop and/or opencode.
# Run: powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "=== SolidWorks MCP Setup ===" -ForegroundColor Cyan
Write-Host ""

# --- Detect Python ---
Write-Host "[1/4] Detecting Python..." -ForegroundColor Yellow

$Python = $null
foreach ($p in @(
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
    "C:\Python313\python.exe", "C:\Python312\python.exe",
    "C:\Python311\python.exe", "C:\Python310\python.exe"
)) {
    if (Test-Path $p) { $Python = $p; break }
}
if (-not $Python) { $Python = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $Python) {
    Write-Host "  ERROR: Python not found. Install Python 3.10+ from https://python.org" -ForegroundColor Red
    exit 1
}
$pyVersion = & $Python --version 2>$null | Out-String
Write-Host "  Found: $Python ($($pyVersion.Trim()))" -ForegroundColor Green

# --- Detect SolidWorks ---
Write-Host "[2/4] Detecting SolidWorks..." -ForegroundColor Yellow

$SWPath = $null
foreach ($ver in 2026..2020) {
    $key = "HKLM:\SOFTWARE\SolidWorks\SolidWorks $ver"
    if (Test-Path $key) {
        $dir = (Get-ItemProperty $key -ErrorAction SilentlyContinue)."Installation Dir"
        if ($dir -and (Test-Path $dir)) { $SWPath = $dir; break }
    }
}
if (-not $SWPath) {
    foreach ($p in @("C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS", "C:\Program Files\SOLIDWORKS\SOLIDWORKS")) {
        if (Test-Path $p) { $SWPath = $p; break }
    }
}
if ($SWPath) { Write-Host "  Found: $SWPath" -ForegroundColor Green }
else { Write-Host "  WARNING: SolidWorks not auto-detected" -ForegroundColor DarkYellow }

# --- Install dependencies ---
Write-Host "[3/4] Installing Python dependencies..." -ForegroundColor Yellow

$requirements = Join-Path $RepoRoot "requirements.txt"
if (-not (Test-Path $requirements)) {
    Write-Host "  ERROR: requirements.txt not found in $RepoRoot" -ForegroundColor Red
    exit 1
}
$null = cmd /c "`"$Python`" -m pip install -r `"$requirements`" --quiet 2>nul"
Write-Host "  Dependencies installed." -ForegroundColor Green

# --- Configure clients ---
Write-Host "[4/4] Configuring MCP clients..." -ForegroundColor Yellow
Write-Host ""
Write-Host "  Which client(s) do you want to configure?" -ForegroundColor Cyan
Write-Host "    1) Claude Desktop"
Write-Host "    2) opencode"
Write-Host "    3) Both"
Write-Host ""
$choice = Read-Host "  Enter choice (1/2/3)"

# --- Claude Desktop ---
if ($choice -eq "1" -or $choice -eq "3") {
    $serverPy = Join-Path $RepoRoot "claude\server.py"
    $claudeDir = "$env:APPDATA\Claude"
    $claudeConfig = "$claudeDir\claude_desktop_config.json"

    if (-not (Test-Path $claudeDir)) {
        New-Item -ItemType Directory -Path $claudeDir -Force | Out-Null
    }

    $entry = @{
        mcpServers = @{
            solidworks = @{
                command = $Python
                args = @($serverPy)
            }
        }
    }

    if (Test-Path $claudeConfig) {
        try {
            $existing = Get-Content $claudeConfig -Raw | ConvertFrom-Json
            if (-not $existing.mcpServers) {
                $existing | Add-Member "mcpServers" @{} -Force
            }
            $existing.mcpServers | Add-Member "solidworks" $entry.mcpServers.solidworks -Force
            $existing | ConvertTo-Json -Depth 10 | Set-Content $claudeConfig -Encoding UTF8
        } catch {
            $entry | ConvertTo-Json -Depth 10 | Set-Content $claudeConfig -Encoding UTF8
        }
        Write-Host "  Claude Desktop: config updated." -ForegroundColor Green
    } else {
        $entry | ConvertTo-Json -Depth 10 | Set-Content $claudeConfig -Encoding UTF8
        Write-Host "  Claude Desktop: config created." -ForegroundColor Green
    }
    Write-Host "    Restart Claude Desktop to use the MCP server." -ForegroundColor DarkGray
}

# --- opencode ---
if ($choice -eq "2" -or $choice -eq "3") {
    $serverPy = Join-Path $RepoRoot "opencode\server.py"
    $ocDir = "$env:USERPROFILE\.config\opencode"
    $ocConfig = "$ocDir\opencode.jsonc"

    if (-not (Test-Path $ocDir)) {
        New-Item -ItemType Directory -Path $ocDir -Force | Out-Null
    }

    $pyEsc = $Python.Replace('\', '\\')
    $svEsc = $serverPy.Replace('\', '\\')
    $cwEsc = $RepoRoot.Replace('\', '\\')

    $ocContent = @"
{
  "`$schema": "https://opencode.ai/config.json",
  "mcp": {
    "solidworks": {
      "type": "local",
      "command": [
        "$pyEsc",
        "$svEsc"
      ],
      "cwd": "$cwEsc",
      "enabled": true
    }
  }
}
"@

    if (Test-Path $ocConfig) {
        $raw = Get-Content $ocConfig -Raw
        if ($raw -match '"solidworks"') {
            Write-Host "  opencode: already configured, skipping." -ForegroundColor DarkYellow
        } else {
            $backup = "$ocConfig.bak.$(Get-Date -Format 'yyyyMMddHHmmss')"
            Copy-Item $ocConfig $backup
            $raw = $raw -replace '("mcp"\s*:\s*\{)', "`$1`n    `"solidworks`": {`n      `"type`": `"local`",`n      `"command`": [`"$pyEsc`",`"$svEsc`"],`n      `"cwd`": `"$cwEsc`",`n      `"enabled`": true`n    }"
            $raw | Set-Content $ocConfig -Encoding UTF8
            Write-Host "  opencode: added to existing config (backup: $backup)." -ForegroundColor Green
        }
    } else {
        $ocContent | Set-Content $ocConfig -Encoding UTF8
        Write-Host "  opencode: config created." -ForegroundColor Green
    }
    Write-Host "    Restart opencode to use the MCP server." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "=== Setup complete! ===" -ForegroundColor Green
Write-Host "  Server: $serverPy"
Write-Host "  Python: $Python"
if ($SWPath) { Write-Host "  SolidWorks: $SWPath" }
Write-Host ""
