<#
  Publie Project-On sur GitHub : dépôt + code + Release (installeur) + Pages.

  Prérequis (une seule fois) :
    1. Installer GitHub CLI :   winget install GitHub.cli
    2. Ouvrir un NOUVEAU terminal, puis s'authentifier :   gh auth login
       (choisir GitHub.com -> HTTPS -> Login with a web browser)

  Puis, depuis la racine du projet :
    powershell -ExecutionPolicy Bypass -File tools\publish_github.ps1

  Options :
    -Repo elieNy7/project-on   (par défaut)
    -Private                      (dépôt privé au lieu de public)
#>
param(
  [string]$Repo = "elieNy7/project-on",
  [string]$Version = "1.3.0",
  [switch]$Private
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$installer = Join-Path $root "installer\Output\ProjectOn_${Version}_Setup.exe"

Write-Host "== Project-On — publication GitHub ==" -ForegroundColor Cyan

# 1. Vérifications
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  Write-Host "[X] GitHub CLI (gh) introuvable. Installez-le :  winget install GitHub.cli" -ForegroundColor Red
  exit 1
}
gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "[X] Non authentifié. Lancez d'abord :  gh auth login" -ForegroundColor Red
  exit 1
}
if (-not (Test-Path $installer)) {
  Write-Host "[X] Installeur introuvable : $installer" -ForegroundColor Red
  Write-Host "    Construisez-le d'abord :  build_installer.bat" -ForegroundColor Yellow
  exit 1
}

$visibility = if ($Private) { "--private" } else { "--public" }

# 2. Dépôt distant + push
$exists = $false
gh repo view $Repo 1>$null 2>$null
if ($LASTEXITCODE -eq 0) { $exists = $true }

if (-not $exists) {
  Write-Host "-> Création du dépôt $Repo ($visibility) et push..." -ForegroundColor Green
  gh repo create $Repo $visibility --source=. --remote=origin --push
} else {
  Write-Host "-> Le dépôt $Repo existe déjà. Push de la branche main..." -ForegroundColor Green
  if (-not (git remote 2>$null | Select-String -Quiet "origin")) {
    git remote add origin "https://github.com/$Repo.git"
  }
  git push -u origin main
}

# 3. Release + installeur
$tag = "v$Version"
gh release view $tag --repo $Repo 1>$null 2>$null
if ($LASTEXITCODE -eq 0) {
  Write-Host "-> La release $tag existe : ajout/maj de l'installeur..." -ForegroundColor Green
  gh release upload $tag $installer --repo $Repo --clobber
} else {
  Write-Host "-> Création de la release $tag avec l'installeur..." -ForegroundColor Green
  gh release create $tag $installer `
    --repo $Repo `
    --title "Project-On $Version" `
    --notes-file (Join-Path $root "RELEASE_NOTES.md")
}

# 4. GitHub Pages (site vitrine depuis /docs)
Write-Host "-> Activation de GitHub Pages (branche main, dossier /docs)..." -ForegroundColor Green
try {
  gh api -X POST "repos/$Repo/pages" `
    -H "Accept: application/vnd.github+json" `
    -f "source[branch]=main" -f "source[path]=/docs" 1>$null 2>$null
} catch { }
if ($LASTEXITCODE -ne 0) {
  Write-Host "   (Pages déjà actif, ou à activer manuellement : Settings > Pages > Branch main /docs)" -ForegroundColor Yellow
}

$owner = $Repo.Split('/')[0]
$name  = $Repo.Split('/')[1]
Write-Host ""
Write-Host "== Terminé ! ==" -ForegroundColor Cyan
Write-Host "  Dépôt   : https://github.com/$Repo"
Write-Host "  Release : https://github.com/$Repo/releases/latest"
Write-Host "  Site    : https://$owner.github.io/$name/  (en ligne sous ~1 min)"
