# build.ps1 - собирает MicToggle (PyInstaller) и установщик MicToggle-Setup-<ver>.exe (NSIS)
#
#   .\build.ps1              # версия берётся из VERSION
#   .\build.ps1 -Version 1.0.1
#
# Требуется: .venv с зависимостями (requirements.txt) и NSIS 3 в Program Files (x86).
# Результат: dist\MicToggle\MicToggle.exe и dist\MicToggle-Setup-<ver>.exe

[CmdletBinding()]
param([string]$Version)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$root   = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$nsis   = "${env:ProgramFiles(x86)}\NSIS\makensis.exe"

if (-not (Test-Path $python)) {
    throw "нет .venv: py -3.12 -m venv .venv && .venv\Scripts\pip install -r requirements.txt"
}
if (-not (Test-Path $nsis)) {
    throw "не найден NSIS: $nsis"
}

if (-not $Version) {
    $Version = (Get-Content (Join-Path $root 'VERSION') -Raw).Trim()
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "версия должна быть вида 1.2.3, получено '$Version'"
}
Write-Host "MicToggle $Version" -ForegroundColor Cyan

# --- PyInstaller -----------------------------------------------------------
& $python -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ставлю pyinstaller..." -ForegroundColor DarkGray
    & $python -m pip install --quiet pyinstaller
}

$buildDir = Join-Path $root 'build'
New-Item -ItemType Directory -Force $buildDir | Out-Null

$parts = $Version.Split('.')
$v = "$($parts[0]), $($parts[1]), $($parts[2]), 0"
$versionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($v),
    prodvers=($v),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'MicToggle'),
        StringStruct('FileDescription', 'MicToggle - микрофон в системном трее'),
        StringStruct('FileVersion', '${Version}.0'),
        StringStruct('InternalName', 'MicToggle'),
        StringStruct('LegalCopyright', 'MIT License, 2026'),
        StringStruct('OriginalFilename', 'MicToggle.exe'),
        StringStruct('ProductName', 'MicToggle'),
        StringStruct('ProductVersion', '${Version}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@
Set-Content -Path (Join-Path $buildDir 'version_info.txt') -Value $versionInfo -Encoding UTF8

Write-Host "собираю exe..." -ForegroundColor DarkGray
Push-Location $root
try {
    & $python -m PyInstaller --noconfirm --clean (Join-Path $root 'MicToggle.spec')
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller завершился с кодом $LASTEXITCODE" }
} finally {
    Pop-Location
}

$appExe = Join-Path $root 'dist\MicToggle\MicToggle.exe'
if (-not (Test-Path $appExe)) { throw "не собрался $appExe" }
Copy-Item (Join-Path $root 'VERSION') (Join-Path $root 'dist\MicToggle\VERSION') -Force
Write-Host ("exe: {0:N1} МБ" -f ((Get-ChildItem (Join-Path $root 'dist\MicToggle') -Recurse -File |
    Measure-Object Length -Sum).Sum / 1MB)) -ForegroundColor DarkGray

# --- NSIS ------------------------------------------------------------------
Write-Host "собираю установщик..." -ForegroundColor DarkGray
& $nsis "/DVERSION=$Version" "/DAPPROOT=$root" (Join-Path $root 'installer\MicToggle.nsi')
if ($LASTEXITCODE -ne 0) { throw "NSIS завершился с кодом $LASTEXITCODE" }

$setup = Join-Path $root "dist\MicToggle-Setup-$Version.exe"
if (-not (Test-Path $setup)) { throw "не собрался $setup" }

$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
Set-Content -Path "$setup.sha256" -Value "$hash  MicToggle-Setup-$Version.exe" -Encoding ASCII
Write-Host ("установщик: {0} ({1:N1} МБ)" -f (Split-Path $setup -Leaf),
    ((Get-Item $setup).Length / 1MB)) -ForegroundColor Green
Write-Host "SHA-256: $hash" -ForegroundColor DarkGray