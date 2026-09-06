@echo off
chcp 65001 >nul
setlocal

set "ROOT=%~dp0"
set "CONFIG=%ROOT%config\bot.json"
set "VENV=%ROOT%.venv\Scripts\python.exe"

if exist "%VENV%" (
    set "PY=%VENV%"
) else (
    set "PY=python"
)

if "%1"==""      goto run
if "%1"=="help"  goto help
if "%1"=="dry"   goto dry
if "%1"=="once"  goto once
if "%1"=="run"   goto run
if "%1"=="test"  goto test
if "%1"=="setup" goto setup

echo [ERR] Lenh khong hop le: %1
goto help

:dry
echo [DRY-RUN] Preview - khong move file thuc su
echo Config: %CONFIG%
echo.
"%PY%" "%ROOT%cli.py" --config "%CONFIG%" --dry-run --once
echo.
pause
goto end

:once
echo [ONCE] Quet 1 lan roi thoat
echo Config: %CONFIG%
echo.
"%PY%" "%ROOT%cli.py" --config "%CONFIG%" --once
echo.
pause
goto end

:run
echo [RUN] Bot dang chay - nhan Ctrl+C de dung
echo Config: %CONFIG%
echo.
"%PY%" "%ROOT%cli.py" --config "%CONFIG%"
goto end

:test
echo [TEST] Chay toan bo test suite
echo.
"%PY%" -m pytest "%ROOT%tests" -v
echo.
pause
goto end

:setup
echo [SETUP] Cai dat dependencies...
"%PY%" -m pip install -r "%ROOT%requirements.txt"
echo.
echo Xong. Gio co the chay: run.bat dry
echo.
pause
goto end

:help
echo.
echo  file_router_bot - launcher
echo  ---------------------------
echo  run.bat dry     Preview thuat toan, khong move file
echo  run.bat once    Quet 1 lan roi thoat (move that)
echo  run.bat run     Chay lien tuc (move that), Ctrl+C de dung
echo  run.bat test    Chay test suite
echo  run.bat setup   Cai pip dependencies
echo.
echo  Chinh thong so bot: sua file config\bot.json
echo.
pause

:end
endlocal
