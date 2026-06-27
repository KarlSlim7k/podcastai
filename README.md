# PodcastAI

Transcripción local de podcasts y videos con IA + editor de clips verticales (9:16).

Todo corre en tu máquina. Sin servidores externos, sin cuentas obligatorias, sin telemetría.

## Características

- **Transcripción automática** — faster-whisper (large-v3) con soporte NVIDIA CUDA, Apple Silicon (mlx-whisper) y CPU
- **Análisis con IA** — resumen, puntos clave, clips virales, preguntas frecuentes y 20 tipos de análisis más
- **Chat con el contenido** — pregunta sobre tu podcast o video usando RAG (búsqueda semántica)
- **Editor de clips verticales 9:16** — estilo OpusClips: captions animados, b-roll, marca de agua y reencuadre por detección de cara
- **Renderizado en lote** — exporta varios clips simultáneamente con control de concurrencia GPU/CPU
- **Exportación** — TXT, DOCX, PDF, MD, JSON, SRT, VTT
- **100% local y privado** — los archivos nunca salen de tu máquina

## Instalación rápida

> **Prerrequisitos:** Python 3.12+, Node.js 18+, FFmpeg, Ollama · El script de Windows los instala automáticamente.
> Guía completa e instrucciones por sistema operativo → [`docs/INSTALL.md`](docs/INSTALL.md)

**Windows** (PowerShell como Administrador):
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
.\install.ps1
```

**macOS / Linux:**
```bash
chmod +x install.sh && ./install.sh
```

El instalador detecta tu GPU/RAM, selecciona el modelo Ollama óptimo para tu hardware y configura `.env` automáticamente.

## Ejecutar

**Windows:**
```bat
start.bat
```

**macOS / Linux:**
```bash
./start.sh
```

| URL | Descripción |
|---|---|
| http://localhost:5173 | Interfaz principal |
| http://localhost:8000/api/docs | API interactiva (Swagger) |

## Modelos recomendados

| Hardware | Modelo Ollama | Whisper |
|---|---|---|
| NVIDIA ≥ 12 GB VRAM | `qwen3:14b` | CUDA — rápido |
| NVIDIA 6–12 GB VRAM | `qwen3:8b` | CUDA — rápido |
| NVIDIA 4–6 GB VRAM | `qwen3:4b` | CUDA — moderado |
| Apple Silicon ≥ 16 GB | `qwen3:8b`–`qwen3:14b` | mlx-whisper — rápido |
| CPU / GPU baja | `qwen3:1.7b` | CPU — lento |

> La primera transcripción descarga Whisper `large-v3` (~3 GB) automáticamente. Con poca VRAM usa `WHISPER_MODEL=medium` en `.env`.

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/INSTALL.md`](docs/INSTALL.md) | Requisitos, instalación paso a paso por OS, opciones avanzadas |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Solución de los problemas más comunes |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Estructura del proyecto, decisiones de diseño |
| [`docs/SOCIAL_SETUP.md`](docs/SOCIAL_SETUP.md) | Configuración de OAuth para publicar en TikTok / YouTube / Instagram |
| [`docs/TESTS.md`](docs/TESTS.md) | Cómo correr la suite de tests (264 tests, 80%+ cobertura) |
| [`.env.example`](.env.example) | Referencia de todas las variables de entorno |

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy async, SQLite |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Transcripción | faster-whisper (CUDA/CPU), mlx-whisper (Apple Silicon) |
| IA / LLM | Ollama (local), llama-cpp-python (fallback GGUF) |
| Video | FFmpeg, OpenCV, MediaPipe |

## Licencia

MIT — ver [`LICENSE`](LICENSE)
