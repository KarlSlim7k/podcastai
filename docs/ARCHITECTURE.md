# Arquitectura

## Tech stack

| Capa | Tecnología |
|------|-----------|
| **Backend** | Python 3.11+ / FastAPI |
| **Base de datos** | Async SQLAlchemy + SQLite |
| **Frontend** | React 18 + TypeScript + Vite |
| **UI** | Tailwind CSS, React Router, TanStack Query |
| **Transcripción** | faster-whisper (CUDA) / mlx-whisper (Apple Silicon) |
| **IA / Análisis** | Ollama (Qwen3:14b, Gemma3:4b) |
| **Detección facial** | MediaPipe (auto-reframe) |
| **Renderizado** | ffmpeg con GPU (NVENC / VideoToolbox / libx264) |

## Pipeline de datos

```
Upload → Transcripción → Análisis → Clips → Editor Vertical → Publicación
                        ↓
                    Chat RAG
                        ↓
                    Exportación
```

### Flujo detallado

1. **Upload**: El usuario sube un archivo de audio/video → `backend/data/uploads/`
2. **Transcripción**: Whisper transcribe → se guarda en SQLite como segments con timestamps
3. **Análisis**: Ollama genera 17 tipos de análisis (resumen, keywords, sentimiento, etc.)
4. **Clips**:
   - Detección de clips basada en silencios / análisis de contenido
   - Score de viralidad (0-100) vía Ollama
   - B-rolls sugeridos (Pexels + Ollama)
5. **Editor vertical**: Renderiza clips en formato 1080×1920 con:
   - Subtítulos (6 estilos: Standard, Karaoke, Neon, MrBeast, Hormozi, TikTok Classic)
   - Watermark
   - Auto-reframe (MediaPipe face tracking)
   - B-rolls superpuestos
6. **Publicación**: Mock o real a TikTok / YouTube Shorts / Instagram Reels
7. **Exportación**: TXT, DOCX, PDF, MD, JSON, SRT, VTT

## Backend módulos

```
backend/app/
├── main.py              # Entrypoint, lifespan, middleware, routers
├── config.py            # Config pydantic-settings (env vars, paths)
├── database.py          # Async SQLAlchemy session factory
├── models/
│   ├── project.py       # ORM: Project, Clip, VerticalPreset, VerticalRender, SocialAccount
│   └── schemas.py       # Pydantic schemas request/response
├── routers/             # Endpoints API
│   ├── projects.py      # CRUD proyectos
│   ├── upload.py        # Subida de archivos
│   ├── transcription.py # Transcripción Whisper
│   ├── analysis.py      # 17 tipos de análisis IA
│   ├── chat.py          # Chat RAG sobre transcripciones
│   ├── export.py        # Exportación multi-formato
│   ├── clips.py         # Clips, viralidad, b-rolls
│   ├── vertical.py      # Editor vertical (presets, watermark, renders)
│   ├── social.py        # OAuth y publicación
│   └── system.py        # Health, hardware, status
├── services/            # Lógica de negocio
│   ├── transcription_service.py
│   ├── ai_service.py          # Ollama
│   ├── virality_service.py    # Score de viralidad
│   ├── clips_service.py       # Detección/generación de clips
│   ├── vertical_editor_service.py  # Renderizado ffmpeg GPU
│   ├── face_detection.py      # MediaPipe auto-reframe
│   ├── broll_service.py       # Pexels + Ollama
│   ├── social_publisher.py    # Publicación redes
│   ├── rag_service.py         # Chunking + retrieval
│   ├── export_service.py      # Exportación
│   ├── diarization_service.py # Diarización de hablantes
│   └── whisper_backends/      # Factory pattern
│       ├── base.py
│       ├── factory.py
│       ├── faster_whisper_backend.py
│       └── mlx_whisper_backend.py
└── utils/
    ├── hardware.py       # Detección OS/GPU/encoder
    ├── logger.py         # Structlog
    ├── security.py       # Sanitización
    └── file_validator.py # Validación uploads
```

## Frontend módulos

```
frontend/src/
├── main.tsx             # Entrypoint React
├── pages/               # Páginas principales
├── components/
│   ├── features/        # Componentes de funcionalidad (VerticalEditor, ClipsPanel, etc.)
│   ├── layout/          # AppLayout, Sidebar
│   └── ui/              # Primitivos (Button, Card, Modal, Badge, ProgressBar)
├── hooks/               # React Query hooks
├── services/api.ts      # Cliente Axios
├── types/index.ts       # Tipos TypeScript
└── utils/index.ts       # Utilidades
```

## Soporte multiplataforma

El sistema detecta automáticamente el hardware al iniciar y elige el backend óptimo:

| OS | Backend Whisper | Codificador ffmpeg | Aceleración |
|----|----------------|-------------------|-------------|
| Windows + NVIDIA | faster-whisper (CUDA) | h264_nvenc | CUDA |
| macOS Apple Silicon | mlx-whisper | h264_videotoolbox | Metal / Neural Engine |
| Linux + NVIDIA | faster-whisper (CUDA) | h264_nvenc | CUDA |
| Linux + AMD | faster-whisper (CPU) | libx264 | CPU |
| Cualquier CPU | faster-whisper (CPU) | libx264 | CPU |

## Docker

```bash
docker-compose up --build
```

Incluye:
- Backend con paso de GPU NVIDIA (`runtime: nvidia`)
- Frontend servido por nginx con proxy reverso a `/api`
- Healthchecks en ambos servicios
