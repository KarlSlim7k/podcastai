# PodcastAI

Transcripción local de podcasts y videos con IA + editor de clips verticales (9:16).

Todo corre en tu máquina. Sin servidores externos, sin cuentas obligatorias, sin telemetría.

## Características

- **Transcripción automática** — faster-whisper (large-v3) con soporte NVIDIA CUDA, Apple Silicon (mlx-whisper) y CPU
- **Análisis con IA** — resumen, puntos clave, clips virales, preguntas frecuentes y 20 tipos de análisis más
- **Chat con el contenido** — pregunta sobre tu podcast o video usando RAG (búsqueda semántica)
- **Editor de clips verticales 9:16** — estilo OpusClips: captions animados, b-roll, marca de agua y reencuadre automático por detección de cara
- **Renderizado en lote** — exporta varios clips simultáneamente con control de concurrencia GPU/CPU
- **Detección de hardware automática** — el encoder de ffmpeg (NVENC / VideoToolbox / libx264) y el backend de Whisper se eligen solos según tu equipo
- **Exportación** — TXT, DOCX, PDF, MD, JSON, SRT, VTT
- **100% local y privado** — los archivos nunca salen de tu máquina

## Requisitos de hardware

El script de instalación detecta tu hardware y descarga el modelo recomendado automáticamente.

| Hardware | VRAM / RAM | Modelo Ollama recomendado | Velocidad Whisper |
|---|---|---|---|
| NVIDIA RTX 4080 / 4090 | ≥ 16 GB | `qwen3:14b` | Muy rápida (CUDA) |
| NVIDIA RTX 3060 / 3070 / 4070 | 8–12 GB | `qwen3:8b` | Rápida (CUDA) |
| NVIDIA RTX 3050 / GTX 1660 | 4–6 GB | `qwen3:4b` | Moderada (CUDA) |
| NVIDIA GPU baja / integrada | < 4 GB | `qwen3:1.7b` | Lenta |
| Apple Silicon M2 Pro / M3 / M4 (24 GB+) | 24–96 GB unif. | `qwen3:14b` | Muy rápida (mlx) |
| Apple Silicon M1 / M2 (16 GB) | 16 GB unif. | `qwen3:8b` | Rápida (mlx) |
| Apple Silicon M1 / M2 (8 GB) | 8 GB unif. | `qwen3:4b` | Moderada (mlx) |
| CPU solamente | — | `qwen3:1.7b` | Muy lenta |

> La primera transcripción descarga el modelo Whisper `large-v3` (~3 GB) automáticamente.
> Si tu GPU tiene poca VRAM, usa `WHISPER_MODEL=medium` o `WHISPER_MODEL=small` en `.env`.

## Prerrequisitos

| Herramienta | Versión | Notas |
|---|---|---|
| Python | 3.12+ | `install.ps1` lo instala en Windows si no está presente |
| Node.js | 18+ | `install.ps1` lo instala en Windows si no está presente |
| FFmpeg | cualquiera | `install.ps1` lo instala en Windows si no está presente |
| Ollama | 0.3+ | Los scripts de instalación lo descargan automáticamente |
| Drivers NVIDIA | actualizados | Solo si tienes GPU NVIDIA |

## Instalación

### Windows

Abre **PowerShell como Administrador** y ejecuta:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
.\install.ps1
```

El instalador:
1. Verifica/instala Python 3.12, FFmpeg, Node.js y Ollama
2. Detecta tu GPU y VRAM con `nvidia-smi`
3. Selecciona y descarga el modelo Ollama óptimo para tu hardware
4. Crea el entorno virtual Python e instala todas las dependencias del backend
5. Instala las dependencias del frontend con npm
6. Crea `.env` con la configuración por defecto ajustada a tu modelo

Para forzar un modelo específico:

```powershell
.\install.ps1 -OllamaModel qwen3:14b
```

Para omitir pasos (si ya tienes algo instalado):

```powershell
.\install.ps1 -SkipPython -SkipFFmpeg
```

### macOS

```bash
chmod +x install.sh
./install.sh
```

Para forzar un modelo específico:

```bash
./install.sh qwen3:14b
```

En Apple Silicon el instalador detecta tu memoria unificada, recomienda el modelo adecuado e instala `mlx-whisper` automáticamente para máxima velocidad usando el Neural Engine.

### Linux

```bash
chmod +x install.sh
./install.sh
```

El script usa `curl -fsSL https://ollama.com/install.sh | sh` para instalar Ollama si no está presente. En distribuciones que no sean Debian/Ubuntu puede que necesites instalar Python 3.12, Node.js y FFmpeg manualmente antes de ejecutar el script.

## Ejecutar la aplicación

**Windows:**
```bat
start.bat
```

**macOS / Linux:**
```bash
./start.sh
```

Inicia Ollama, el backend (puerto 8000) y el frontend (puerto 5173). El script verifica que el backend esté respondiendo antes de abrir el navegador.

| URL | Descripción |
|---|---|
| http://localhost:5173 | Interfaz principal |
| http://localhost:8000 | API REST |
| http://localhost:8000/api/docs | Documentación interactiva (Swagger) |

Los logs se guardan en la raíz del proyecto:

| Archivo | Contenido |
|---|---|
| `logs_backend.txt` | Log del servidor FastAPI |
| `logs_frontend.txt` | Log de Vite (macOS/Linux) |
| `logs_ollama.txt` | Log del proceso Ollama |

En Windows el backend y el frontend abren cada uno en su propia ventana de terminal donde puedes ver los errores en tiempo real.

## Configuración

El instalador crea `.env` desde `.env.example` automáticamente. Los ajustes más comunes:

```env
# Modelo Whisper — opciones: tiny | base | small | medium | large-v3
# large-v3 requiere ~3 GB VRAM (se descarga la primera vez que transcribes)
# Usa "small" si tienes GPU con poca VRAM o solo CPU
WHISPER_MODEL=large-v3

# Modelo Ollama (el instalador lo ajusta según tu hardware)
OLLAMA_DEFAULT_MODEL=qwen3:8b

# B-roll con Pexels (opcional — sin key usa b-rolls de muestra integrados)
# Key gratuita en: https://www.pexels.com/api/
PEXELS_API_KEY=

# Tamaño máximo de archivo a subir
MAX_FILE_SIZE_MB=2048
```

## Solución de problemas

**El backend no inicia**
- Windows: mira la ventana "PodcastAI Backend" o abre `logs_backend.txt`
- macOS/Linux: `cat logs_backend.txt`
- Causa frecuente: FFmpeg no está en el PATH — verifica con `ffmpeg -version`

**La transcripción es muy lenta**
- Cambia `WHISPER_MODEL=large-v3` por `WHISPER_MODEL=medium` o `WHISPER_MODEL=small` en `.env`
- Verifica que PyTorch detecta tu GPU (activa el entorno virtual primero):
  ```bash
  # macOS/Linux
  source backend/.venv/bin/activate
  python -c "import torch; print('CUDA:', torch.cuda.is_available())"

  # Windows
  backend\.venv\Scripts\activate
  python -c "import torch; print('CUDA:', torch.cuda.is_available())"
  ```

**Ollama no responde / el análisis no funciona**
- Ejecuta `ollama serve` en una terminal y déjala abierta
- Verifica que el modelo está descargado: `ollama list`
- Si cambiaste de modelo, descárgalo primero: `ollama pull qwen3:14b`

**"CUDA out of memory" al transcribir**
- Baja el modelo Whisper en `.env`: `WHISPER_MODEL=medium`
- Cierra otras apps que usen la GPU antes de transcribir

**Windows: error "ejecución de scripts está deshabilitada"**
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
```

**macOS: "ffmpeg not found" al iniciar**
```bash
brew install ffmpeg
```

**La primera transcripción tarda mucho en iniciar**
Normal: descarga el modelo Whisper large-v3 (~3 GB) solo la primera vez. Las siguientes inician inmediatamente.

**Los renders de video salen corruptos o sin audio**
- Verifica que el archivo fuente no está abierto en otro programa
- Confirma que FFmpeg está en el PATH: `ffmpeg -version`

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), SQLite, Alembic |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Transcripción | faster-whisper (CUDA/CPU), mlx-whisper (Apple Silicon) |
| IA / LLM | Ollama (local), llama-cpp-python (fallback GGUF) |
| Video | FFmpeg, OpenCV, MediaPipe (detección de cara) |
| Tests | pytest, pytest-asyncio, pytest-cov — 264 tests, 80%+ cobertura |
