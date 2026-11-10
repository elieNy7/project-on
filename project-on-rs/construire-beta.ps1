<#
  Project-On 3.0 bêta - construction de l'installateur.

  Compilation (cargo, release) -> dossier dist\Project-On-3-beta (exécutable, polices, licences)
  -> installateur Inno Setup (installer\Output\Project-On_<version>_Setup.exe).

  Usage :
    powershell -ExecutionPolicy Bypass -File project-on-rs\construire-beta.ps1
    ... -SansCompilation   (reprendre l'exécutable déjà compilé)

  Variable reconnue : ISCC_EXE (Inno Setup), sinon C:\Program Files\Inno Setup 7\ISCC.exe.
  La bêta n'est pas signée : Windows SmartScreen peut demander une confirmation.
#>
param([switch]$SansCompilation)
$ErrorActionPreference = 'Stop'

$rs = $PSScriptRoot
$root = Split-Path $rs -Parent
$cargo = Get-Content (Join-Path $rs 'Cargo.toml') -Raw
if ($cargo -notmatch '(?m)^version\s*=\s*"([^"]+)"') { throw 'Version introuvable dans Cargo.toml' }
$version = $Matches[1]
Write-Host "[INFO] Project-On $version"

if (-not $SansCompilation) {
    Push-Location $rs
    try {
        & cargo build --release -p project-on
        if ($LASTEXITCODE -ne 0) { throw 'La compilation a échoué' }
    } finally { Pop-Location }
}

$dist = Join-Path $rs 'dist\Project-On-3-beta'
if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }
New-Item -ItemType Directory -Force (Join-Path $dist 'assets') | Out-Null
Copy-Item (Join-Path $rs 'target\release\project-on.exe') (Join-Path $dist 'Project-On-3-beta.exe')
# Les polices : celles de l'interface (Inter) et toutes celles que les réglages de projection
# peuvent choisir. Leurs licences (OFL…) sont dans leurs dossiers.
Copy-Item -Recurse (Join-Path $root 'assets\fonts') (Join-Path $dist 'assets\fonts')
New-Item -ItemType Directory -Force (Join-Path $dist 'licences') | Out-Null
Copy-Item (Join-Path $root 'LICENSE.txt') (Join-Path $dist 'licences\Project-On-LICENSE.txt')
Copy-Item (Join-Path $rs 'crates\project-on\LICENSE-lucide.txt') (Join-Path $dist 'licences\LICENSE-lucide.txt')
$size = (Get-ChildItem -Recurse $dist | Measure-Object -Sum Length).Sum / 1MB
Write-Host ("[INFO] dist : {0:N0} Mo" -f $size)

$iscc = $env:ISCC_EXE
if (-not $iscc) { $iscc = 'C:\Program Files\Inno Setup 7\ISCC.exe' }
if (-not (Test-Path $iscc)) { throw "Inno Setup introuvable : $iscc (variable ISCC_EXE)" }
& $iscc "/Q" "/DMyAppVersion=$version" (Join-Path $rs 'installer\project-on-3-beta.iss')
if ($LASTEXITCODE -ne 0) { throw "Inno Setup a échoué ($LASTEXITCODE)" }
$setup = Join-Path $rs "installer\Output\Project-On_${version}_Setup.exe"
Write-Host ("[OK] {0} ({1:N0} Mo)" -f $setup, ((Get-Item $setup).Length / 1MB))
