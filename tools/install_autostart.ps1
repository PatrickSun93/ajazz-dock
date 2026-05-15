# Make ajazz-dock start automatically at every logon (current user).
#
# Why not a real Windows Service?
# A service runs in session 0, isolated from your desktop -- it could not
# send keystrokes or launch apps into your session. This installs into the
# per-user Startup folder instead: it runs in your session at logon, needs
# no admin rights, and is the correct equivalent for a desktop app.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\install_autostart.ps1
#   powershell -ExecutionPolicy Bypass -File tools\install_autostart.ps1 -PythonExe "C:\path\to\python.exe"

param(
  [string]$PythonExe = "$env:USERPROFILE\.conda\envs\ajazzreplace\python.exe"
)

$ErrorActionPreference = "Stop"
$proj = (Resolve-Path "$PSScriptRoot\..").Path
$q = [string][char]34   # double-quote

if (-not (Test-Path $PythonExe)) {
  throw "Python not found: $PythonExe -- pass -PythonExe with the path to your env python.exe"
}

# Launcher batch (in the project dir) -- runs the dock, logging to dock.log.
# Note: build each line into its own variable first. Inside an @(...) array
# literal, ',' binds tighter than '+', so unparenthesized concatenations
# would be shredded into separate elements.
$batPath = Join-Path $proj "start-dock.bat"
$batCd  = 'cd /d ' + $q + $proj + $q
$batRun = $q + $PythonExe + $q + ' -u -m ajazz_dock >> dock.log 2>&1'
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
Write-Output "  log:       $(Join-Path $proj 'dock.log')"
Write-Output "  start now: wscript `"$vbsPath`""
Write-Output "  remove:    powershell -ExecutionPolicy Bypass -File tools\uninstall_autostart.ps1"
