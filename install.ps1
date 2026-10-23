$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$AppName   = 'TurkceSesliYazma'
$AppDir    = Join-Path $env:LOCALAPPDATA $AppName
$VenvDir   = Join-Path $AppDir 'venv'
$RepoRaw   = 'https://raw.githubusercontent.com/osmnabyram/TextToSpeech-Turkce/main'
$Source    = if ($PSScriptRoot) { Join-Path $PSScriptRoot 'dictation.pyw' } else { '' }
$Target    = Join-Path $AppDir 'dictation.pyw'
$Shortcut  = Join-Path ([Environment]::GetFolderPath('Startup')) 'Sesli Yazma.lnk'
$PyVersion = '3.12.10'
$PyUrl     = "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-amd64.exe"
$Packages  = @('faster-whisper', 'sounddevice', 'keyboard', 'numpy', 'pystray', 'pillow')

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Red }

function Invoke-Checked($exe, [string[]]$argList) {
    & $exe @argList
    if ($LASTEXITCODE -ne 0) { throw "Komut basarisiz ($LASTEXITCODE): $exe $($argList -join ' ')" }
}

function Find-Python312 {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:ProgramFiles 'Python312\python.exe')
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}

if (-not $Source -or -not (Test-Path $Source)) {
    Step 'dictation.pyw GitHub uzerinden indiriliyor'
    $Source = Join-Path $env:TEMP 'dictation.pyw'
    Invoke-WebRequest -Uri "$RepoRaw/dictation.pyw" -OutFile $Source -UseBasicParsing
}

Step 'Python 3.12 kontrol ediliyor'
$Python = Find-Python312
if (-not $Python) {
    $installer = Join-Path $env:TEMP "python-$PyVersion-amd64.exe"
    Write-Host "Python bulunamadi, python.org'dan indiriliyor ($PyVersion)..."
    Invoke-WebRequest -Uri $PyUrl -OutFile $installer -UseBasicParsing
    $sig = Get-AuthenticodeSignature $installer
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        Remove-Item $installer -Force
        throw 'Python yukleyicisinin imzasi dogrulanamadi, kurulum durduruldu.'
    }
    Write-Host 'Python kuruluyor (yonetici izni gerekmez)...'
    $p = Start-Process $installer -Wait -PassThru -ArgumentList @(
        '/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_test=0',
        'Include_tcltk=1', 'Include_pip=1', 'Shortcuts=0'
    )
    Remove-Item $installer -Force
    if ($p.ExitCode -ne 0) { throw "Python kurulumu basarisiz (kod $($p.ExitCode))" }
    $Python = Find-Python312
    if (-not $Python) { throw 'Python kuruldu ama bulunamadi.' }
}
Write-Host "Python: $Python"

Step 'Calisan eski surum kapatiliyor'
Get-Process pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($AppDir, 'OrdinalIgnoreCase') } |
    Stop-Process -Force

Step "Uygulama klasoru hazirlaniyor: $AppDir"
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
if (-not (Test-Path (Join-Path $VenvDir 'Scripts\python.exe'))) {
    Invoke-Checked $Python @('-m', 'venv', $VenvDir)
}
$VenvPython  = Join-Path $VenvDir 'Scripts\python.exe'
$VenvPythonW = Join-Path $VenvDir 'Scripts\pythonw.exe'

Step 'Paketler kuruluyor (birkac dakika surebilir)'
Invoke-Checked $VenvPython @('-m', 'pip', 'install', '--upgrade', '--disable-pip-version-check', 'pip')
Invoke-Checked $VenvPython (@('-m', 'pip', 'install', '--upgrade', '--disable-pip-version-check') + $Packages)

Copy-Item $Source $Target -Force

$ModelSize = 'small'
$m = Select-String -Path $Target -Pattern '^MODEL_SIZE\s*=\s*"([\w.-]+)"' | Select-Object -First 1
if ($m) { $ModelSize = $m.Matches[0].Groups[1].Value }

Step "Ses modeli indiriliyor: $ModelSize (tek seferlik, sonra tamamen offline)"
Invoke-Checked $VenvPython @('-c', "from faster_whisper import WhisperModel; WhisperModel('$ModelSize', device='cpu', compute_type='int8'); print('Model hazir.')")

Step 'Bilgisayar acilisinda otomatik baslatma ekleniyor'
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($Shortcut)
$lnk.TargetPath = $VenvPythonW
$lnk.Arguments = "`"$Target`""
$lnk.WorkingDirectory = $AppDir
$lnk.Description = 'Offline Turkce sesli yazma (Win+H)'
$lnk.Save()

Step 'Baslatiliyor'
Start-Process $Shortcut

Write-Host "`nKurulum tamamlandi. Win+H ile konusmaya basla, tekrar Win+H ile yapistir, ESC ile iptal." -ForegroundColor Green
