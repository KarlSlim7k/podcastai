#!/usr/bin/env bash
# ============================================================================
#  PodcastAI - Script de instalación (macOS / Linux)
# ============================================================================
#
#  Uso:
#    ./install.sh                  # detecta hardware y elige modelo automáticamente
#    ./install.sh qwen3:14b        # fuerza un modelo de Ollama concreto
#
#  Qué hace:
#    1. Verifica Python 3.12+, Node.js 18+, FFmpeg y Ollama
#    2. Detecta GPU/VRAM (NVIDIA) o memoria unificada (Apple Silicon)
#    3. Descarga el modelo Ollama recomendado para tu hardware
#    4. Crea el entorno virtual Python e instala dependencias del backend
#    5. Instala mlx-whisper en Apple Silicon (transcripción vía Neural Engine)
#    6. Instala dependencias del frontend (npm)
#    7. Crea .env desde .env.example si no existe
# ============================================================================

set -euo pipefail

# ── Colores / helpers ────────────────────────────────────────────────────────
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

say()  { echo -e "${BLUE}[PASO]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}   $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[ERR]${NC}  $*"; exit 1; }
info() { echo -e "       $*"; }

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# ── Detección de OS ──────────────────────────────────────────────────────────
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
IS_APPLE_SILICON=false

case "$OS" in
  darwin)
    [ "$ARCH" = "arm64" ] && IS_APPLE_SILICON=true
    ;;
  linux)
    ;;
  *)
    fail "Sistema operativo no soportado: $OS. Usa install.ps1 en Windows."
    ;;
esac

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║          PodcastAI - Instalación Automática          ║"
echo "║      Transcripción y Análisis Local con IA           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

if [ "$IS_APPLE_SILICON" = "true" ]; then
  ok "Apple Silicon detectado (M-series)"
else
  info "OS: $OS ($ARCH)"
fi
echo ""

# ── 1. Python 3.12+ ──────────────────────────────────────────────────────────
say "Verificando Python 3.12+"

PYTHON=""
for cmd in python3.13 python3.12 python3 python; do
  if command -v "$cmd" >/dev/null 2>&1; then
    ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    if [ "$major" -eq 3 ] && [ "$minor" -ge 12 ]; then
      PYTHON="$cmd"
      ok "Python $("$cmd" --version 2>&1)"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  warn "Python 3.12+ no encontrado."
  if [ "$OS" = "darwin" ]; then
    info "Instala con Homebrew:  brew install python@3.12"
    info "O descarga desde:      https://www.python.org/downloads/"
  else
    info "Ubuntu/Debian:  sudo apt install python3.12 python3.12-venv python3.12-dev"
    info "Otras distros:  usa tu gestor de paquetes o https://www.python.org/"
  fi
  fail "Instala Python 3.12+ y vuelve a ejecutar este script."
fi

# ── 2. Node.js 18+ ───────────────────────────────────────────────────────────
say "Verificando Node.js 18+"

if command -v node >/dev/null 2>&1; then
  NODE_VER=$(node --version | tr -d 'v' | cut -d. -f1)
  if [ "$NODE_VER" -ge 18 ]; then
    ok "Node.js $(node --version)"
  else
    warn "Node.js $(node --version) detectado, se necesita v18+."
    if [ "$OS" = "darwin" ]; then
      info "Actualiza con: brew upgrade node"
    else
      info "Actualiza con nvm: nvm install --lts"
    fi
    fail "Actualiza Node.js a v18+ y vuelve a ejecutar."
  fi
else
  warn "Node.js no encontrado."
  if [ "$OS" = "darwin" ]; then
    info "Instala con: brew install node"
  else
    info "Ubuntu/Debian: sudo apt install nodejs npm"
    info "O usa nvm: https://github.com/nvm-sh/nvm"
  fi
  fail "Instala Node.js 18+ y vuelve a ejecutar este script."
fi

# ── 3. FFmpeg ────────────────────────────────────────────────────────────────
say "Verificando FFmpeg"

if command -v ffmpeg >/dev/null 2>&1; then
  ok "FFmpeg: $(ffmpeg -version 2>&1 | head -1 | cut -d' ' -f1-3)"
else
  warn "FFmpeg no encontrado."
  if [ "$OS" = "darwin" ]; then
    info "Instala con: brew install ffmpeg"
  else
    info "Ubuntu/Debian: sudo apt install ffmpeg"
  fi
  fail "FFmpeg es necesario para el editor de clips. Instálalo y vuelve a ejecutar."
fi

# ── 4. Ollama ────────────────────────────────────────────────────────────────
say "Verificando Ollama"

if ! command -v ollama >/dev/null 2>&1; then
  warn "Ollama no encontrado. Instalando..."
  if [ "$OS" = "darwin" ] && command -v brew >/dev/null 2>&1; then
    brew install ollama
  else
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  ok "Ollama instalado"
else
  ok "Ollama: $(ollama version 2>&1 | head -1)"
fi

# ── 5. Detección de hardware y selección de modelo ───────────────────────────
say "Detectando hardware..."

OLLAMA_MODEL="${1:-}"
VRAM_MB=0
RAM_GB=0

if [ "$IS_APPLE_SILICON" = "true" ]; then
  RAM_RAW=$(system_profiler SPHardwareDataType 2>/dev/null | grep "Memory:" | grep -oE '[0-9]+' | head -1)
  RAM_GB="${RAM_RAW:-0}"
  ok "Apple Silicon — Memoria unificada: ${RAM_GB} GB"

  if [ -z "$OLLAMA_MODEL" ]; then
    if [ "$RAM_GB" -ge 32 ] 2>/dev/null; then
      OLLAMA_MODEL="qwen3:14b"
    elif [ "$RAM_GB" -ge 16 ] 2>/dev/null; then
      OLLAMA_MODEL="qwen3:8b"
    elif [ "$RAM_GB" -ge 12 ] 2>/dev/null; then
      OLLAMA_MODEL="qwen3:4b"
    else
      OLLAMA_MODEL="qwen3:4b"
    fi
  fi

elif [ "$OS" = "linux" ] && command -v nvidia-smi >/dev/null 2>&1; then
  VRAM_STR=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d '[:space:]')
  if [ -n "$VRAM_STR" ] && echo "$VRAM_STR" | grep -qE '^[0-9]+$'; then
    VRAM_MB="$VRAM_STR"
    VRAM_GB_INT=$(( VRAM_MB / 1024 ))
    ok "NVIDIA GPU detectada — VRAM: ${VRAM_GB_INT} GB"

    if [ -z "$OLLAMA_MODEL" ]; then
      if [ "$VRAM_MB" -ge 12000 ]; then
        OLLAMA_MODEL="qwen3:14b"
      elif [ "$VRAM_MB" -ge 6000 ]; then
        OLLAMA_MODEL="qwen3:8b"
      elif [ "$VRAM_MB" -ge 4000 ]; then
        OLLAMA_MODEL="qwen3:4b"
      else
        OLLAMA_MODEL="qwen3:1.7b"
      fi
    fi
  fi
fi

if [ -z "$OLLAMA_MODEL" ]; then
  OLLAMA_MODEL="qwen3:4b"
  warn "No se detectó GPU con VRAM conocida. Modelo por defecto: $OLLAMA_MODEL"
  info "Para usar un modelo más potente: ./install.sh qwen3:8b"
fi

info "Modelo seleccionado: $OLLAMA_MODEL"
info "(Para cambiarlo: ./install.sh qwen3:14b)"
echo ""

# ── 6. Entorno virtual Python + dependencias ─────────────────────────────────
say "Configurando entorno Python"

VENV="$BACKEND_DIR/.venv"

if [ ! -d "$VENV" ]; then
  info "Creando entorno virtual en $VENV..."
  (cd "$BACKEND_DIR" && "$PYTHON" -m venv .venv)
  ok "Entorno virtual creado"
else
  ok "Entorno virtual ya existe"
fi

PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

info "Actualizando pip..."
"$PIP" install --upgrade pip --quiet

# PyTorch: CUDA en Linux con NVIDIA, CPU/MPS en macOS y el resto
if [ "$OS" = "linux" ] && [ "$VRAM_MB" -gt 0 ]; then
  info "Instalando PyTorch con soporte CUDA 12.1..."
  "$PIP" install torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu121 --quiet
else
  info "Instalando PyTorch (CPU/MPS)..."
  "$PIP" install torch torchvision torchaudio --quiet
fi

info "Instalando dependencias del backend..."
(cd "$BACKEND_DIR" && "$PIP" install -r requirements.txt --quiet)
ok "Dependencias Python instaladas"

# mlx-whisper en Apple Silicon (transcripción vía Neural Engine)
if [ "$IS_APPLE_SILICON" = "true" ]; then
  echo ""
  info "Apple Silicon detectado. mlx-whisper ofrece transcripción más rápida"
  info "usando el Neural Engine. Se instalará automáticamente."
  "$PIP" install mlx-whisper --quiet
  ok "mlx-whisper instalado"
fi

# ── 7. Descargar modelo Ollama ───────────────────────────────────────────────
say "Descargando modelo Ollama: $OLLAMA_MODEL"
info "Esto puede tardar varios minutos la primera vez..."

# Arrancar Ollama si no está corriendo
if ! pgrep -f "ollama serve" >/dev/null 2>&1 && \
   ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  ollama serve > /dev/null 2>&1 &
  sleep 3
fi

ollama pull "$OLLAMA_MODEL"
ok "Modelo $OLLAMA_MODEL descargado"

# ── 8. Dependencias del frontend ─────────────────────────────────────────────
say "Instalando dependencias del frontend"
(cd "$FRONTEND_DIR" && npm install --silent)
ok "Dependencias Node.js instaladas"

# ── 9. Crear .env ────────────────────────────────────────────────────────────
say "Configurando .env"

ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"

if [ ! -f "$ENV_FILE" ]; then
  if [ -f "$ENV_EXAMPLE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    # Actualizar el modelo en .env según el hardware detectado
    if [ "$OS" = "darwin" ]; then
      sed -i '' "s|^OLLAMA_DEFAULT_MODEL=.*|OLLAMA_DEFAULT_MODEL=$OLLAMA_MODEL|" "$ENV_FILE"
    else
      sed -i "s|^OLLAMA_DEFAULT_MODEL=.*|OLLAMA_DEFAULT_MODEL=$OLLAMA_MODEL|" "$ENV_FILE"
    fi
    ok ".env creado (modelo: $OLLAMA_MODEL)"
  else
    warn ".env.example no encontrado — crea .env manualmente si lo necesitas"
  fi
else
  ok ".env ya existe (no se sobreescribió)"
fi

# ── Resumen ──────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║              INSTALACIÓN COMPLETADA                  ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Para iniciar la aplicación:                        ║"
echo "║                                                      ║"
echo "║    ./start.sh                                        ║"
echo "║                                                      ║"
echo "║  URLs:                                               ║"
echo "║    Frontend:  http://localhost:5173                  ║"
echo "║    Backend:   http://localhost:8000                  ║"
echo "║    API Docs:  http://localhost:8000/api/docs         ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
