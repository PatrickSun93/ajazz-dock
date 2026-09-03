# Make ajazz-dock start automatically at every logon (current user).
#
# Why not a real Windows Service?
# A service runs in session 0, isolated from your desktop -- it could not
# send keystrokes or launch apps into your session. This installs into the
# per-user Startup folder instead: it runs in your session at logon, needs
# no admin rights, and is the correct equivalent for a desktop app.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\install_autostart_windows.ps1
#   powershell -ExecutionPolicy Bypass -File tools\install_autostart_windows.ps1 -PythonExe "C:\path\to\python.exe"
#   powershell -ExecutionPolicy Bypass -File tools\install_autostart_windows.ps1 -Config settings.windows.json
#
# This is the Windows counterpart of tools/install_autostart_macos.sh, and
# takes the same two knobs: which interpreter, and which config.

param(
  [string]$PythonExe = "",
  [string]$Config = "settings.windows.json"
)

$ErrorActionPreference = "Stop"
$proj = (Resolve-Path "$PSScriptRoot\..").Path
$q = [string][char]34   # double-quote

# Same resolution order as start-dock.ps1, so autostart runs the interpreter
# you already start it with by hand.
if (-not $PythonExe) { $PythonExe = $env:PYTHON }
if (-not $PythonExe) {
  $venv = Join-Path $proj ".venv\Scripts\python.exe"
  if (Test-Path $venv) { $PythonExe = $venv }
}
if (-not $PythonExe) { $PythonExe = "$env:USERPROFILE\.conda\envs\ajazzreplace\python.exe" }

if (-not (Test-Path $PythonExe)) {
  throw "Python not found: $PythonExe -- pass -PythonExe with the path to your env python.exe"
}
if (-not (Test-Path (Join-Path $proj $Config))) {
  throw "Config not found: $Config -- pass -Config with a path relative to $proj"
}

# Launcher batch (in the project dir) -- runs the dock, logging to dock.log.
# Note: build each line into its own variable first. Inside an @(...) array
# literal, ',' binds tighter than '+', so unparenthesized concatenations
# would be shredded into separate elements.
$batPath = Join-Path $proj "start-dock.bat"
$batCd  = 'cd /d ' + $q + $proj + $q
# Name the config explicitly rather than leaning on the per-platform default:
# the launcher outlives edits to the repo, and a bat that says what it runs is
# the one thing you can read back months later.
$batRun = $q + $PythonExe + $q + ' -u -m ajazz_dock ' + $q + $Config + $q + ' >> dock.log 2>&1'
Set-Content -Path $batPath -Value @('@echo off', $batCd, $batRun) -Encoding ASCII

# VBS shim placed directly in the Startup folder. Windows runs it at logon;
# it launches the batch fully hidden, so there is no console window flash.
$startup = [Environment]::GetFolderPath('Startup')
$vbsPath = Join-Path $startup "ajazz-dock.vbs"
$vbsLine = 'CreateObject("WScript.Shell").Run ' + ($q * 3) + $batPath + ($q * 3) + ', 0, False'
Set-Content -Path $vbsPath -Value $vbsLine -Encoding ASCII

Write-Output "Installed -- ajazz-dock will start at every logon."
Write-Output "  launcher:  $batPath"
Write-Output "  startup:   $vbsPath"
Write-Output "  config:    $Config"
Write-Output "  log:       $(Join-Path $proj 'dock.log')"
Write-Output "  start now: wscript `"$vbsPath`""
Write-Output "  remove:    powershell -ExecutionPolicy Bypass -File tools\uninstall_autostart_windows.ps1"
