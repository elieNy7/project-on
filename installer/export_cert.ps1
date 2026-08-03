<#
    Exporte le certificat public de signature de code Project-On (.cer)
    vers installer\Project-On-CodeSigning.cer pour distribution aux utilisateurs.
#>
$ErrorActionPreference = 'Stop'
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Where-Object { $_.Subject -match 'Project-On|Elie Nyembo' } |
    Select-Object -First 1
if (-not $cert) {
    Write-Host "[ERROR] Certificat de signature introuvable."
    exit 1
}
$out = Join-Path $PSScriptRoot 'Project-On-CodeSigning.cer'
Export-Certificate -Cert $cert -FilePath $out -Force | Out-Null
Write-Host "[OK] Certificat public exporte : $out"
Write-Host "     Sujet     : $($cert.Subject)"
Write-Host "     Empreinte : $($cert.Thumbprint)"
