<#
  Project-On 3.0 bêta - construction de l'installateur.

  Compilation (cargo, release) -> dossier dist\Project-On-3-beta (exécutable, polices, licences,
  base fournie) -> installateur Inno Setup (installer\Output\Project-On_<version>_Setup.exe).

  La base fournie est data\project_on.db à la racine du dépôt, la même que celle de l'installateur
  de la 2.8 (project_on.spec). Au premier lancement, la bêta propose de partir de vos données de la
  2.8 ou de cette base.

  Usage :
    powershell -ExecutionPolicy Bypass -File project-on-rs\construire-beta.ps1
    ... -Bascule           (l'installateur de la bascule : remplace la 2.x, données en place ;
                            à ne publier qu'avec l'accord de l'utilisateur)
    ... -SansCompilation   (reprendre l'exécutable déjà compilé)
    ... -SansBase          (installateur léger, sans la base fournie)

  Variable reconnue : ISCC_EXE (Inno Setup), sinon C:\Program Files\Inno Setup 7\ISCC.exe.
  La bêta n'est pas signée : Windows SmartScreen peut demander une confirmation.
#>
param([switch]$SansCompilation, [switch]$SansBase, [switch]$Bascule)
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
        if ($Bascule) { & cargo build --release -p project-on --features bascule }
        else { & cargo build --release -p project-on }
        if ($LASTEXITCODE -ne 0) { throw 'La compilation a échoué' }
    } finally { Pop-Location }
}

if ($Bascule) { $dist = Join-Path $rs 'dist\Project-On-3'; $exe = 'Project-On.exe'; $iss = 'project-on-3.iss' }
else { $dist = Join-Path $rs 'dist\Project-On-3-beta'; $exe = 'Project-On-3-beta.exe'; $iss = 'project-on-3-beta.iss' }
if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }
New-Item -ItemType Directory -Force (Join-Path $dist 'assets') | Out-Null
Copy-Item (Join-Path $rs 'target\release\project-on.exe') (Join-Path $dist $exe)
# Les polices : celles de l'interface (Inter) et toutes celles que les réglages de projection
# peuvent choisir. Leurs licences (OFL…) sont dans leurs dossiers.
Copy-Item -Recurse (Join-Path $root 'assets\fonts') (Join-Path $dist 'assets\fonts')
# Les fonds fournis (16:9), proposés dans Réglages → Projection, avec leurs crédits.
New-Item -ItemType Directory -Force (Join-Path $dist 'assets\backgrounds') | Out-Null
Copy-Item (Join-Path $root 'assets\backgrounds\*_16x9.png') (Join-Path $dist 'assets\backgrounds')
Copy-Item (Join-Path $root 'assets\backgrounds\CREDITS.txt') (Join-Path $dist 'assets\backgrounds')
# Les Bibles fournies (domaine public), installables depuis « Gérer les Bibles ».
Copy-Item -Recurse (Join-Path $root 'bibles') (Join-Path $dist 'bibles')
# La bibliothèque NDI, comme la 2.8 la livrait (ndi\bin du dépôt, non versionnée) : la sortie NDI
# marche sans installer le runtime NDI. NDI® est une marque de Vizrt NDI AB.
$ndi = Join-Path $root 'ndi\bin\Processing.NDI.Lib.x64.dll'
if (Test-Path $ndi) {
    New-Item -ItemType Directory -Force (Join-Path $dist 'ndi') | Out-Null
    Copy-Item $ndi (Join-Path $dist 'ndi')
} else {
    Write-Warning "Bibliothèque NDI absente ($ndi) : la sortie NDI demandera le runtime NDI."
}
New-Item -ItemType Directory -Force (Join-Path $dist 'licences') | Out-Null
Copy-Item (Join-Path $root 'LICENSE.txt') (Join-Path $dist 'licences\Project-On-LICENSE.txt')
Copy-Item (Join-Path $rs 'crates\project-on\LICENSE-lucide.txt') (Join-Path $dist 'licences\LICENSE-lucide.txt')
if (-not $SansBase) {
    $base = Join-Path $root 'data\project_on.db'
    if (-not (Test-Path $base)) { throw "Base fournie introuvable : $base (ou -SansBase)" }
    New-Item -ItemType Directory -Force (Join-Path $dist 'data') | Out-Null
    Copy-Item $base (Join-Path $dist 'data\project_on.db')
    Write-Host ("[INFO] base fournie : {0:N0} Mo" -f ((Get-Item $base).Length / 1MB))
}
$size = (Get-ChildItem -Recurse $dist | Measure-Object -Sum Length).Sum / 1MB
Write-Host ("[INFO] dist : {0:N0} Mo" -f $size)

$iscc = $env:ISCC_EXE
if (-not $iscc) { $iscc = 'C:\Program Files\Inno Setup 7\ISCC.exe' }
if (-not (Test-Path $iscc)) { throw "Inno Setup introuvable : $iscc (variable ISCC_EXE)" }
& $iscc "/Q" "/DMyAppVersion=$version" (Join-Path $rs "installer\$iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup a échoué ($LASTEXITCODE)" }
if ($Bascule) { $setup = Join-Path $rs "installer\Output\ProjectOn_${version}_Setup.exe" }
else { $setup = Join-Path $rs "installer\Output\Project-On_${version}_Setup.exe" }
Write-Host ("[OK] {0} ({1:N0} Mo)" -f $setup, ((Get-Item $setup).Length / 1MB))
