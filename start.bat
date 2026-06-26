@echo off
echo ============================================
echo   PodcastAI - Iniciando servicios...
echo ============================================
echo.

REM --- Verificar entorno virtual ---
if not exist "backend\.venv\Scripts\activate.bat" (
    echo [ERROR] Entorno virtual no encontrado.
    echo Ejecuta primero: powershell -ExecutionPolicy Bypass -File install.ps1
    pause
    exit /b 1
)

REM --- Verificar node_modules del frontend ---
if not exist "frontend\node_modules" (
    echo [WARN] Dependencias del frontend no encontradas. Instalando...
    cd /d "%~dp0frontend"
    call npm install
    cd /d "%~dp0"
    echo [OK]  Dependencias del frontend instaladas
    echo.
)

REM --- 1. Ollama ---
echo [1/3] Iniciando Ollama...
set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if exist "%OLLAMA_EXE%" (
    set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
    start /b "" "%OLLAMA_EXE%" serve > "%~dp0logs_ollama.txt" 2>&1
) else (
    start /b "" ollama serve > "%~dp0logs_ollama.txt" 2>&1
)
timeout /t 3 /nobreak > nul
echo [OK]  Ollama iniciado (log: logs_ollama.txt)

REM --- 2. Backend ---
echo [2/3] Iniciando Backend (puerto 8000)...
start "PodcastAI Backend" cmd /k "cd /d %~dp0backend && call .venv\Scripts\activate.bat && uvicorn app.main:app --host 0.0.0.0 --port 8000"

REM --- Esperar a que el backend responda ---
echo       Esperando al backend (puede tardar 30-60 s la primera vez)...
set RETRY=0
:check_backend
set /a RETRY+=1
if %RETRY% gtr 30 (
    echo [WARN] El backend tarda mas de lo esperado.
    echo        Revisa la ventana "PodcastAI Backend" o el archivo logs_backend.txt
    goto start_frontend
)
curl -sf "http://localhost:8000/api/v1/system/health" > nul 2>&1
if errorlevel 1 (
    timeout /t 2 /nobreak > nul
    goto check_backend
)
echo [OK]  Backend listo

REM --- 3. Frontend ---
:start_frontend
echo [3/3] Iniciando Frontend (puerto 5173)...
start "PodcastAI Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 4 /nobreak > nul

echo.
echo ============================================
echo   PodcastAI iniciado!
echo ============================================
echo   Frontend:  http://localhost:5173
echo   Backend:   http://localhost:8000
echo   API Docs:  http://localhost:8000/api/docs
echo   Log Ollama: logs_ollama.txt
echo ============================================
echo.
start http://localhost:5173
