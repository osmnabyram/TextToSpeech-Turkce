$ErrorActionPreference = 'Stop'

$AppDir   = Join-Path $env:LOCALAPPDATA 'TurkceSesliYazma'
$Shortcut = Join-Path ([Environment]::GetFolderPath('Startup')) 'Sesli Yazma.lnk'
$ModelDir = Join-Path $env:USERPROFILE '.cache\huggingface\hub'

Get-Process pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($AppDir, 'OrdinalIgnoreCase') } |
    Stop-Process -Force
Start-Sleep -Seconds 1

if (Test-Path $Shortcut) { Remove-Item $Shortcut -Force }
if (Test-Path $AppDir)   { Remove-Item $AppDir -Recurse -Force }

$answer = Read-Host 'Indirilen ses modelleri de silinsin mi? (E/H)'
if ($answer -match '^[eEyY]') {
    Get-ChildItem $ModelDir -Directory -Filter 'models--Systran--faster-whisper-*' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
}

Write-Host 'Sesli Yazma kaldirildi. (Python yerinde birakildi.)' -ForegroundColor Green
