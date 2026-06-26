# Solución de problemas

## "ffmpeg not found"

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg

# Windows (PowerShell Admin)
choco install ffmpeg
# o descargar de https://www.gyan.dev/ffmpeg/builds/ y agregar al PATH
```

Verificar: `ffmpeg -version`

## "No GPU encoder available" — todo es lento

El sistema cae a `libx264` (CPU). Es 5-10x más lento.

**Windows + NVIDIA**:
```bash
ffmpeg -hide_banner -encoders | findstr h264_nvenc
```
Usar build BtbN o gyan.dev (incluyen NVENC).

**macOS**: `brew install ffmpeg` ya incluye `h264_videotoolbox`.

**Linux + NVIDIA**:
```bash
ffmpeg -hide_banner -encoders | grep h264_nvenc
```
Si no aparece, probar static build de johnvansickle.com.

## "mlx_whisper not installed" en macOS

Es una advertencia, no error. Cae a `faster-whisper` (más lento pero funciona).

Para instalar mlx-whisper (Apple Silicon):
```bash
cd backend && source .venv/bin/activate
pip install mlx-whisper
```

## "Address already in use" (puerto 8000)

```bash
# macOS / Linux
lsof -i :8000
kill -9 <PID>

# Windows (PowerShell)
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

## "Port 5173 is in use"

Lo mismo pero para el frontend. O cambiar el puerto en `frontend/vite.config.ts`.

## "CUDA out of memory"

El modelo Whisper es muy grande para tu VRAM. Soluciones:
1. En `backend/app/config.py`, cambiar `whisper_model: str = "large-v3"` a `"medium"` o `"small"`
2. Cerrar otras apps que usen GPU (navegador con aceleración, juegos, etc.)

## Ollama no responde

```bash
curl http://localhost:11434/api/tags
# Si no responde:
ollama serve
# Logs: ~/.ollama/logs/server.log
```

## Virality score / b-rolls en "pending" forever

Ollama no está corriendo. Iniciar con `ollama serve` y click en "Recalcular".

## B-rolls de Pexels genéricos (mock mode)

No configuraste `PEXELS_API_KEY` en `.env`. El panel muestra un banner amarillo en mock mode. Ver [INSTALL.md](INSTALL.md#api-keys).

## Watermark upload falla

Formatos: PNG, JPG, SVG. Máximo 5 MB. Si no aparece en el render:
- Verificar que sea un PNG válido
- Verificar posición dentro del frame 1080×1920
- Probar opacidad ≥ 0.3

## Auto-reframe no sigue a nadie

MediaPipe `blaze_face_short_range` funciona mejor con primeros planos. Caras pequeñas (planos abiertos, reuniones) pueden no detectarse. Revisar logs:
- `auto_reframe_trajectory_built` → OK
- `auto_reframe_fallback_to_fill` → cayó a center crop

## Publicación en redes en mock mode

Funciona sin credenciales OAuth — simula upload de 2s y devuelve URL falsa. Para habilitar plataformas reales, ver [SOCIAL_SETUP.md](SOCIAL_SETUP.md).

## Tests fallan con "no such table"

Correr migraciones en orden:
```bash
cd backend
.venv/Scripts/python.exe tests/phase6_migrate.py
.venv/Scripts/python.exe tests/phase7_migrate_title_text.py
.venv/Scripts/python.exe tests/phase8_migrate_virality.py
.venv/Scripts/python.exe tests/phase12_migrate_social.py
```

Cada una es idempotente.
