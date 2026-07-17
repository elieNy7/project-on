<#
    Signe un fichier (.exe) avec le certificat de signature de code de Project-On.

    Recherche du certificat dans Cert:\CurrentUser\My, dans cet ordre :
      1. empreinte exacte si $env:SIGN_THUMBPRINT est defini ;
      2. certificat de signature de code dont le sujet contient
         "Project-On" ou "Elie Nyembo" ;
      3. premier certificat de signature de code disponible.

    Horodatage : $env:SIGN_TIMESTAMP_URL, sinon DigiCert par defaut.

    Codes de sortie :
      0 = signature incorporee (meme si la racine n'est pas approuvee sur
          cette machine -> statut "UnknownError", normal pour un cert auto-signe) ;
      1 = la signature n'a pas pu etre incorporee ;
      2 = aucun certificat de signature trouve.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Path)) {
    Write-Host "[WARN] Fichier a signer introuvable : $Path"
    exit 1
}

function Find-SigningCert {
    if ($env:SIGN_THUMBPRINT) {
        $c = Get-ChildItem Cert:\CurrentUser\My |
            Where-Object { $_.Thumbprint -eq $env:SIGN_THUMBPRINT }
        if ($c) { return ($c | Select-Object -First 1) }
    }
    $c = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Subject -match 'Project-On|Elie Nyembo' } |
        Select-Object -First 1
    if ($c) { return $c }
    Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Select-Object -First 1
}

$cert = Find-SigningCert
if (-not $cert) {
    Write-Host "[WARN] Aucun certificat de signature de code dans Cert:\CurrentUser\My."
    exit 2
}

$ts = if ($env:SIGN_TIMESTAMP_URL) { $env:SIGN_TIMESTAMP_URL } else { 'http://timestamp.digicert.com' }

try {
    Set-AuthenticodeSignature -FilePath $Path -Certificate $cert `
        -HashAlgorithm SHA256 -TimestampServer $ts | Out-Null
}
catch {
    # Set-AuthenticodeSignature renvoie "UnknownError" pour un certificat
    # auto-signe (racine non approuvee ici) ALORS QUE la signature est bien
    # incorporee. On ne se fie donc pas au statut : on revalide ci-dessous.
}

$sig = Get-AuthenticodeSignature -FilePath $Path
if ($sig.SignerCertificate) {
    Write-Host ("[OK] Signe par {0} (statut local : {1})" -f $sig.SignerCertificate.Subject, $sig.Status)
    exit 0
}

Write-Host "[WARN] La signature n'a pas pu etre incorporee."
exit 1
