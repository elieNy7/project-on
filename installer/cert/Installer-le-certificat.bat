@echo off
rem ============================================================
rem  Project-On - Faire confiance au certificat de l'editeur
rem
rem  A executer UNE FOIS sur chaque PC ou l'installeur est
rem  bloque par une "strategie de controle d'application"
rem  (AppLocker / WDAC). Clic droit > "Executer en tant
rem  qu'administrateur".
rem
rem  Cela importe le certificat public ProjectOn-Publisher.cer
rem  dans les magasins "Autorites de certification racines de
rem  confiance" et "Editeurs approuves" de l'ordinateur, afin
rem  que la signature de Project-On soit reconnue.
rem ============================================================
setlocal
set "CER=%~dp0ProjectOn-Publisher.cer"

net session >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Ce script doit etre lance en tant qu'administrateur.
    echo          Clic droit sur le fichier ^> Executer en tant qu'administrateur.
    pause
    exit /b 1
)

if not exist "%CER%" (
    echo [ERREUR] Certificat introuvable: "%CER%"
    pause
    exit /b 1
)

echo Importation du certificat dans le magasin "Racines de confiance"...
certutil -addstore -f Root "%CER%"
echo.
echo Importation du certificat dans le magasin "Editeurs approuves"...
certutil -addstore -f TrustedPublisher "%CER%"
echo.
echo [OK] Certificat installe. Vous pouvez relancer l'installeur Project-On.
pause
endlocal
