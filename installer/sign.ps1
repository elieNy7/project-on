<#
    Signe un fichier (.exe) avec le certificat de signature de code de Project-On.

    Recherche du certificat dans Cert:\CurrentUser\My, dans cet ordre :
      1. empreinte exacte si $env:SIGN_THUMBPRINT est defini. Si elle est
         definie mais introuvable -> ECHEC (pas de repli silencieux vers un
         autre certificat) ;
      2. certificat de signature de code dont le sujet contient
         "Project-On" ou "Elie Nyembo" ;
      3. premier certificat de signature de code disponible.

    Horodatage : $env:SIGN_TIMESTAMP_URL, sinon DigiCert par defaut.

    Mode strict (-Strict, ou $env:SIGN_STRICT=1) : reserve aux releases.
      - SIGN_THUMBPRINT OBLIGATOIRE et le certificat doit etre trouve ;
      - la signature finale doit provenir de l'empreinte attendue ;
      - le statut doit etre Valid (ou UnknownError accepte uniquement si
        $env:SIGN_ALLOW_SELF_SIGNED=1, cas d'un certificat auto-signe dont
        la racine n'est pas installee sur la machine de build).

    Codes de sortie :
      0 = signature valide selon le mode demande ;
      1 = la signature n'a pas pu etre incorporee / revalidee ;
      2 = aucun certificat de signature (ou empreinte absente en strict).
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [switch]$Strict
)

$ErrorActionPreference = 'Stop'

if (-not $Strict -and $env:SIGN_STRICT -eq '1') { $Strict = $true }

if (-not (Test-Path -LiteralPath $Path)) {
    Write-Host "[WARN] Fichier a signer introuvable : $Path"
    exit 1
}

if ($Strict -and -not $env:SIGN_THUMBPRINT) {
    Write-Host "[ERROR] Mode strict : SIGN_THUMBPRINT est obligatoire."
    exit 2
}

function Find-SigningCert {
    if ($env:SIGN_THUMBPRINT) {
        $c = Get-ChildItem Cert:\CurrentUser\My |
            Where-Object { $_.Thumbprint -eq $env:SIGN_THUMBPRINT }
        if ($c) { return ($c | Select-Object -First 1) }
        # Empreinte explicite mais introuvable : ne JAMAIS signer avec un
        # autre certificat sans le demander.
        return $null
    }
    $c = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Subject -match 'Project-On|Elie Nyembo' } |
        Select-Object -First 1
    if ($c) { return $c }
    Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Select-Object -First 1
}

$cert = Find-SigningCert
if (-not $cert) {
    if ($env:SIGN_THUMBPRINT) {
        Write-Host ("[ERROR] Certificat introuvable pour l'empreinte demandee : {0}" -f $env:SIGN_THUMBPRINT)
    } else {
        Write-Host "[WARN] Aucun certificat de signature de code dans Cert:\CurrentUser\My."
    }
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
if (-not $sig.SignerCertificate) {
    Write-Host "[WARN] La signature n'a pas pu etre incorporee."
    exit 1
}

if ($env:SIGN_THUMBPRINT -and $sig.SignerCertificate.Thumbprint -ne $env:SIGN_THUMBPRINT) {
    Write-Host ("[ERROR] Le fichier est signe par {0} au lieu de l'empreinte attendue." -f $sig.SignerCertificate.Subject)
    exit 1
}

if ($Strict) {
    $allowSelfSigned = ($env:SIGN_ALLOW_SELF_SIGNED -eq '1')
    if ($sig.Status -ne 'Valid' -and -not ($allowSelfSigned -and $sig.Status -eq 'UnknownError')) {
        Write-Host ("[ERROR] Mode strict : statut de signature {0} (signataire : {1})." -f $sig.Status, $sig.SignerCertificate.Subject)
        exit 1
    }
}

Write-Host ("[OK] Signe par {0} (statut local : {1})" -f $sig.SignerCertificate.Subject, $sig.Status)
exit 0
