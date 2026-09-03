# Remove the ajazz-dock logon entry created by install_autostart_windows.ps1.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\uninstall_autostart_windows.ps1

$vbsPath = Join-Path ([Environment]::GetFolderPath('Startup')) "ajazz-dock.vbs"

if (Test-Path $vbsPath) {
  Remove-Item $vbsPath -Force
  Write-Output "Removed startup entry: $vbsPath"
  Write-Output "(ajazz-dock will no longer start at logon; a running instance keeps going until you close it.)"
} else {
  Write-Output "No startup entry found -- nothing to do."
}
