# SolidWorks MCP — Auto Setup Script
# Detects Python & SolidWorks, installs deps, and configures MCP clients.
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
# Enumerate every version-specific ProgID (SldWorks.Application.<major>) and
# resolve each to the .exe it actually launches. This matters on machines with
# more than one SolidWorks installed: the bare "SldWorks.Application" ProgID
# belongs to whichever install registered it last, which is not necessarily
# the newest, so it is never used to decide anything here.
Write-Host "[2/4] Detecting SolidWorks..." -ForegroundColor Yellow

function Get-SolidWorksInstalls {
    $found = @()
    foreach ($major in 19..60) {
        $progid = "SldWorks.Application.$major"
        $clsid = (Get-ItemProperty "Registry::HKEY_CLASSES_ROOT\$progid\CLSID" -ErrorAction SilentlyContinue)."(default)"
        if (-not $clsid) { continue }
        $exe = (Get-ItemProperty "Registry::HKEY_CLASSES_ROOT\CLSID\$clsid\LocalServer32" -ErrorAction SilentlyContinue)."(default)"
        if ($exe) { $exe = $exe.Trim('"') }
        $found += [pscustomobject]@{
            Major  = $major
            Year   = 1992 + $major
            ProgId = $progid
            Exe    = $exe
        }
    }
    return $found | Sort-Object Major -Descending
}

$SWInstalls = Get-SolidWorksInstalls
$SWModern = $SWInstalls | Where-Object { $_.Major -ge 20 } | Select-Object -First 1
$SW2011 = $SWInstalls | Where-Object { $_.Major -eq 19 } | Select-Object -First 1

if ($SWInstalls.Count -gt 0) {
    foreach ($i in $SWInstalls) {
        $tag = if ($i.Major -ge 20) { "-> modern server" } else { "-> sw2011 server" }
        Write-Host ("  Found: SolidWorks {0}  [{1}]  {2}" -f $i.Year, $i.ProgId, $tag) -ForegroundColor Green
        if ($i.Exe) { Write-Host "         $($i.Exe)" -ForegroundColor DarkGray }
    }
    if ($SWInstalls.Count -gt 1) {
        Write-Host "  Multiple versions installed - each server pins its own, so they won't collide." -ForegroundColor DarkGray
    }
} else {
    Write-Host "  WARNING: no SolidWorks ProgID registered; could not auto-detect" -ForegroundColor DarkYellow
}
$SWPath = if ($SWModern -and $SWModern.Exe) { Split-Path -Parent $SWModern.Exe } else { $null }

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
Write-Host "  Which server do you want to configure?" -ForegroundColor Cyan
Write-Host "    Modern SolidWorks (2012+), registered as 'solidworks':"
Write-Host "      1) Claude Desktop"
Write-Host "      2) opencode"
Write-Host "      3) Both"
Write-Host "      7) Codex"
Write-Host "      8) All three clients"
Write-Host "    SolidWorks 2011, registered separately as 'solidworks2011':"
Write-Host "      4) Claude Desktop"
Write-Host "      5) opencode"
Write-Host "      6) Both"
Write-Host "      9) Codex"
Write-Host "     10) All three clients"
Write-Host ""
Write-Host "  The two are separate servers with separate tool calls, so you can" -ForegroundColor DarkGray
Write-Host "  configure both and pick a version per conversation." -ForegroundColor DarkGray
Write-Host ""
$choice = Read-Host "  Enter choice (1/2/3/4/5/6/7/8/9/10)"

# Which server directory and registered name this choice implies.
if ($choice -in @("4", "5", "6", "9", "10")) {
    $ServerDir = "sw2011"
    $ServerName = "solidworks2011"
    $ServerLabel = "SolidWorks 2011"
    if (-not $SW2011) {
        Write-Host "  WARNING: no SolidWorks 2011 install detected - configuring anyway." -ForegroundColor DarkYellow
    }
} else {
    $ServerDir = $null   # resolved per client below (claude/ or opencode/)
    $ServerName = "solidworks"
    $ServerLabel = "modern SolidWorks (2012+)"
    if (-not $SWModern) {
        Write-Host "  WARNING: no SolidWorks 2012+ install detected - configuring anyway." -ForegroundColor DarkYellow
    }
}
$wantClaude = $choice -in @("1", "3", "4", "6", "8", "10")
$wantOpencode = $choice -in @("2", "3", "5", "6", "8", "10")
$wantCodex = $choice -in @("7", "8", "9", "10")

# --- Claude Desktop ---
if ($wantClaude) {
    $dir = if ($ServerDir) { $ServerDir } else { "claude" }
    $serverPy = Join-Path $RepoRoot "$dir\server.py"
    $claudeDir = "$env:APPDATA\Claude"
    $claudeConfig = "$claudeDir\claude_desktop_config.json"

    if (-not (Test-Path $claudeDir)) {
        New-Item -ItemType Directory -Path $claudeDir -Force | Out-Null
    }

    $serverEntry = @{
        command = $Python
        args = @($serverPy)
    }
    $entry = @{ mcpServers = @{ $ServerName = $serverEntry } }

    if (Test-Path $claudeConfig) {
        try {
            $existing = Get-Content $claudeConfig -Raw | ConvertFrom-Json
            if (-not $existing.mcpServers) {
                $existing | Add-Member "mcpServers" @{} -Force
            }
            $existing.mcpServers | Add-Member $ServerName $serverEntry -Force
            $existing | ConvertTo-Json -Depth 10 | Set-Content $claudeConfig -Encoding UTF8
        } catch {
            $entry | ConvertTo-Json -Depth 10 | Set-Content $claudeConfig -Encoding UTF8
        }
        Write-Host "  Claude Desktop: '$ServerName' config updated ($ServerLabel)." -ForegroundColor Green
    } else {
        $entry | ConvertTo-Json -Depth 10 | Set-Content $claudeConfig -Encoding UTF8
        Write-Host "  Claude Desktop: '$ServerName' config created ($ServerLabel)." -ForegroundColor Green
    }
    Write-Host "    Restart Claude Desktop to use the MCP server." -ForegroundColor DarkGray
}

# --- opencode ---
if ($wantOpencode) {
    $dir = if ($ServerDir) { $ServerDir } else { "opencode" }
    $serverPy = Join-Path $RepoRoot "$dir\server.py"
    $serverCwd = Join-Path $RepoRoot $dir
    $ocDir = "$env:USERPROFILE\.config\opencode"
    $ocConfig = "$ocDir\opencode.jsonc"

    if (-not (Test-Path $ocDir)) {
        New-Item -ItemType Directory -Path $ocDir -Force | Out-Null
    }

    $pyEsc = $Python.Replace('\', '\\')
    $svEsc = $serverPy.Replace('\', '\\')
    $cwEsc = $serverCwd.Replace('\', '\\')

    $ocContent = @"
{
  "`$schema": "https://opencode.ai/config.json",
  "mcp": {
    "$ServerName": {
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
        # Exact key match, so "solidworks" does not match "solidworks2011"
        # and the two servers can coexist in one config.
        if ($raw -match ('"' + [regex]::Escape($ServerName) + '"\s*:')) {
            Write-Host "  opencode: '$ServerName' already configured, skipping." -ForegroundColor DarkYellow
        } else {
            $backup = "$ocConfig.bak.$(Get-Date -Format 'yyyyMMddHHmmss')"
            Copy-Item $ocConfig $backup
            $raw = $raw -replace '("mcp"\s*:\s*\{)', "`$1`n    `"$ServerName`": {`n      `"type`": `"local`",`n      `"command`": [`"$pyEsc`",`"$svEsc`"],`n      `"cwd`": `"$cwEsc`",`n      `"enabled`": true`n    },"
            $raw | Set-Content $ocConfig -Encoding UTF8
            Write-Host "  opencode: '$ServerName' added to existing config (backup: $backup)." -ForegroundColor Green
        }
    } else {
        $ocContent | Set-Content $ocConfig -Encoding UTF8
        Write-Host "  opencode: '$ServerName' config created ($ServerLabel)." -ForegroundColor Green
    }
    Write-Host "    Restart opencode to use the MCP server." -ForegroundColor DarkGray
}

# --- Codex ---
if ($wantCodex) {
    $dir = if ($ServerDir) { $ServerDir } else { "claude" }
    $serverPy = Join-Path $RepoRoot "$dir\server.py"
    $codex = (Get-Command codex -ErrorAction SilentlyContinue).Source
    if (-not $codex) {
        Write-Host "  ERROR: Codex CLI not found. Install or open the Codex desktop app first." -ForegroundColor Red
        exit 1
    }

    # Some restricted shells omit these even though USERPROFILE is present.
    if (-not $env:HOME) { $env:HOME = $env:USERPROFILE }
    if (-not $env:HOMEDRIVE) { $env:HOMEDRIVE = Split-Path -Qualifier $env:USERPROFILE }
    if (-not $env:HOMEPATH) { $env:HOMEPATH = $env:USERPROFILE.Substring($env:HOMEDRIVE.Length) }
    if (-not $env:CODEX_HOME) { $env:CODEX_HOME = Join-Path $env:USERPROFILE ".codex" }

    & $codex mcp remove $ServerName 2>$null | Out-Null
    & $codex mcp add $ServerName -- $Python $serverPy
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: Codex could not register '$ServerName'." -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "  Codex: '$ServerName' config updated ($ServerLabel)." -ForegroundColor Green
    Write-Host "    Restart the Codex desktop app to use the MCP server." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "=== Setup complete! ===" -ForegroundColor Green
if ($serverPy) {
    Write-Host "  Registered as: $ServerName  ($ServerLabel)"
    Write-Host "  Server: $serverPy"
} else {
    Write-Host "  No client configured (unrecognized choice '$choice')." -ForegroundColor DarkYellow
}
Write-Host "  Python: $Python"
if ($SWPath) { Write-Host "  SolidWorks: $SWPath" }
Write-Host ""
