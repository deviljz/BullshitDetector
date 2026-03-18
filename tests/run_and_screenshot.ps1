param([string]$mode = "analyze", [string]$outfile = "tests/chat_test.png")

$python = ".venv\Scripts\python.exe"
$proc = Start-Process -FilePath $python -ArgumentList "tests/result_window_test.py $mode" -PassThru

Start-Sleep -Seconds 4

# Screenshot: crop directly to window bounds (no MinimizeAll)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$sw = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width
$sh = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height
$bmpFull = New-Object System.Drawing.Bitmap($sw, $sh)
$g = [System.Drawing.Graphics]::FromImage($bmpFull)
$g.CopyFromScreen(0, 0, 0, 0, (New-Object System.Drawing.Size($sw, $sh)))
$g.Dispose()
# Window is at bottom-right corner (1200x860, 20px margin)
$wx = [Math]::Max(0, $sw - 1200 - 40)
$wy = [Math]::Max(0, $sh - 860 - 40)
$crop = $bmpFull.Clone((New-Object System.Drawing.Rectangle($wx, $wy, 1240, 900)), $bmpFull.PixelFormat)
$crop.Save((Join-Path (Get-Location) $outfile))
$bmpFull.Dispose(); $crop.Dispose()

$proc.Kill()
Write-Host "Saved to $outfile"
