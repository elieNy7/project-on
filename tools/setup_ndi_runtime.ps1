param(
  [string]$Destination = "./ndi",
  [switch]$Install,
  [string]$RedistUrl = "http://ndi.link/NDIRedistV6"
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

Write-Host "== Project-On NDI Runtime Setup ==" -ForegroundColor Cyan
Write-Host "Destination: $Destination" -ForegroundColor Gray

if ($Install) {
  $tmp = Join-Path $env:TEMP ("NDI_Redist_" + [guid]::NewGuid().ToString() + ".exe")
  Write-Host "Downloading NDI redistributable..." -ForegroundColor Cyan
  Invoke-WebRequest -Uri $RedistUrl -OutFile $tmp

  Write-Host "Running installer (silent)..." -ForegroundColor Cyan
  $p = Start-Process -FilePath $tmp -ArgumentList "/verysilent /norestart" -Wait -PassThru
  if ($p.ExitCode -ne 0) {
    throw "NDI redistributable installer failed with exit code $($p.ExitCode)"
  }

  try { Remove-Item -Force $tmp } catch {}
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
