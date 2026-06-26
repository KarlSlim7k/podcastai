#Requires -RunAsAdministrator
<#
.SYNOPSIS
    PodcastAI - Script de instalación automática para Windows 11
.DESCRIPTION
    Instala Python, FFmpeg, Ollama, y todas las dependencias necesarias.
    Descarga modelos de IA y configura el entorno completo.
#>

param(
    [switch]$SkipPython,
    [switch]$SkipFFmpeg,
    [switch]$SkipOllama,
    [switch]$SkipModels,
    [string]$OllamaModel = "qwen3:8b"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SCRIPT_DIR = $PSScriptRoot
$BACKEND_DIR = Join-Path $SCRIPT_DIR "backend"
$FRONTEND_DIR = Join-Path $SCRIPT_DIR "frontend"
$VENV_DIR = Join-Path $BACKEND_DIR ".venv"

function Write-Step { param($msg) Write-Host "`n[STEP] $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "[OK]   $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err  { param($msg) Write-Host "[ERR]  $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "       $msg" -ForegroundColor Gray }

Write-Host @"
╔══════════════════════════════════════════════════════╗
║          PodcastAI - Instalación Automática          ║
║      Transcripción y Análisis Local con IA           ║
╚══════════════════════════════════════════════════════╝
"@ -ForegroundColor Magenta

# ─────────────────────────────────────────────────────────────────────────────
# 1. PYTHON
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Verificando Python 3.12+"

if (-not $SkipPython) {
    $python = $null
    foreach ($cmd in @("python", "python3", "py")) {
        try {
            $ver = & $cmd --version 2>&1
            if ($ver -match "Python 3\.(1[2-9]|[2-9]\d)") {
                $python = $cmd
                Write-Ok "Python encontrado: $ver"
                break
            }
        } catch {}
    }

    if (-not $python) {
        Write-Warn "Python 3.12+ no encontrado. Descargando..."
        $pythonUrl = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
        $pythonInstaller = Join-Path $env:TEMP "python_installer.exe"
        Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonInstaller -UseBasicParsing
        Start-Process -FilePath $pythonInstaller -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1" -Wait
        Remove-Item $pythonInstaller -Force
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
        Write-Ok "Python 3.12 instalado"
    }
} else {
    Write-Warn "Saltando instalación de Python"
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. FFmpeg
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Verificando FFmpeg"

if (-not $SkipFFmpeg) {
    try {
        $ffVer = & ffmpeg -version 2>&1 | Select-Object -First 1
        Write-Ok "FFmpeg encontrado: $ffVer"
    } catch {
        Write-Warn "FFmpeg no encontrado. Instalando via winget..."
        try {
            winget install --id Gyan.FFmpeg -e --silent --accept-source-agreements --accept-package-agreements
            Write-Ok "FFmpeg instalado via winget"
        } catch {
            Write-Warn "winget falló. Descargando manualmente..."
            $ffmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
            $ffmpegZip = Join-Path $env:TEMP "ffmpeg.zip"
            $ffmpegDir = "C:\ffmpeg"
            Invoke-WebRequest -Uri $ffmpegUrl -OutFile $ffmpegZip -UseBasicParsing
            Expand-Archive -Path $ffmpegZip -DestinationPath $env:TEMP -Force
            $extracted = Get-ChildItem $env:TEMP -Directory | Where-Object { $_.Name -like "ffmpeg-*" } | Select-Object -First 1
            if ($extracted) {
                Move-Item $extracted.FullName $ffmpegDir -Force
                $binPath = Join-Path $ffmpegDir "bin"
                $currentPath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
                if ($currentPath -notlike "*$binPath*") {
                    [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$binPath", "Machine")
                }
            }
            Remove-Item $ffmpegZip -Force
            Write-Ok "FFmpeg instalado en C:\ffmpeg"
        }
    }
} else {
    Write-Warn "Saltando instalación de FFmpeg"
}

# ─────────────────────────────────────────────────────────────────────────────
# 3. CUDA / PyTorch check
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Verificando CUDA"

$cudaAvailable = $false
try {
    $nvidiaSmi = & nvidia-smi 2>&1 | Select-Object -First 3
    if ($nvidiaSmi -match "NVIDIA") {
        $cudaAvailable = $true
        Write-Ok "NVIDIA GPU detectada"
        Write-Info ($nvidiaSmi | Select-Object -First 1)
    }
} catch {
    Write-Warn "nvidia-smi no disponible. Asegúrate de tener drivers NVIDIA instalados."
}

# Detectar VRAM para seleccionar el modelo óptimo
$vramMb = 0
if ($cudaAvailable) {
    try {
        $vramStr = & nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>&1
        $vramMb = [int]($vramStr.Trim().Split("`n")[0].Trim())
        $vramGb = [math]::Round($vramMb / 1024, 1)
        Write-Ok "VRAM detectada: $vramGb GB"
    } catch {
        Write-Warn "No se pudo obtener la cantidad de VRAM."
    }
}

# Auto-seleccionar modelo Ollama si el usuario no pasó -OllamaModel
if (-not $PSBoundParameters.ContainsKey('OllamaModel')) {
    if ($vramMb -ge 12000) {
        $OllamaModel = "qwen3:14b"
    } elseif ($vramMb -ge 6000) {
        $OllamaModel = "qwen3:8b"
    } elseif ($vramMb -ge 4000) {
        $OllamaModel = "qwen3:4b"
    } else {
        $OllamaModel = "qwen3:1.7b"
    }
}
Write-Ok "Modelo Ollama seleccionado: $OllamaModel"
Write-Info "(Para cambiar: .\install.ps1 -OllamaModel qwen3:14b)"

# ─────────────────────────────────────────────────────────────────────────────
# 4. Python virtual environment & dependencies
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Configurando entorno Python"

Set-Location $BACKEND_DIR

if (-not (Test-Path $VENV_DIR)) {
    python -m venv $VENV_DIR
    Write-Ok "Virtualenv creado en $VENV_DIR"
}

$pip = Join-Path $VENV_DIR "Scripts\pip.exe"
$pythonVenv = Join-Path $VENV_DIR "Scripts\python.exe"

Write-Info "Actualizando pip..."
& $pip install --upgrade pip --quiet

Write-Info "Instalando dependencias del backend..."

if ($cudaAvailable) {
    Write-Info "Instalando PyTorch con soporte CUDA 12.1..."
    & $pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 --quiet
} else {
    Write-Warn "CUDA no disponible - instalando PyTorch CPU (transcripción será más lenta)"
    & $pip install torch torchvision torchaudio --quiet
}

& $pip install -r requirements.txt --quiet
Write-Ok "Dependencias del backend instaladas"

# ─────────────────────────────────────────────────────────────────────────────
# 5. OLLAMA
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Verificando Ollama"

if (-not $SkipOllama) {
    try {
        $ollamaVer = & ollama version 2>&1
        Write-Ok "Ollama encontrado: $ollamaVer"
    } catch {
        Write-Warn "Ollama no encontrado. Descargando..."
        $ollamaUrl = "https://ollama.com/download/OllamaSetup.exe"
        $ollamaInstaller = Join-Path $env:TEMP "OllamaSetup.exe"
        Invoke-WebRequest -Uri $ollamaUrl -OutFile $ollamaInstaller -UseBasicParsing
        Start-Process -FilePath $ollamaInstaller -ArgumentList "/silent" -Wait
        Remove-Item $ollamaInstaller -Force
        Write-Ok "Ollama instalado"
        Start-Sleep -Seconds 3
    }

    if (-not $SkipModels) {
        Write-Step "Descargando modelo IA: $OllamaModel"
        Write-Warn "Esto puede tardar varios minutos dependiendo de tu conexión..."
        & ollama pull $OllamaModel
        Write-Ok "Modelo $OllamaModel descargado"

        if ($OllamaModel -ne "qwen3:8b") {
            Write-Info "Descargando modelo base qwen3:8b también..."
            & ollama pull qwen3:8b
        }
    }
} else {
    Write-Warn "Saltando instalación de Ollama"
}

# ─────────────────────────────────────────────────────────────────────────────
# 6. Node.js & Frontend
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Verificando Node.js"

try {
    $nodeVer = & node --version 2>&1
    Write-Ok "Node.js: $nodeVer"
} catch {
    Write-Warn "Node.js no encontrado. Instalando via winget..."
    winget install --id OpenJS.NodeJS.LTS -e --silent --accept-source-agreements --accept-package-agreements
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    Write-Ok "Node.js instalado"
}

Write-Step "Instalando dependencias del frontend"
Set-Location $FRONTEND_DIR
& npm install --silent
Write-Ok "Dependencias frontend instaladas"

# ─────────────────────────────────────────────────────────────────────────────
# 7. Archivo de configuración (.env)
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "Configurando .env"
Set-Location $SCRIPT_DIR

$envFile    = Join-Path $SCRIPT_DIR ".env"
$envExample = Join-Path $SCRIPT_DIR ".env.example"

if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        # Actualizar el modelo en .env según el hardware detectado
        (Get-Content $envFile) `
            -replace "^OLLAMA_DEFAULT_MODEL=.*", "OLLAMA_DEFAULT_MODEL=$OllamaModel" `
            | Set-Content $envFile -Encoding utf8
        Write-Ok ".env creado desde .env.example (modelo: $OllamaModel)"
    } else {
        Write-Warn ".env.example no encontrado — crea .env manualmente si lo necesitas"
    }
} else {
    Write-Ok ".env ya existe (no se sobreescribió)"
}

# ─────────────────────────────────────────────────────────────────────────────
# 8. Resumen final
# ─────────────────────────────────────────────────────────────────────────────
Write-Host @"

╔══════════════════════════════════════════════════════╗
║              INSTALACIÓN COMPLETADA                  ║
╠══════════════════════════════════════════════════════╣
║  Para iniciar la aplicación:                        ║
║                                                      ║
║    .\start.bat                                       ║
║                                                      ║
║  Modelo IA instalado: $($OllamaModel.PadRight(31))║
║                                                      ║
║  URLs:                                               ║
║    Frontend:  http://localhost:5173                  ║
║    Backend:   http://localhost:8000                  ║
║    API Docs:  http://localhost:8000/api/docs         ║
╚══════════════════════════════════════════════════════╝
"@ -ForegroundColor Green

Set-Location $SCRIPT_DIR
