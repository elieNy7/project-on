param(
  [string]$Destination = "./ndi",
  [switch]$Install,
  [string]$RedistUrl = "https://ndi.link/NDIRedistV6",
  # Sujet attendu du signataire Authenticode de l'installeur NDI (regex,
  # insensible a la casse). Par defaut : NDI / NewTek / Vizrt.
  [string]$ExpectedSigner = "NDI|NewTek|Vizrt"
)

$ErrorActionPreference = 'Stop'

function Find-NdiRuntimeDllFolder {
  $candidates = @(
    "$env:ProgramFiles\NDI",
    "$env:ProgramFiles\NewTek\NDI",
    "$env:ProgramFiles\NDI\NDI 6 Runtime",
    "$env:ProgramFiles\NDI\NDI 5 Runtime",
    "$env:ProgramFiles(x86)\NDI",
    "$env:ProgramFiles(x86)\NewTek\NDI"
  ) | Where-Object { $_ -and (Test-Path $_) }

  foreach ($base in $candidates) {
    try {
      $hit = Get-ChildItem -Path $base -Recurse -File -Filter "Processing.NDI.Lib.x64.dll" -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($hit) { return $hit.Directory.FullName }
    } catch {}
  }

  return $null
}

function Copy-NdiRuntimeToLocalFolder([string]$dllFolder, [string]$destRoot) {
  New-Item -ItemType Directory -Force -Path $destRoot | Out-Null

  $destBin = Join-Path $destRoot "bin"
  New-Item -ItemType Directory -Force -Path $destBin | Out-Null

  Write-Host "Copying NDI runtime DLLs from: $dllFolder" -ForegroundColor Cyan

  $dlls = Get-ChildItem -Path $dllFolder -File -Filter "*.dll" -ErrorAction SilentlyContinue
  if (!$dlls -or $dlls.Count -eq 0) {
    throw "No DLLs found in '$dllFolder'"
  }

  foreach ($d in $dlls) {
    Copy-Item -Force -Path $d.FullName -Destination (Join-Path $destBin $d.Name)
  }

  Write-Host "OK: copied $($dlls.Count) DLL(s) -> $destBin" -ForegroundColor Green
}

# Fail-closed : le telechargement d'un runtime executable ne peut se faire
# qu'en HTTPS, et le fichier obtenu doit porter une signature Authenticode
# du signataire attendu AVANT toute execution.
function Assert-HttpsUrl([string]$Url) {
  $parsed = [uri]$Url
  if ($parsed.Scheme -ne 'https') {
    throw "Refusing non-HTTPS download URL: $Url (scheme must be https)"
  }
}

function Assert-AuthenticodeSignedByExpectedPublisher([string]$Path) {
  $sig = Get-AuthenticodeSignature -FilePath $Path
  if (-not $sig.SignerCertificate) {
    throw "Downloaded redistributable is NOT signed. Refusing to run it."
  }
  $subject = $sig.SignerCertificate.Subject
  if ($subject -notmatch $ExpectedSigner) {
    throw "Downloaded redistributable is signed by an unexpected publisher: $subject (expected pattern: $ExpectedSigner)"
  }
  # Status must be Valid (chain ok). UnknownError peut survenir si la racine
  # n'est pas approuvee sur la machine locale : on l'accepte uniquement quand
  # le signataire correspond au modele attendu ci-dessus.
  if ($sig.Status -ne 'Valid' -and $sig.Status -ne 'UnknownError') {
    throw "Downloaded redistributable signature status is $($sig.Status). Refusing to run it."
  }
  Write-Host ("OK: redistributable signed by {0} (status: {1})" -f $subject, $sig.Status) -ForegroundColor Green
}

Write-Host "== Project-On NDI Runtime Setup ==" -ForegroundColor Cyan
Write-Host "Destination: $Destination" -ForegroundColor Gray

if ($Install) {
  Assert-HttpsUrl $RedistUrl
  $tmp = Join-Path $env:TEMP ("NDI_Redist_" + [guid]::NewGuid().ToString() + ".exe")
  try {
    Write-Host "Downloading NDI redistributable..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $RedistUrl -OutFile $tmp

    Assert-AuthenticodeSignedByExpectedPublisher $tmp

    Write-Host "Running installer (silent)..." -ForegroundColor Cyan
    $p = Start-Process -FilePath $tmp -ArgumentList "/verysilent /norestart" -Wait -PassThru
    if ($p.ExitCode -ne 0) {
      throw "NDI redistributable installer failed with exit code $($p.ExitCode)"
    }
  }
  finally {
    try { Remove-Item -Force $tmp -ErrorAction SilentlyContinue } catch {}
  }
}

$dllFolder = Find-NdiRuntimeDllFolder
if (!$dllFolder) {
  Write-Host "NDI runtime not found." -ForegroundColor Yellow
  Write-Host "- Option 1: rerun with -Install to download/install the redistributable" -ForegroundColor Yellow
  Write-Host "- Option 2: install NDI Runtime manually, then rerun this script" -ForegroundColor Yellow
  throw "Unable to locate Processing.NDI.Lib.x64.dll"
}

Copy-NdiRuntimeToLocalFolder -dllFolder $dllFolder -destRoot $Destination

Write-Host "Done. You can now build and ship Project-On with the './ndi' folder." -ForegroundColor Green
