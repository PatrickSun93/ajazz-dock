# Open ONE new Windows Terminal window, cd to a folder, and run a command there.
# Used by the dock's `shell` actions -- both for per-project Claude Code
# launchers and for anything whose output you need to SEE (devstack status,
# a dev server). A bare `shell` action would swallow all of that.
#
#   powershell -ExecutionPolicy Bypass -File tools\run-in-wt.ps1 D:\devitems
#   powershell -ExecutionPolicy Bypass -File tools\run-in-wt.ps1 D:\devitems "npm run dev"
#
# Windows counterpart of tools/run-in-iterm.sh: same two arguments, same
# default command, same "one new window" behaviour.

param(
  [Parameter(Mandatory = $true)][string]$Directory,
  [string]$Command = "claude --dangerously-skip-permissions"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Directory -PathType Container)) {
  Write-Error "no such dir: $Directory"
  exit 1
}

# PowerShell 7 if it is installed, the shipped 5.1 otherwise -- a stock
# Windows has no pwsh, and the key should still work there.
$shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }

# -NoExit keeps the window open, which is the whole reason this helper exists:
# output you launched the key to read has to stay on screen.
$wt = Get-Command wt.exe -ErrorAction SilentlyContinue
if ($wt) {
  & $wt.Source -d $Directory $shell -NoExit -Command $Command
} else {
  # No Windows Terminal installed: a plain console window still beats nothing.
  Start-Process $shell -ArgumentList @(
    "-NoExit", "-Command", "Set-Location -LiteralPath `"$Directory`"; $Command")
}
