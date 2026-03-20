<# 
.SYNOPSIS
    IssueGuard CLI Setup Script (Windows PowerShell)

.DESCRIPTION
    Creates a PowerShell function that wraps `gh` so that
    `gh issue create` is automatically scanned for secrets.

.NOTES
    Run: .\setup.ps1
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Wrapper = Join-Path $ScriptDir "issueguard.py"

if (-not (Test-Path $Wrapper)) {
    Write-Error "issueguard.py not found at $Wrapper"
    exit 1
}

# Check Python is available (prefer "python" on Windows since "python3" is often a Store stub)
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
        # Verify it actually runs (Windows Store alias stubs exist but don't work)
        try {
            $ver = & $cmd --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $ver -match "Python 3") {
                $python = $cmd
                break
            }
        } catch {
            # Command exists but doesn't work, skip it
        }
    }
}

if (-not $python) {
    Write-Error "Python 3 not found. Please install Python 3 and ensure it's on PATH."
    exit 1
}

Write-Host "Using Python: $python" -ForegroundColor Cyan

# Determine PowerShell profile path
$ProfilePath = $PROFILE.CurrentUserAllHosts
$ProfileDir = Split-Path -Parent $ProfilePath

if (-not (Test-Path $ProfileDir)) {
    New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
}

if (-not (Test-Path $ProfilePath)) {
    New-Item -ItemType File -Path $ProfilePath -Force | Out-Null
}

$Marker = "# >>> IssueGuard CLI wrapper >>>"
$MarkerEnd = "# <<< IssueGuard CLI wrapper <<<"

# Check if already installed
$profileContent = Get-Content $ProfilePath -Raw -ErrorAction SilentlyContinue
if ($profileContent -and $profileContent.Contains($Marker)) {
    Write-Host "IssueGuard CLI wrapper is already installed in $ProfilePath"
    Write-Host "To reinstall, remove the IssueGuard block from $ProfilePath first."
    exit 0
}

$FunctionBlock = @"

$Marker
# Wraps ``gh issue create/edit/comment`` and ``glab issue create/update/note``
# to scan for secrets via IssueGuard.
# To remove, delete this block from your PowerShell profile.
function Invoke-GhIssueGuard {
    `$args_list = `$args

    # Check if this is a ``gh issue create`` or ``gh issue edit`` command
    `$positionals = `$args_list | ForEach-Object { [string]`$_ } | Where-Object { -not `$_.StartsWith('-') }
    `$isIssueGuarded = (`$positionals.Count -ge 2) -and (`$positionals[0] -eq 'issue') -and ((`$positionals[1] -eq 'create') -or (`$positionals[1] -eq 'edit') -or (`$positionals[1] -eq 'comment'))

    if (`$isIssueGuarded) {
        & $python "$Wrapper" @args_list
    } else {
        & (Get-Command gh -CommandType Application | Select-Object -First 1).Source @args_list
    }
}

function Invoke-GlabIssueGuard {
    `$args_list = `$args

    # Check if this is a ``glab issue create``, ``glab issue update``, or ``glab issue note`` command
    `$positionals = `$args_list | ForEach-Object { [string]`$_ } | Where-Object { -not `$_.StartsWith('-') }
    `$isIssueGuarded = (`$positionals.Count -ge 2) -and (`$positionals[0] -eq 'issue') -and ((`$positionals[1] -eq 'create') -or (`$positionals[1] -eq 'update') -or (`$positionals[1] -eq 'note'))

    if (`$isIssueGuarded) {
        & $python "$Wrapper" --glab @args_list
    } else {
        & (Get-Command glab -CommandType Application | Select-Object -First 1).Source @args_list
    }
}

Set-Alias -Name gh -Value Invoke-GhIssueGuard -Scope Global -Force
Set-Alias -Name glab -Value Invoke-GlabIssueGuard -Scope Global -Force
$MarkerEnd
"@

Add-Content -Path $ProfilePath -Value $FunctionBlock -Encoding UTF8

Write-Host ""
Write-Host "IssueGuard CLI wrapper installed in $ProfilePath" -ForegroundColor Green
Write-Host ""
Write-Host "To activate now, run:" -ForegroundColor Yellow
Write-Host "    . `$PROFILE.CurrentUserAllHosts"
Write-Host ""
Write-Host "After that, 'gh issue create' commands will be scanned automatically." -ForegroundColor Cyan
