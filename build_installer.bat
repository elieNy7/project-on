@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ================================================================
rem  Project-On - build Windows installer
rem
rem  Usage:
rem    build_installer.bat
rem    build_installer.bat --no-clean
rem    build_installer.bat --skip-pyinstaller
rem    build_installer.bat --skip-installer
rem    build_installer.bat --help
rem
rem  Optional environment variables:
rem    PYTHON_EXE=C:\Path\to\python.exe
rem    ISCC_EXE=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
rem ================================================================

set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR:~0,-1%"
set "SPEC_FILE=project_on.spec"
set "ISS_FILE=installer\setup.iss"
set "APP_DIR=dist\Project-On"
set "APP_EXE=dist\Project-On\Project-On.exe"
set "INSTALLER_OUTPUT_DIR=installer\Output"
set "LOG_DIR=build_logs"
set "PYINSTALLER_LOG=%LOG_DIR%\pyinstaller.log"
set "INNO_LOG=%LOG_DIR%\inno_setup.log"
set "DO_CLEAN=1"
set "RUN_PYINSTALLER=1"
set "RUN_INNO=1"
set "DO_SIGN=1"
set "PYTHON_ARGS="
set "SIGN_PS1=installer\sign.ps1"

for %%A in (%*) do (
    if /I "%%~A"=="--help" goto :help
    if /I "%%~A"=="/?" goto :help
    if /I "%%~A"=="--no-clean" set "DO_CLEAN=0"
    if /I "%%~A"=="--skip-pyinstaller" set "RUN_PYINSTALLER=0"
    if /I "%%~A"=="--skip-installer" set "RUN_INNO=0"
    if /I "%%~A"=="--no-sign" set "DO_SIGN=0"
)

pushd "%ROOT_DIR%" || (
    echo [ERROR] Impossible d'ouvrir le dossier du projet:
    echo         "%ROOT_DIR%"
    exit /b 1
)

echo ================================================================
echo   Project-On - creation de l'installeur Windows
echo ================================================================
echo Dossier projet : %CD%
echo.

if "%RUN_PYINSTALLER%"=="1" (
    call :check_file "%SPEC_FILE%" "Spec PyInstaller"
    if errorlevel 1 goto :fail
)

if "%RUN_INNO%"=="1" (
    call :check_file "%ISS_FILE%" "Script Inno Setup"
    if errorlevel 1 goto :fail
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

if "%RUN_PYINSTALLER%"=="1" (
    call :resolve_python
    if errorlevel 1 goto :fail
)

if "%RUN_INNO%"=="1" (
    call :resolve_iscc
    if errorlevel 1 goto :fail
)

if "%RUN_PYINSTALLER%"=="1" echo [INFO] Python     : %PYTHON_EXE% %PYTHON_ARGS%
if "%RUN_INNO%"=="1" echo [INFO] Inno Setup : %ISCC_EXE%
echo.

if "%DO_CLEAN%"=="1" (
    if "%RUN_PYINSTALLER%"=="1" (
        call :clean_dir "build"
        if errorlevel 1 goto :fail
        call :clean_dir "dist"
        if errorlevel 1 goto :fail
    ) else (
        echo [SKIP] Nettoyage build/dist ignore: --skip-pyinstaller.
    )
    if "%RUN_INNO%"=="1" (
        call :clean_dir "%INSTALLER_OUTPUT_DIR%"
        if errorlevel 1 goto :fail
    )
) else (
    echo [SKIP] Nettoyage ignore: --no-clean.
)

if "%RUN_PYINSTALLER%"=="1" (
    echo.
    echo [1/2] Verification de PyInstaller...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m PyInstaller --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] PyInstaller n'est pas disponible pour ce Python.
        echo         Installe les dependances avec:
        echo         "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r requirements.txt
        goto :fail
    )

    echo [2/2] Build de l'application avec PyInstaller...
    echo       Log: %PYINSTALLER_LOG%
    "%PYTHON_EXE%" %PYTHON_ARGS% -m PyInstaller --noconfirm --clean "%SPEC_FILE%" > "%PYINSTALLER_LOG%" 2>&1
    if errorlevel 1 (
        echo [ERROR] PyInstaller a echoue. Dernieres lignes du log:
        powershell -NoProfile -Command "Get-Content -Tail 40 '%PYINSTALLER_LOG%'" 2>nul
        goto :fail
    )
) else (
    echo [SKIP] PyInstaller ignore: --skip-pyinstaller.
)

if "%RUN_PYINSTALLER%%RUN_INNO%"=="00" (
    echo [INFO] Aucune etape de build demandee.
) else (
    call :check_file "%APP_EXE%" "Executable genere"
    if errorlevel 1 goto :fail
    call :audit_dist
    if errorlevel 1 goto :fail
    call :sign_file "%APP_EXE%" "Application Project-On.exe"
)

if "%RUN_INNO%"=="1" (
    echo.
    echo [3/3] Compilation de l'installeur Inno Setup...
    echo       Log: %INNO_LOG%
    "%ISCC_EXE%" "%ISS_FILE%" > "%INNO_LOG%" 2>&1
    if errorlevel 1 (
        echo [ERROR] Inno Setup a echoue. Dernieres lignes du log:
        powershell -NoProfile -Command "Get-Content -Tail 40 '%INNO_LOG%'" 2>nul
        goto :fail
    )
) else (
    echo [SKIP] Compilation Inno Setup ignoree: --skip-installer.
)

call :find_installer
if errorlevel 1 goto :fail

if "%RUN_INNO%"=="1" call :sign_file "%INSTALLER_PATH%" "Installeur"

echo.
echo ================================================================
echo   Build termine avec succes.
echo   Installeur : %INSTALLER_PATH%
echo   Logs       : %CD%\%LOG_DIR%
echo ================================================================
popd
pause
exit /b 0

:help
echo.
echo Project-On installer build
echo.
echo Options:
echo   --no-clean           Ne supprime pas build\ et dist\
echo   --skip-pyinstaller   Reutilise dist\Project-On deja genere
echo   --skip-installer     Genere seulement dist\Project-On
echo   --no-sign            Ne signe pas l'application ni l'installeur
echo   --help               Affiche cette aide
echo.
echo Variables optionnelles:
echo   PYTHON_EXE=chemin\python.exe
echo   ISCC_EXE=chemin\ISCC.exe
echo   SIGN_THUMBPRINT=empreinte du certificat de signature ^(sinon auto^)
echo   SIGN_TIMESTAMP_URL=serveur d'horodatage ^(defaut DigiCert^)
echo.
exit /b 0

:check_file
set "CHECK_PATH=%~1"
set "CHECK_LABEL=%~2"
if not exist "%CHECK_PATH%" (
    echo [ERROR] %CHECK_LABEL% introuvable:
    echo         "%CHECK_PATH%"
    exit /b 1
)
exit /b 0

rem ----------------------------------------------------------------
rem  Signe un fichier avec le certificat de Project-On (non bloquant).
rem  Une signature absente/echouee n'interrompt PAS le build : elle
rem  ameliore la confiance (editeur + horodatage) mais n'est pas
rem  indispensable pour produire l'installeur.
rem  NOTE: un certificat auto-signe ne satisfait PAS Smart App Control
rem  de Windows ; seul un certificat EV ou le Microsoft Store le font.
rem ----------------------------------------------------------------
:sign_file
set "SIGN_TARGET=%~1"
set "SIGN_LABEL=%~2"
if "%DO_SIGN%"=="0" (
    echo [SKIP] Signature ignoree ^(--no-sign^): %SIGN_LABEL%.
    exit /b 0
)
if not exist "%SIGN_PS1%" (
    echo [WARN] Script de signature introuvable: %SIGN_PS1% ^(signature ignoree^).
    exit /b 0
)
echo [SIGN] !SIGN_LABEL! ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SIGN_PS1%" "%SIGN_TARGET%"
set "SIGN_RC=!errorlevel!"
if "!SIGN_RC!"=="0" (
    echo [SIGN] !SIGN_LABEL! : OK.
) else if "!SIGN_RC!"=="2" (
    echo [WARN] !SIGN_LABEL! : aucun certificat de signature, build poursuivi non signe.
) else (
    echo [WARN] !SIGN_LABEL! : signature non appliquee, rc=!SIGN_RC!, build poursuivi.
)
exit /b 0

:resolve_python
if defined PYTHON_EXE (
    if exist "%PYTHON_EXE%" exit /b 0
    where "%PYTHON_EXE%" >nul 2>&1
    if not errorlevel 1 exit /b 0
    echo [ERROR] PYTHON_EXE pointe vers un fichier introuvable:
    echo         "%PYTHON_EXE%"
    exit /b 1
)

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
    exit /b 0
)

where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python"
    exit /b 0
)

echo [ERROR] Python introuvable dans le PATH.
echo         Installe Python 3 puis relance ce script.
exit /b 1

:resolve_iscc
if defined ISCC_EXE (
    if exist "%ISCC_EXE%" exit /b 0
    where "%ISCC_EXE%" >nul 2>&1
    if not errorlevel 1 exit /b 0
    echo [ERROR] ISCC_EXE pointe vers un fichier introuvable:
    echo         "%ISCC_EXE%"
    exit /b 1
)

set "ISCC_CANDIDATE=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if exist "%ISCC_CANDIDATE%" (
    set "ISCC_EXE=%ISCC_CANDIDATE%"
    exit /b 0
)

set "ISCC_CANDIDATE=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if exist "%ISCC_CANDIDATE%" (
    set "ISCC_EXE=%ISCC_CANDIDATE%"
    exit /b 0
)

where iscc.exe >nul 2>&1
if not errorlevel 1 (
    set "ISCC_EXE=iscc.exe"
    exit /b 0
)

echo [ERROR] Inno Setup 7 introuvable.
echo         Installe Inno Setup 7 ou lance avec:
echo         set "ISCC_EXE=C:\Program Files (x86)\Inno Setup 7\ISCC.exe"
exit /b 1

:clean_dir
set "DIR_TO_CLEAN=%~1"
if "%DIR_TO_CLEAN%"=="" exit /b 1
if /I not "%DIR_TO_CLEAN%"=="build" if /I not "%DIR_TO_CLEAN%"=="dist" (
    if /I not "%DIR_TO_CLEAN%"=="installer\Output" (
        echo [ERROR] Nettoyage refuse pour un dossier non autorise: %DIR_TO_CLEAN%
        exit /b 1
    )
)

if exist "%DIR_TO_CLEAN%" (
    echo [CLEAN] Suppression de %DIR_TO_CLEAN%\ ...
    rmdir /s /q "%DIR_TO_CLEAN%"
    if exist "%DIR_TO_CLEAN%" (
        echo [ERROR] Impossible de supprimer %DIR_TO_CLEAN%\.
        echo         Ferme les fenetres ou processus qui utilisent ce dossier.
        exit /b 1
    )
) else (
    echo [CLEAN] %DIR_TO_CLEAN%\ deja absent.
)
exit /b 0

:audit_dist
set "RESOURCE_DIR=%APP_DIR%"
if exist "%APP_DIR%\_internal" set "RESOURCE_DIR=%APP_DIR%\_internal"

for %%D in (
    "bible_json"
    "cantiques"
    "expose"
    "vgr"
    "shp"
    "installer"
    "build"
    "assets\icons"
) do (
    if exist "%RESOURCE_DIR%\%%~D" (
        echo [ERROR] Ressource inutile detectee dans le build: %%~D
        echo         Verifie project_on.spec avant de compiler l'installeur.
        exit /b 1
    )
)

for %%F in (
    "%RESOURCE_DIR%\data\*.bak*"
    "%RESOURCE_DIR%\data\project_on.before_*.db"
    "%RESOURCE_DIR%\data\sermons_main_fr.sqlite"
    "%RESOURCE_DIR%\presentation\obs-test.html"
    "%RESOURCE_DIR%\assets\fonts\*\OFL.txt"
    "%RESOURCE_DIR%\assets\fonts\*\README.txt"
) do (
    if exist "%%~F" (
        echo [ERROR] Fichier inutile detecte dans le build: %%~F
        echo         Verifie project_on.spec avant de compiler l'installeur.
        exit /b 1
    )
)

echo [OK] Contenu runtime verifie: aucun dossier source ou backup inutile.
exit /b 0

:find_installer
set "INSTALLER_PATH="
for /f "delims=" %%F in ('dir /b /a-d /o-d "installer\Output\*.exe" 2^>nul') do (
    set "INSTALLER_PATH=%CD%\installer\Output\%%F"
    exit /b 0
)

if "%RUN_INNO%"=="0" (
    set "INSTALLER_PATH=%CD%\%APP_DIR%"
    exit /b 0
)

echo [ERROR] Aucun installeur trouve dans installer\Output\.
exit /b 1

:fail
echo.
echo ================================================================
echo   Build interrompu.
echo   Consulte les logs dans: %CD%\%LOG_DIR%
echo ================================================================
popd
pause
exit /b 1
