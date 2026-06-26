import asyncio
import subprocess
import json
from pathlib import Path
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AudioExtractor:
    def __init__(self):
        self._ffmpeg = self._find_ffmpeg()

    def _find_ffmpeg(self) -> str:
        candidates = ["ffmpeg", r"C:\ffmpeg\bin\ffmpeg.exe", r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"]
        for c in candidates:
            try:
                result = subprocess.run([c, "-version"], capture_output=True, timeout=5)
                if result.returncode == 0:
                    return c
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        raise RuntimeError("FFmpeg not found. Please install FFmpeg and add it to PATH.")

    async def get_duration(self, file_path: Path) -> float:
        cmd = [
            self._ffmpeg.replace("ffmpeg", "ffprobe"),
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            str(file_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        try:
            data = json.loads(stdout)
            for stream in data.get("streams", []):
                if stream.get("duration"):
                    return float(stream["duration"])
        except Exception:
            pass
        return 0.0

    async def extract_audio(
        self,
        input_path: Path,
        output_path: Path,
        sample_rate: int = 16000,
        channels: int = 1,
        progress_callback=None,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self._ffmpeg,
            "-y",
            "-i", str(input_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", str(sample_rate),
            "-ac", str(channels),
            "-f", "wav",
            str(output_path),
        ]

        logger.info("extracting_audio", input=str(input_path), output=str(output_path))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error = stderr.decode("utf-8", errors="replace")
            logger.error("ffmpeg_error", error=error)
            raise RuntimeError(f"FFmpeg extraction failed: {error[-500:]}")

        if not output_path.exists():
            raise RuntimeError("Audio extraction produced no output file")

        logger.info("audio_extracted", output=str(output_path), size=output_path.stat().st_size)
        return output_path

    def is_audio_file(self, filename: str) -> bool:
        return Path(filename).suffix.lower() in {".mp3", ".wav", ".m4a", ".aac"}


audio_extractor = AudioExtractor()
