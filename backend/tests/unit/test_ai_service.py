"""Unit tests for AIService and LlamaCppBackend."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestLlamaCppBackend:
    def test_is_available_false_when_dll_missing(self):
        from app.services.ai_service import LlamaCppBackend
        # On CI / test env without compiled llama.dll, must return False (not raise)
        result = LlamaCppBackend.is_available()
        assert isinstance(result, bool)

    def test_list_models_empty_when_no_gguf(self, tmp_path):
        from app.services.ai_service import LlamaCppBackend
        from app import config as cfg
        original = cfg.settings.llamacpp_models_dir
        cfg.settings.llamacpp_models_dir = tmp_path
        try:
            assert LlamaCppBackend.list_models() == []
        finally:
            cfg.settings.llamacpp_models_dir = original

    def test_list_models_finds_gguf_files(self, tmp_path):
        from app.services.ai_service import LlamaCppBackend
        from app import config as cfg
        original = cfg.settings.llamacpp_models_dir
        cfg.settings.llamacpp_models_dir = tmp_path
        (tmp_path / "model-7b.gguf").write_bytes(b"fake")
        (tmp_path / "model-13b.gguf").write_bytes(b"fake")
        (tmp_path / "not_a_model.txt").write_text("txt")
        try:
            models = LlamaCppBackend.list_models()
            assert "model-7b.gguf" in models
            assert "model-13b.gguf" in models
            assert "not_a_model.txt" not in models
        finally:
            cfg.settings.llamacpp_models_dir = original


class TestAIServiceDispatch:
    @pytest.mark.asyncio
    async def test_generate_routes_gguf_to_llamacpp(self):
        from app.services.ai_service import AIService
        svc = AIService()
        with patch.object(svc, '_generate_llamacpp', new_callable=AsyncMock) as mock_lc:
            mock_lc.return_value = "llamacpp response"
            result = await svc.generate("test prompt", "mymodel.gguf")
            mock_lc.assert_called_once_with("test prompt", None)
            assert result == "llamacpp response"
        await svc.close()

    @pytest.mark.asyncio
    async def test_generate_routes_name_to_ollama(self):
        from app.services.ai_service import AIService
        svc = AIService()
        with patch.object(svc, '_generate_ollama', new_callable=AsyncMock) as mock_ol:
            mock_ol.return_value = "ollama response"
            result = await svc.generate("test prompt", "qwen3:8b")
            mock_ol.assert_called_once_with("test prompt", "qwen3:8b", None)
            assert result == "ollama response"
        await svc.close()

    @pytest.mark.asyncio
    async def test_generate_routes_default_to_ollama(self):
        from app.services.ai_service import AIService
        svc = AIService()
        with patch.object(svc, '_generate_ollama', new_callable=AsyncMock) as mock_ol:
            mock_ol.return_value = "ollama response"
            await svc.generate("prompt", "gemma3")
            mock_ol.assert_called_once()
        await svc.close()

    @pytest.mark.asyncio
    async def test_llamacpp_unavailable_raises(self):
        from app.services.ai_service import AIService, LlamaCppBackend
        svc = AIService()
        with patch.object(LlamaCppBackend, 'is_available', return_value=False):
            with pytest.raises(RuntimeError, match="llama-cpp-python not installed"):
                await svc._generate_llamacpp("prompt")
        await svc.close()

    def test_check_llamacpp_reports_correctly(self):
        from app.services.ai_service import AIService, LlamaCppBackend
        svc = AIService()
        with patch.object(LlamaCppBackend, 'is_available', return_value=True), \
             patch.object(LlamaCppBackend, 'list_models', return_value=["a.gguf"]):
            available, models = svc.check_llamacpp()
            assert available is True
            assert models == ["a.gguf"]

    def test_check_llamacpp_unavailable(self):
        from app.services.ai_service import AIService, LlamaCppBackend
        svc = AIService()
        with patch.object(LlamaCppBackend, 'is_available', return_value=False):
            available, models = svc.check_llamacpp()
            assert available is False
            assert models == []

    @pytest.mark.asyncio
    async def test_analyze_transcript_unknown_type_raises(self):
        from app.services.ai_service import AIService
        svc = AIService()
        with pytest.raises(ValueError, match="Unknown analysis type"):
            await svc.analyze_transcript("text", "nonexistent_type", "qwen3:8b")
        await svc.close()

    @pytest.mark.asyncio
    async def test_analyze_transcript_truncates_long_text(self):
        from app.services.ai_service import AIService
        svc = AIService()
        long_text = "word " * 5000  # ~25000 chars
        with patch.object(svc, 'generate', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "result"
            result, elapsed = await svc.analyze_transcript(long_text, "executive_summary", "qwen3:8b")
            # Verify generate was called with truncated prompt
            call_args = mock_gen.call_args[0][0]
            assert "truncated" in call_args
            assert result == "result"
        await svc.close()

    @pytest.mark.asyncio
    async def test_chat_with_context_passes_system_prompt(self):
        from app.services.ai_service import AIService
        svc = AIService()
        with patch.object(svc, 'generate', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "answer"
            result = await svc.chat_with_context("What is this?", "Context text", "qwen3:8b")
            assert result == "answer"
            call_kwargs = mock_gen.call_args
            # system prompt passed as keyword argument
            assert call_kwargs.kwargs.get('system') is not None or (
                len(call_kwargs.args) >= 3 and call_kwargs.args[2] is not None
            )
        await svc.close()
