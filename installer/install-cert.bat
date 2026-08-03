@echo off
rem ================================================================
rem  Project-On - Installation du certificat de confiance
rem
rem  Installe le certificat public de signature de code Project-On
rem  dans les magasins "Autorites de certification racines de
rem  confiance" et "Editeurs approuves" de l'utilisateur courant.
rem
rem  Effet : Windows reconnait l'editeur "Elie Nyembo / Project-On"
rem  et les avertissements SmartScreen / Controle intelligent des
rem  applications sont fortement reduits pour les fichiers signes.
rem
rem  Aucun droit administrateur requis (magasin utilisateur).
rem ================================================================
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
set "CERT_FILE=%SCRIPT_DIR%Project-On-CodeSigning.cer"

if not exist "%CERT_FILE%" (
    echo [ERROR] Certificat introuvable : %CERT_FILE%
    pause
    exit /b 1
)

echo Installation du certificat Project-On pour l'utilisateur courant...
certutil -user -addstore Root "%CERT_FILE%" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Echec de l'installation dans le magasin racine.
    pause
    exit /b 1
)
certutil -user -addstore TrustedPublisher "%CERT_FILE%" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Echec de l'installation dans les editeurs approuves.
    pause
    exit /b 1
)

echo.
echo [OK] Certificat installe. Windows reconnaitra desormais
echo      l'editeur "Elie Nyembo / Project-On" pour les fichiers signes.
echo.
pause
exit /b 0
