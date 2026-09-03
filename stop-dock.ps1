# Stop ajazz-dock and leave the panel dark.
#
#   .\stop-dock.ps1           # graceful: blank the LCD, sleep the device, exit
#   .\stop-dock.ps1 -Force    # kill it outright (leaves the icons lit)
#
# This is the Windows counterpart of stop-dock.sh. The runner listens for
# SIGBREAK, which is what a console CTRL_BREAK delivers; on that it clears
# every key, sleeps the panel, then exits. `taskkill /F` skips all of that and
# leaves the last page's icons glowing on a dock nothing is driving.
#
# Windows has no `kill -TERM` for a console app, so the graceful path attaches
# to the target's console and raises CTRL_BREAK there. If that cannot be done
# (no console, access denied), the script says so and falls back to /F rather
# than pretending it stopped cleanly.

param([switch]$Force)

$ErrorActionPreference = "Continue"

$procs = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
           Where-Object { $_.CommandLine -and $_.CommandLine -match '-m\s+ajazz_dock' })

if ($procs.Count -eq 0) {
  Write-Output "ajazz-dock 没有在跑。"

  # A Startup entry would just restart it at next logon, so say so rather than
  # let the user wonder why it came back.
  $vbs = Join-Path ([Environment]::GetFolderPath('Startup')) "ajazz-dock.vbs"
  if (Test-Path $vbs) {
    Write-Output "注意: 开机自启还装着，下次登录它会把进程拉起来。"
    Write-Output "      要彻底停掉: powershell -ExecutionPolicy Bypass -File tools\uninstall_autostart_windows.ps1"
  }
  exit 0
}

$ids = $procs | ForEach-Object { $_.ProcessId }
Write-Output "找到进程: $($ids -join ' ')"

if ($Force) {
  foreach ($id in $ids) { taskkill /PID $id /F | Out-Null }
  Write-Output "已强制结束（LCD 上的图标会留着）。"
  exit 0
}

if (-not ("Win32.DockConsole" -as [type])) {
  Add-Type -Namespace Win32 -Name DockConsole -MemberDefinition @"
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool AttachConsole(uint dwProcessId);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool FreeConsole();
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool GenerateConsoleCtrlEvent(uint dwCtrlEvent, uint dwProcessGroupId);
"@
}

$CTRL_BREAK = 1
$signalled = $false

foreach ($id in $ids) {
  try {
    [void][Win32.DockConsole]::FreeConsole()
    if ([Win32.DockConsole]::AttachConsole([uint32]$id)) {
      # Ignore the event in this shell, or we would break ourselves with it.
      [void][Win32.DockConsole]::SetConsoleCtrlHandler([IntPtr]::Zero, $true)
      if ([Win32.DockConsole]::GenerateConsoleCtrlEvent([uint32]$CTRL_BREAK, 0)) { $signalled = $true }
      [void][Win32.DockConsole]::FreeConsole()
      [void][Win32.DockConsole]::SetConsoleCtrlHandler([IntPtr]::Zero, $false)
    }
  } catch {
    Write-Output "无法向进程 $id 发送 CTRL_BREAK: $($_.Exception.Message)"
  }
}

if (-not $signalled) {
  Write-Output "没能发出 CTRL_BREAK —— 用 .\stop-dock.ps1 -Force 强制结束（图标会留着）。"
  exit 1
}

# Give it room to blank the panel and sleep the device before checking.
$gone = $false
for ($i = 0; $i -lt 20; $i++) {
  Start-Sleep -Milliseconds 250
  $left = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
            Where-Object { $_.CommandLine -and $_.CommandLine -match '-m\s+ajazz_dock' })
  if ($left.Count -eq 0) { Write-Output "已停止，面板已熄灭。"; $gone = $true; break }
}

if (-not $gone) {
  Write-Output "20 次检查后仍在运行 —— 用 .\stop-dock.ps1 -Force 强制结束。"
  exit 1
}

$vbs = Join-Path ([Environment]::GetFolderPath('Startup')) "ajazz-dock.vbs"
if (Test-Path $vbs) {
  Write-Output "注意: 开机自启还装着，下次登录它会重新拉起进程。"
  Write-Output "      要彻底停掉: powershell -ExecutionPolicy Bypass -File tools\uninstall_autostart_windows.ps1"
}
