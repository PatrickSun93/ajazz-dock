# Launch ajazz-dock on Windows, logging to dock.log.
#
#   .\start-dock.ps1                          # uses settings.windows.json
#   .\start-dock.ps1 other-settings.json
#   .\start-dock.ps1 -PythonExe C:\path\python.exe
#
# The PYTHON environment variable overrides the interpreter too, so the same
# knob works here as in start-dock.sh.
#
# This is the Windows counterpart of start-dock.sh. Both run the dock in the
# foreground with stdout and stderr appended to dock.log.

param(
  [string]$Config = "settings.windows.json",
  [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
$proj = $PSScriptRoot
Set-Location $proj

if (-not $PythonExe) { $PythonExe = $env:PYTHON }
if (-not $PythonExe) { $PythonExe = Join-Path $proj ".venv\Scripts\python.exe" }

if (-not (Test-Path $PythonExe)) {
  Write-Error @"
python not found: $PythonExe
hint: py -m venv .venv; .\.venv\Scripts\pip install -e .
      or pass -PythonExe with the path to your env python.exe
"@
  exit 1
}

if (-not (Test-Path (Join-Path $proj $Config))) {
  Write-Error "config not found: $Config"
  exit 1
}

$log = Join-Path $proj "dock.log"

# Hand the append-redirect to cmd.exe rather than PowerShell's own streams:
# a native process's stderr arrives as ErrorRecord objects, which PowerShell
# would reformat before writing. cmd gives the same byte-for-byte log the
# .sh launcher and the generated start-dock.bat produce.
& cmd.exe /c "`"$PythonExe`" -u -m ajazz_dock `"$Config`" >> `"$log`" 2>&1"
exit $LASTEXITCODE
