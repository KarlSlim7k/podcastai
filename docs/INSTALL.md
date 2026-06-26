# Instalación

## Requisitos de hardware

| OS | GPU | Recomendado | Mínimo |
|----|-----|-------------|--------|
| **Windows 10/11** | NVIDIA RTX 2060+ | RTX 3060 12GB, ffmpeg con NVENC | 8GB VRAM |
| **Linux** | NVIDIA / AMD | NVIDIA RTX 3060+ | NVIDIA GTX 1060 6GB |
| **macOS 13+** | Apple Silicon (M1/M2/M3/M4) | M2 Pro 16GB+ | M1 8GB |
| **macOS Intel** | ❌ No recomendado | — | 16GB RAM, muy lento |

- **Disco**: ~15 GB para modelos (Whisper large-v3, Ollama, MediaPipe TFLite)
- **RAM**: 16 GB recomendada (8 GB mínimo para modelos pequeños)
- **Almacenamiento**: SSD recomendado

## Instalación rápida

### Windows 11 (NVIDIA)

```powershell
# PowerShell como Administrador:
powershell -ExecutionPolicy Bypass -File install.ps1
```

El script instala: Python 3.11, ffmpeg (BtbN con NVENC), Ollama, Node.js y todas las dependencias.

### macOS (Apple Silicon)

```bash
# 1. Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Dependencias
brew install python@3.11 ffmpeg node ollama

# 3. Iniciar Ollama
brew services start ollama
# o: ollama serve &

# 4. Modelos IA
ollama pull qwen3:14b
ollama pull gemma3:4b

# 5. Clonar y ejecutar
git clone <repo-url> transcripciones
cd transcripciones
./start.sh
```

### Linux (Ubuntu/Debian + NVIDIA)

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv ffmpeg nodejs npm curl
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:14b
ollama pull gemma3:4b
git clone <repo-url> transcripciones
cd transcripciones
chmod +x start.sh
./start.sh
```

## Instalación manual

### 1. Dependencias del sistema

| Herramienta | Por qué | Instalación |
|-------------|---------|-------------|
| **Python 3.11** | Backend | python.org / `brew install python@3.11` / `apt install python3.11` |
| **ffmpeg** | Renderizado de video | `brew install ffmpeg` / `apt install ffmpeg` / BtbN en Windows |
| **Node.js 20+** | Frontend | nodejs.org / `brew install node` |
| **Ollama** | LLM local | ollama.com/download |

Verificar codificador de hardware:

```bash
ffmpeg -hide_banner -encoders | grep -E "h264_nvenc|h264_videotoolbox|h264_qsv"
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

**Apple Silicon (opcional, recomendado)**:
```bash
pip install mlx-whisper
```

**NVIDIA GPU (opcional, para auto-reframe acelerado por GPU)**:
```bash
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121
```

### 3. Frontend

```bash
cd ../frontend
npm install
```

### 4. Modelos Ollama

```bash
ollama serve &
ollama pull qwen3:14b
ollama pull gemma3:4b
```

## Ejecutar la app

### Un comando (recomendado)

```bash
./start.sh          # macOS / Linux / Git Bash
start.bat           # Windows (cmd / PowerShell)
```

Logs: `logs_backend.txt`, `logs_frontend.txt`, `logs_ollama.txt`.

### Tres terminales (control manual)

```bash
# Terminal 1: Ollama
ollama serve

# Terminal 2: Backend
cd backend && source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 3: Frontend
cd frontend && npm run dev
```

### URLs

| Servicio | URL |
|----------|-----|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/api/docs |
| Ollama | http://localhost:11434 |

## API keys

Crea un archivo `.env` en la raíz:

```bash
cp .env.example .env
```

| Key | Obligatoria | Para qué |
|-----|-------------|----------|
| `PEXELS_API_KEY` | ❌ (usa mocks) | B-rolls con fotos reales |
| TikTok / YouTube / IG keys | ❌ (usa mocks) | Publicación directa |

### Pexels (recomendado, gratis)

1. Regístrate en https://www.pexels.com/api/ (200 req/hora, 20K/mes)
2. Agrega a `.env`: `PEXELS_API_KEY=tu_key`

### Redes sociales

Ver [SOCIAL_SETUP.md](SOCIAL_SETUP.md).
