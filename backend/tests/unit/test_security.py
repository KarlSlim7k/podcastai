import pytest
from pathlib import Path
from fastapi import HTTPException
from app.utils.security import resolve_safe_path, sanitize_text_input, validate_model_name


class TestResolveSafePath:
    def test_valid_path(self, tmp_path):
        result = resolve_safe_path(tmp_path, "file.txt")
        assert result == (tmp_path / "file.txt").resolve()

    def test_path_traversal_detected(self, tmp_path):
        with pytest.raises(HTTPException) as exc:
            resolve_safe_path(tmp_path, "../../etc/passwd")
        assert exc.value.status_code == 400

    def test_nested_valid_path(self, tmp_path):
        result = resolve_safe_path(tmp_path, "subdir/file.txt")
        assert str(tmp_path) in str(result)


class TestSanitizeTextInput:
    def test_normal_text(self):
        result = sanitize_text_input("Hello world")
        assert result == "Hello world"

    def test_strips_dangerous_chars(self):
        result = sanitize_text_input("<script>alert('xss')</script>")
        assert "<" not in result
        assert ">" not in result

    def test_too_long_raises(self):
        with pytest.raises(HTTPException) as exc:
            sanitize_text_input("x" * 10001, max_length=10000)
        assert exc.value.status_code == 400

    def test_strips_whitespace(self):
        result = sanitize_text_input("  hello  ")
        assert result == "hello"


class TestValidateModelName:
    def test_valid_model(self):
        result = validate_model_name("qwen3:14b")
        assert result == "qwen3:14b"

    def test_valid_model_with_dots(self):
        result = validate_model_name("llama3.2:latest")
        assert result == "llama3.2:latest"

    def test_invalid_model_with_spaces(self):
        with pytest.raises(HTTPException) as exc:
            validate_model_name("my model")
        assert exc.value.status_code == 400

    def test_invalid_model_with_injection(self):
        with pytest.raises(HTTPException) as exc:
            validate_model_name("model; rm -rf /")
        assert exc.value.status_code == 400
