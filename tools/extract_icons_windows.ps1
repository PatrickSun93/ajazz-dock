# Extract high-res app icons from .exe files into icons/.
# Run with Windows PowerShell 5.1 (has System.Drawing in the GAC):
#   powershell.exe -ExecutionPolicy Bypass -File tools\extract_icons_windows.ps1
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Drawing;
using System.Runtime.InteropServices;
public class IconX {
  [DllImport("user32.dll", CharSet=CharSet.Auto)]
  public static extern int PrivateExtractIcons(string f, int idx, int cx, int cy, IntPtr[] h, int[] id, int n, int flags);
  [DllImport("user32.dll")] public static extern bool DestroyIcon(IntPtr h);
  public static bool Save(string exe, string outPng, int size) {
    IntPtr[] h = new IntPtr[1]; int[] id = new int[1];
    int got = PrivateExtractIcons(exe, 0, size, size, h, id, 1, 0);
    if (got < 1 || h[0] == IntPtr.Zero) return false;
    using (Icon ico = Icon.FromHandle(h[0]))
    using (Bitmap bmp = ico.ToBitmap()) { bmp.Save(outPng, System.Drawing.Imaging.ImageFormat.Png); }
    DestroyIcon(h[0]); return true;
  }
}
'@ -ReferencedAssemblies System.Drawing

$icons = Join-Path $PSScriptRoot '..\icons'
$jobs = [ordered]@{
  'antigravity.png' = 'C:\Users\peido\AppData\Local\Programs\Antigravity\Antigravity.exe'
  'vscode.png'      = 'C:\Users\peido\AppData\Local\Programs\Microsoft VS Code\Code.exe'
  'obsidian.png'    = 'C:\Users\peido\AppData\Local\Programs\obsidian\Obsidian.exe'
  'docker.png'      = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
  'gitbash.png'     = 'C:\Program Files\Git\git-bash.exe'
  'notepadpp.png'   = 'C:\Program Files\Notepad++\notepad++.exe'
  'terminal.png'    = 'C:\Users\peido\AppData\Local\Microsoft\WindowsApps\wt.exe'
  'explorer.png'    = 'C:\Windows\explorer.exe'
  'taskmgr.png'     = 'C:\Windows\System32\Taskmgr.exe'
}
foreach ($name in $jobs.Keys) {
  $exe = $jobs[$name]; $out = Join-Path $icons $name
  if (-not (Test-Path $exe)) { Write-Output "SKIP (no exe)  $name"; continue }
  $ok = $false
  foreach ($sz in 256,128,64,48,32) {
    if ([IconX]::Save($exe, $out, $sz)) { $ok = $true; Write-Output "OK  $name  @${sz}px"; break }
  }
  if (-not $ok) { Write-Output "FAIL  $name" }
}
