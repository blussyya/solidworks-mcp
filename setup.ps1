# SolidWorks MCP installer (Windows PowerShell 5.1+)
# Detects installed Python, SolidWorks and MCP clients. Backs up existing configs.
param(
    [ValidateSet("Auto","Modern","2011","Both")][string]$Server = "Auto",
    [string[]]$Clients = @(),
    [switch]$AllClients
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$SupportedClients = @("claude-desktop","claude-code","codex","cursor","opencode","windsurf","gemini","vscode")
function Note($message) { Write-Host "[+] $message" -ForegroundColor Cyan }
function Warn($message) { Write-Warning $message }
function Fail($message) { throw $message }
function ExistingCommand($name) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    return $null
}
function Resolve-Python {
    $candidates = New-Object System.Collections.ArrayList
    $venv = Join-Path $Root ".venv\Scripts\python.exe"
    # Only use a previous venv if it is valid; don't create a venv inside itself.
    if (Test-Path $venv) { [void]$candidates.Add($venv) }
    $py = ExistingCommand "py.exe"
    if ($py) {
        $listing = & $py -0p 2>$null
        foreach ($line in $listing) {
            if ($line -match '([A-Za-z]:\\[^\r\n]*?python(?:\.exe)?)\s*$') {
                [void]$candidates.Add($Matches[1])
            }
        }
    }
    foreach ($name in @("python.exe","python3.exe")) {
        $path = ExistingCommand $name
        if ($path) { [void]$candidates.Add($path) }
    }
    $bases = @("$env:LOCALAPPDATA\Programs\Python","C:\","$env:ProgramFiles\Python")
    foreach ($base in $bases) {
        if (-not (Test-Path $base)) { continue }
        foreach ($dir in @(Get-ChildItem $base -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^Python3\d+' })) {
            $exe = Join-Path $dir.FullName "python.exe"
            if (Test-Path $exe) { [void]$candidates.Add($exe) }
        }
    }
    $found = @()
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        try {
            $result = & $candidate -c "import sys; print('%s.%s.%s|%s|%s' % (*sys.version_info[:3], sys.executable, sys.platform))" 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $result) { continue }
            $parts = $result.Trim().Split("|")
            if ($parts[2] -ne "win32") { continue }
            $version = [version]$parts[0]
            if ($version -lt [version]"3.10") {
                Warn "Python $version at $($parts[1]) is too old. Python 3.10+ is required."
                continue
            }
            $found += [pscustomobject]@{ Version=$version; Path=$parts[1] }
        } catch { Warn "Could not run Python candidate $candidate" }
    }
    if (-not $found) { Fail "No compatible Python found. Install Python 3.10+ from https://www.python.org/downloads/windows/ and rerun setup.bat." }
    $best = $found | Sort-Object Version -Descending | Select-Object -First 1
    Note "Python $($best.Version): $($best.Path)"
    return $best.Path
}
function Get-SolidWorks {
    $installs = @()
    foreach ($major in 19..60) {
        $id = "SldWorks.Application.$major"
        $key = "Registry::HKEY_CLASSES_ROOT\$id\CLSID"
        $clsid = (Get-ItemProperty $key -ErrorAction SilentlyContinue)."(default)"
        if ($clsid) {
            $installs += [pscustomobject]@{ Major=$major; Year=(1992+$major); ProgId=$id }
        }
    }
    return @($installs)
}
function Backup-Config($path) {
    if (Test-Path $path) {
        $backup = "$path.bak.$(Get-Date -Format 'yyyyMMddHHmmssfff')"
        Copy-Item -LiteralPath $path -Destination $backup -ErrorAction Stop
        Note "Backed up $path"
    }
}
function Set-JsonConfig($path,$section,$name,$entry) {
    $dir = Split-Path -Parent $path
    if (-not (Test-Path $dir)) { New-Item $dir -ItemType Directory -Force | Out-Null }
    $config = [pscustomobject]@{}
    if (Test-Path $path) {
        $raw = Get-Content -LiteralPath $path -Raw
        if ($raw.Trim()) {
            try { $config = $raw | ConvertFrom-Json -ErrorAction Stop }
            catch {
                Warn "Skipped $path: cannot safely parse existing JSON/JSONC. Existing settings were not changed. Remove comments manually or configure this client yourself."
                return $false
            }
        }
    }
    if (-not ($config.PSObject.Properties.Name -contains $section)) {
        $config | Add-Member -NotePropertyName $section -NotePropertyValue ([pscustomobject]@{})
    }
    if ($null -eq $config.$section) { $config.$section = [pscustomobject]@{} }
    $config.$section | Add-Member -NotePropertyName $name -NotePropertyValue $entry -Force
    $json = $config | ConvertTo-Json -Depth 50
    # Serialize before backup/write; preserve original if any step fails.
    Backup-Config $path
    $temp = "$path.tmp.$([guid]::NewGuid().ToString('N'))"
    try {
        [System.IO.File]::WriteAllText($temp,$json,(New-Object System.Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $temp -Destination $path -Force
    } finally { if (Test-Path $temp) { Remove-Item $temp -Force } }
    Note "Configured $name in $path"
    return $true
}
function Detect-Clients {
    $found = @()
    if ((Test-Path "$env:APPDATA\Claude") -or (ExistingCommand "claude")) {
        if (Test-Path "$env:APPDATA\Claude") { $found += "claude-desktop" }
    }
    if (ExistingCommand "claude") { $found += "claude-code" }
    if ((ExistingCommand "codex") -or (Test-Path "$env:USERPROFILE\.codex") -or (Test-Path "$env:LOCALAPPDATA\Programs\Codex") -or (Test-Path "$env:LOCALAPPDATA\Packages\OpenAI.Codex_2p2nqsd0c76g0")) { $found += "codex" }
    if ((ExistingCommand "cursor") -or (Test-Path "$env:APPDATA\Cursor") -or (Test-Path "$env:USERPROFILE\.cursor")) { $found += "cursor" }
    if ((ExistingCommand "opencode") -or (Test-Path "$env:USERPROFILE\.config\opencode")) { $found += "opencode" }
    if ((Test-Path "$env:USERPROFILE\.codeium\windsurf") -or (Test-Path "$env:APPDATA\Windsurf")) { $found += "windsurf" }
    if ((ExistingCommand "gemini") -or (Test-Path "$env:USERPROFILE\.gemini")) { $found += "gemini" }
    if ((ExistingCommand "code") -or (Test-Path "$env:APPDATA\Code\User")) { $found += "vscode" }
    return @($found | Select-Object -Unique)
}
function Register-Client($client,$name,$python,$serverPath) {
    $args = @($serverPath)
    $entry = [pscustomobject]@{ command=$python; args=$args }
    switch ($client) {
        "claude-desktop" {
            return Set-JsonConfig "$env:APPDATA\Claude\claude_desktop_config.json" "mcpServers" $name $entry
        }
        "cursor" {
            return Set-JsonConfig "$env:USERPROFILE\.cursor\mcp.json" "mcpServers" $name $entry
        }
        "windsurf" {
            return Set-JsonConfig "$env:USERPROFILE\.codeium\windsurf\mcp_config.json" "mcpServers" $name $entry
        }
        "gemini" {
            return Set-JsonConfig "$env:USERPROFILE\.gemini\settings.json" "mcpServers" $name $entry
        }
        "vscode" {
            $vscodeEntry = [pscustomobject]@{ type="stdio"; command=$python; args=$args }
            return Set-JsonConfig "$env:APPDATA\Code\User\mcp.json" "servers" $name $vscodeEntry
        }
        "opencode" {
            $ocdir = "$env:USERPROFILE\.config\opencode"
            $ocfile = Join-Path $ocdir "opencode.json"
            $jsonc = Join-Path $ocdir "opencode.jsonc"
            if ((Test-Path $jsonc) -and -not (Test-Path $ocfile)) { $ocfile = $jsonc }
            $ocentry = [pscustomobject]@{ type="local"; command=@($python,$serverPath); enabled=$true }
            return Set-JsonConfig $ocfile "mcp" $name $ocentry
        }
        "codex" {
            $codex = ExistingCommand "codex"
            if (-not $codex) {
                Warn "Codex detected, but CLI is not on PATH. Skipping: install/expose Codex CLI, then rerun setup. No config was overwritten."
                return $false
            }
            # Codex's own CLI edits TOML without discarding unrelated configuration.
            & $codex mcp get $name *> $null
            if ($LASTEXITCODE -eq 0) {
                & $codex mcp remove $name
                if ($LASTEXITCODE -ne 0) { Warn "Could not replace existing Codex entry $name"; return $false }
            }
            & $codex mcp add $name -- $python $serverPath
            if ($LASTEXITCODE -ne 0) { Warn "Codex registration failed for $name"; return $false }
            Note "Configured $name for Codex"
            return $true
        }
        "claude-code" {
            $claude = ExistingCommand "claude"
            if (-not $claude) { Warn "Claude Code CLI not found; skipped"; return $false }
            & $claude mcp remove $name -s user *> $null
            & $claude mcp add --scope user --transport stdio $name -- $python $serverPath
            if ($LASTEXITCODE -ne 0) { Warn "Claude Code registration failed for $name"; return $false }
            Note "Configured $name for Claude Code"
            return $true
        }
    }
    Warn "Unknown client: $client"
    return $false
}
try {
    if ($env:OS -ne "Windows_NT") { Fail "This installer requires Windows (SolidWorks COM)." }
    Note "SolidWorks MCP setup: $Root"
    $python = Resolve-Python
    $venv = Join-Path $Root ".venv"
    $venvPython = Join-Path $venv "Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Note "Creating isolated Python environment in .venv"
        & $python -m venv $venv
        if ($LASTEXITCODE -ne 0) { Fail "Failed to create .venv. Ensure Python venv is installed." }
    }
    $venvVersion = & $venvPython -c "import sys; print('%s.%s' % sys.version_info[:2])"
    if ($LASTEXITCODE -ne 0 -or [version]$venvVersion -lt [version]"3.10") {
        Fail "Existing .venv has an incompatible/broken Python. Back it up or remove it and rerun setup."
    }
    Note "Installing requirements in isolated .venv"
    & $venvPython -m pip install -r (Join-Path $Root "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Fail "Dependency installation failed; check pip output above." }
    & $venvPython -c "from mcp.server.fastmcp import FastMCP; import win32com.client"
    if ($LASTEXITCODE -ne 0) { Fail "MCP or pywin32 import test failed. See output above." }
    $installs = @(Get-SolidWorks)
    foreach ($sw in $installs) { Note "SolidWorks $($sw.Year) ($($sw.ProgId)) detected" }
    if (-not $installs.Count) { Warn "No versioned SolidWorks COM registration detected; server registration can proceed, but connection may fail." }
    if ($Server -eq "Auto") {
        if ($installs.Count -eq 0) { $Server = "Modern"; Warn "Defaulting to modern server; verify your SolidWorks version." }
        elseif (($installs | Where-Object Major -eq 19).Count -gt 0 -and ($installs | Where-Object Major -ge 20).Count -gt 0) { $Server = "Both" }
        elseif (($installs | Where-Object Major -eq 19).Count -gt 0) { $Server = "2011" }
        else { $Server = "Modern" }
    }
    $targets = @()
    if ($Server -in @("Modern","Both")) { $targets += [pscustomobject]@{ Name="solidworks"; Path=(Join-Path $Root "server.py") } }
    if ($Server -in @("2011","Both")) { $targets += [pscustomobject]@{ Name="solidworks2011"; Path=(Join-Path $Root "sw2011\server.py") } }
    $selected = @()
    if ($AllClients) { $selected = $SupportedClients }
    elseif ($Clients.Count -gt 0) { $selected = $Clients }
    else { $selected = @(Detect-Clients) }
    $selected = @($selected | Select-Object -Unique)
    if (-not $selected.Count) {
        Warn "No known MCP clients detected. Install a client and rerun, or use -Clients cursor,codex etc."
        exit 0
    }
    foreach ($client in $selected) { if ($client -notin $SupportedClients) { Fail "Unknown client '$client'. Choose from: $($SupportedClients -join ', ')" } }
    Note "Selected clients: $($selected -join ', ')"
    foreach ($target in $targets) {
        if (-not (Test-Path $target.Path)) { Fail "Server file missing: $($target.Path)" }
        foreach ($client in $selected) {
            try { [void](Register-Client $client $target.Name $venvPython $target.Path) }
            catch { Warn "Failed $client / $($target.Name): $_" }
        }
    }
    Note "Finished. Restart configured clients and enable their MCP servers if prompted."
} catch {
    Write-Host "[ERROR] $_" -ForegroundColor Red
    exit 1
}
