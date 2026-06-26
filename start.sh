#!/usr/bin/env bash
# ============================================================================
#  PodcastAI Transcriber - Cross-platform start script
# ============================================================================
#  Works on:
#    - macOS (Apple Silicon or Intel)
#    - Linux (Ubuntu, Debian, Fedora, Arch, etc.)
#    - Windows (Git Bash) - just call start.sh instead of start.bat
#
#  What it does:
#    1. Detects the OS and Python interpreter
#    2. Creates a virtual environment if it doesn't exist
#    3. Installs Python dependencies
#    4. Starts Ollama (if installed and not already running)
#    5. Starts the FastAPI backend on port 8000
#    6. Starts the Vite frontend on port 5173
# ============================================================================
set -e

# --- Pretty output ---------------------------------------------------------
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

say()    { echo -e "${BLUE}>>>${NC} $*"; }
ok()     { echo -e "${GREEN}✓${NC} $*"; }
warn()   { echo -e "${YELLOW}!${NC} $*"; }
fail()   { echo -e "${RED}✗${NC} $*"; exit 1; }

# --- Project paths ---------------------------------------------------------
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VENV="$BACKEND_DIR/.venv"

# --- OS detection ----------------------------------------------------------
OS="unknown"
case "$(uname -s 2>/dev/null || echo Windows)" in
  Darwin*)  OS="darwin" ;;
  Linux*)   OS="linux"  ;;
  MINGW*|CYGWIN*|MSYS*) OS="windows_gitbash" ;;
  *)        OS="unknown" ;;
esac
say "Detected OS: $OS"

# --- Apple Silicon detection (macOS) ---------------------------------------
IS_APPLE_SILICON=false
if [ "$OS" = "darwin" ]; then
  if [ "$(uname -m)" = "arm64" ]; then
    IS_APPLE_SILICON=true
    ok "Apple Silicon detected - will use mlx-whisper if available"
  fi
fi

# --- Python ----------------------------------------------------------------
if [ "$OS" = "windows_gitbash" ]; then
  PY="$VENV/Scripts/python.exe"
  PIP="$VENV/Scripts/pip.exe"
else
  PY="$VENV/bin/python"
  PIP="$VENV/bin/pip"
fi

if [ ! -x "$PY" ]; then
  fail "Virtual environment not found at $VENV. Run: cd backend && python -m venv .venv"
fi

# --- ffmpeg check ----------------------------------------------------------
if ! command -v ffmpeg >/dev/null 2>&1; then
  warn "ffmpeg not found in PATH"
  if [ "$OS" = "darwin" ]; then
    warn "Install with: brew install ffmpeg"
  elif [ "$OS" = "linux" ]; then
    warn "Install with: sudo apt install ffmpeg   (or your distro's package manager)"
  else
    warn "Install ffmpeg and add it to PATH"
  fi
  fail "ffmpeg is required for the vertical editor. Install it first."
fi
ok "ffmpeg: $(ffmpeg -version 2>&1 | head -1)"

# --- Hardware detection ---------------------------------------------------
say "Detecting hardware..."
PYTHONPATH="$BACKEND_DIR" "$PY" -c \
  "from app.utils.hardware import detect_hardware, reset_cache; reset_cache(); print(detect_hardware().summary())" \
  2>/dev/null || warn "Detección de hardware no disponible (no afecta al arranque)"

# --- Optional: install mlx-whisper on macOS Apple Silicon ----------------
if [ "$IS_APPLE_SILICON" = "true" ]; then
  if ! "$PY" -c "import mlx_whisper" 2>/dev/null; then
    warn "mlx-whisper not installed (recommended for best performance)"
    warn "Install with: $PIP install mlx-whisper"
    warn "Falling back to faster-whisper for now (works fine, slightly slower)"
  fi
fi

# --- Ollama ----------------------------------------------------------------
if command -v ollama >/dev/null 2>&1; then
  if ! pgrep -f "ollama serve" >/dev/null 2>&1 && ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    say "Starting Ollama..."
    ollama serve > "$SCRIPT_DIR/logs_ollama.txt" 2>&1 &
    sleep 3
    ok "Ollama started"
  else
    ok "Ollama already running"
  fi
else
  warn "Ollama not found. Install from: https://ollama.com/download"
  warn "Skipping Ollama. AI features (clip detection, analysis, chat) won't work."
fi

# --- Start backend ---------------------------------------------------------
say "Starting FastAPI backend on http://localhost:8000 ..."
cd "$BACKEND_DIR"
"$PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > "$SCRIPT_DIR/logs_backend.txt" 2>&1 &
BACKEND_PID=$!
sleep 4
if ! kill -0 $BACKEND_PID 2>/dev/null; then
  fail "Backend failed to start. See logs_backend.txt for details."
fi
ok "Backend started (PID $BACKEND_PID)"

# --- Start frontend --------------------------------------------------------
say "Starting Vite frontend on http://localhost:5173 ..."
cd "$FRONTEND_DIR"
if [ ! -d node_modules ]; then
  warn "node_modules not found, running npm install first..."
  npm install
fi
npm run dev > "$SCRIPT_DIR/logs_frontend.txt" 2>&1 &
FRONTEND_PID=$!
sleep 5
if ! kill -0 $FRONTEND_PID 2>/dev/null; then
  fail "Frontend failed to start. See logs_frontend.txt for details."
fi
ok "Frontend started (PID $FRONTEND_PID)"

# --- Done ------------------------------------------------------------------
echo ""
ok "All services running!"
echo ""
echo "  Backend:  http://localhost:8000  (API docs: /api/docs)"
echo "  Frontend: http://localhost:5173"
echo "  Ollama:   http://localhost:11434"
echo ""
echo "  Logs:    logs_backend.txt   logs_frontend.txt   logs_ollama.txt"
echo ""
echo "  Press Ctrl+C to stop all services"
echo ""

# Wait for any of the PIDs to exit
wait $BACKEND_PID $FRONTEND_PID
