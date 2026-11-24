# Capture the real skillget window (used for the README screenshots).
#   powershell -File scripts/capture-window.ps1 -Out shot.png
#   powershell -File scripts/capture-window.ps1 -Click "133,191" -Out installed.png
param(
  [string]$ProcessName = "skillget",
  [string]$Out = "skillget-window.png",
  [string]$Click = ""
)

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NativeWin {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hWnd, ref POINT lpPoint);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, IntPtr extra);
}
"@

[void][NativeWin]::SetProcessDPIAware()

$proc = Get-Process -Name $ProcessName -ErrorAction Stop |
  Where-Object { $_.MainWindowHandle -ne 0 } |
  Select-Object -First 1
if (-not $proc) { throw "no visible window for $ProcessName" }
$h = $proc.MainWindowHandle
[void][NativeWin]::SetForegroundWindow($h)
Start-Sleep -Milliseconds 700

if ($Click) {
  $parts = $Click.Split(",")
  $pt = New-Object NativeWin+POINT
  $pt.X = [int]$parts[0]
  $pt.Y = [int]$parts[1]
  [void][NativeWin]::ClientToScreen($h, [ref]$pt)
  [void][NativeWin]::SetCursorPos($pt.X, $pt.Y)
  Start-Sleep -Milliseconds 200
  [NativeWin]::mouse_event(0x0002, 0, 0, 0, [IntPtr]::Zero)
  [NativeWin]::mouse_event(0x0004, 0, 0, 0, [IntPtr]::Zero)
  Start-Sleep -Milliseconds 1400
}

$rect = New-Object NativeWin+RECT
[void][NativeWin]::GetWindowRect($h, [ref]$rect)
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
$bmp = New-Object System.Drawing.Bitmap $width, $height
$gfx = [System.Drawing.Graphics]::FromImage($bmp)
$gfx.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bmp.Size)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$gfx.Dispose()
$bmp.Dispose()
Write-Output "saved $Out ($width x $height)"
