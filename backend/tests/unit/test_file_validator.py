import pytest
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from app.utils.file_validator import (
    sanitize_filename, validate_extension, validate_file_size,
    validate_path_safety, validate_upload_file,
)


class TestSanitizeFilename:
    def test_normal_filename(self):
        assert sanitize_filename("podcast.mp4") == "podcast.mp4"

    def test_filename_with_spaces(self):
        result = sanitize_filename("my podcast.mp4")
        assert ".mp4" in result

    def test_filename_with_special_chars(self):
        result = sanitize_filename("podcast/../evil.mp4")
        assert ".." not in result
        assert ".mp4" in result

    def test_filename_with_unicode(self):
        result = sanitize_filename("podcäst.mp3")
        assert ".mp3" in result

    def test_empty_stem(self):
        result = sanitize_filename(".mp4")
        assert ".mp4" in result


class TestValidateExtension:
    def test_valid_mp4(self):
        ext = validate_extension("video.mp4")
        assert ext == ".mp4"

    def test_valid_mp3(self):
        ext = validate_extension("audio.mp3")
        assert ext == ".mp3"

    def test_valid_mkv(self):
        ext = validate_extension("video.mkv")
        assert ext == ".mkv"

    def test_invalid_exe(self):
        with pytest.raises(HTTPException) as exc:
            validate_extension("malware.exe")
        assert exc.value.status_code == 400

    def test_invalid_pdf(self):
        with pytest.raises(HTTPException) as exc:
            validate_extension("document.pdf")
        assert exc.value.status_code == 400

    def test_case_insensitive(self):
        ext = validate_extension("VIDEO.MP4")
        assert ext == ".mp4"


class TestValidateFileSize:
    def test_valid_size(self):
        validate_file_size(100 * 1024 * 1024)  # 100 MB - should not raise

    def test_too_large(self):
        from app.config import settings
        max_bytes = settings.max_file_size_mb * 1024 * 1024
        with pytest.raises(HTTPException) as exc:
            validate_file_size(max_bytes + 1)
        assert exc.value.status_code == 413

    def test_zero_size(self):
        validate_file_size(0)  # should not raise


class TestValidatePathSafety:
    def test_valid_path(self, tmp_path):
        subdir = tmp_path / "sub" / "file.mp4"
        validate_path_safety(tmp_path, subdir)  # should not raise

    def test_path_traversal_detected(self, tmp_path):
        evil_path = tmp_path / ".." / "etc" / "passwd"
        with pytest.raises(HTTPException) as exc:
            validate_path_safety(tmp_path, evil_path)
        assert exc.value.status_code == 400


class TestValidateUploadFile:
    def _make_upload(self, filename: str, content: bytes):
        file_obj = io.BytesIO(content)
        mock = MagicMock()
        mock.filename = filename
        pos = [0]

        async def read(size=-1):
            if size == -1:
                data = content[pos[0]:]
            else:
                data = content[pos[0]:pos[0] + size]
            pos[0] += len(data)
            return data

        async def seek(offset):
            pos[0] = offset

        mock.read = read
        mock.seek = seek
        return mock

    @pytest.mark.asyncio
    async def test_valid_mp4_file(self):
        upload = self._make_upload("podcast.mp4", b"fake video data" * 10)
        safe_name, size = await validate_upload_file(upload)
        assert safe_name.endswith(".mp4")
        assert size > 0

    @pytest.mark.asyncio
    async def test_missing_filename_raises(self):
        upload = self._make_upload("", b"data")
        upload.filename = None
        with pytest.raises(HTTPException) as exc:
            await validate_upload_file(upload)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_extension_raises(self):
        upload = self._make_upload("virus.exe", b"data")
        with pytest.raises(HTTPException) as exc:
            await validate_upload_file(upload)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_too_large_file_raises(self):
        from app.config import settings
        big_content = b"x" * (settings.max_file_size_mb * 1024 * 1024 + 1)
        upload = self._make_upload("big.mp4", big_content)
        with pytest.raises(HTTPException) as exc:
            await validate_upload_file(upload)
        assert exc.value.status_code == 413
