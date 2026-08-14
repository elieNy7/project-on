<#
  Publish Project-On code, release assets, and GitHub Pages.

  Usage:
    powershell -ExecutionPolicy Bypass -File tools\publish_github.ps1
    powershell -ExecutionPolicy Bypass -File tools\publish_github.ps1 -Version 1.5.2

  Requirements: GitHub CLI installed and authenticated with `gh auth login`.
  This file intentionally uses ASCII text so Windows PowerShell 5.1 can parse
  it correctly without relying on a UTF-8 BOM.
#>
param(
  [string]$Repo = "elieNy7/project-on",
  [string]$Version = "1.5.2",
  [switch]$Private
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$installer = Join-Path $root "installer\Output\ProjectOn_${Version}_Setup.exe"
$portable = Join-Path $root "installer\Output\ProjectOn_${Version}_Portable.zip"
$releaseNotes = Join-Path $root "RELEASE_NOTES.md"
$tag = "v$Version"

Write-Host "== Project-On GitHub publication ==" -ForegroundColor Cyan

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw "GitHub CLI is missing. Install it with: winget install GitHub.cli"
}

gh auth status 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
  throw "GitHub CLI is not authenticated. Run: gh auth login"
}

if (-not (Test-Path -LiteralPath $installer)) {
  throw "Installer not found: $installer"
}

$assets = @($installer)
if (Test-Path -LiteralPath $portable) {
  $assets += $portable
}

gh repo view $Repo 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
  $visibility = if ($Private) { "--private" } else { "--public" }
  gh repo create $Repo $visibility --source=. --remote=origin
  if ($LASTEXITCODE -ne 0) { throw "Repository creation failed." }
}

$branch = (git branch --show-current).Trim()
if (-not $branch) { throw "Unable to determine the current Git branch." }
git push -u origin $branch
if ($LASTEXITCODE -ne 0) { throw "Git push failed." }

gh release view $tag --repo $Repo 1>$null 2>$null
if ($LASTEXITCODE -eq 0) {
  gh release upload $tag @assets --repo $Repo --clobber
} else {
  gh release create $tag @assets --repo $Repo --title "Project-On $Version" --notes-file $releaseNotes
}
if ($LASTEXITCODE -ne 0) { throw "GitHub release publication failed." }

gh api -X POST "repos/$Repo/pages" -H "Accept: application/vnd.github+json" -f "source[branch]=main" -f "source[path]=/docs" 1>$null 2>$null

$owner = $Repo.Split('/')[0]
$name = $Repo.Split('/')[1]
Write-Host "Publication complete." -ForegroundColor Green
Write-Host "Repository: https://github.com/$Repo"
Write-Host "Release:    https://github.com/$Repo/releases/tag/$tag"
Write-Host "Website:    https://$owner.github.io/$name/"
