# forktex installer — Windows (PowerShell 5.1+ / PowerShell 7)
#
# Usage:
#     iwr -useb install.forktex.com/ps | iex
#
# Finds a Python >= 3.14 via the `py` launcher (preferred) or `python.exe`
# on PATH and hands control to the inlined `_install_core.py`.

$ErrorActionPreference = "Stop"

function Resolve-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        # The `py` launcher supports `-3` to prefer the latest 3.x.
        return @{ Exe = $py.Source; Args = @("-3") }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @{ Exe = $python.Source; Args = @() } }
    $python3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($python3) { return @{ Exe = $python3.Source; Args = @() } }
    return $null
}

$pythonInfo = Resolve-Python
if (-not $pythonInfo) {
    Write-Host "forktex installer: Python is required (>= 3.14)." -ForegroundColor Red
    Write-Host "  install:  winget install Python.Python.3.14"
    Write-Host "  or visit: https://www.python.org/downloads/windows/"
    exit 2
}

# Inlined core — build_installers.py replaces this block at publish time.
$core = @'
# @@INSTALL_CORE@@
# Fallback: fetch from the hosted installer when the inliner wasn't run.
import os, sys, urllib.request
url = os.environ.get("FORKTEX_INSTALL_CORE_URL", "https://install.forktex.com/_install_core.py")
exec(urllib.request.urlopen(url).read().decode("utf-8"))
'@

# Pipe the core into Python via stdin.
$core | & $pythonInfo.Exe @($pythonInfo.Args) -
exit $LASTEXITCODE
