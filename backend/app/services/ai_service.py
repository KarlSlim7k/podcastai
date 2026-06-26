import time
import asyncio
import httpx
from pathlib import Path
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

ANALYSIS_PROMPTS = {
    "executive_summary": """Analyze the following transcript and generate a concise executive summary in the same language as the transcript.
Include: main purpose, key outcomes, most important information.
Format as structured paragraphs. Be professional and clear.

TRANSCRIPT:
{text}

EXECUTIVE SUMMARY:""",

    "main_topics": """Analyze the following transcript and identify the main topics discussed.
List each topic with a brief description of what was covered.
Format as a numbered list. Use the same language as the transcript.

TRANSCRIPT:
{text}

MAIN TOPICS:""",

    "key_ideas": """Extract the key ideas and insights from this transcript.
Focus on the most important concepts, discoveries, or perspectives shared.
Format as bullet points. Use the same language as the transcript.

TRANSCRIPT:
{text}

KEY IDEAS:""",

    "action_items": """Identify all action items, tasks, or next steps mentioned in this transcript.
For each item, note who is responsible (if mentioned) and any deadlines.
Format as a checklist. Use the same language as the transcript.

TRANSCRIPT:
{text}

ACTION ITEMS:""",

    "important_questions": """Extract the most important questions raised or discussed in this transcript.
Include both explicit questions asked and implicit questions that arose from the discussion.
Format as a numbered list. Use the same language as the transcript.

TRANSCRIPT:
{text}

IMPORTANT QUESTIONS:""",

    "chapters": """Divide this transcript into logical chapters or sections.
For each chapter: title, time range (approximate, based on content flow), brief summary.
Use the same language as the transcript.

TRANSCRIPT:
{text}

CHAPTERS:""",

    "timeline": """Create a chronological timeline of events, topics, and key moments from this transcript.
Include approximate timestamps or sequence markers.
Use the same language as the transcript.

TRANSCRIPT:
{text}

TIMELINE:""",

    "learning_points": """Extract the key learning points and educational insights from this transcript.
Focus on what someone would learn from listening/watching this content.
Format as numbered learning objectives. Use the same language as the transcript.

TRANSCRIPT:
{text}

LEARNING POINTS:""",

    "facebook_post": """Create an engaging Facebook post to promote the content of this transcript.
Include: hook, key insights teaser, call to action.
Max 500 characters. Use emojis appropriately. Same language as transcript.

TRANSCRIPT:
{text}

FACEBOOK POST:""",

    "twitter_post": """Create an engaging Twitter/X post thread (3-5 tweets) based on this transcript content.
Each tweet max 280 characters. Include relevant hashtags. Same language as transcript.

TRANSCRIPT:
{text}

TWITTER THREAD:""",

    "linkedin_post": """Create a professional LinkedIn post based on this transcript.
Include: professional hook, key insights, professional value, call to action.
800-1200 characters. Professional tone. Same language as transcript.

TRANSCRIPT:
{text}

LINKEDIN POST:""",

    "blog_article": """Write a complete blog article based on this transcript content.
Include: compelling title, introduction, multiple sections with subheadings, conclusion.
1500-2500 words. Engaging and informative. Same language as transcript.

TRANSCRIPT:
{text}

BLOG ARTICLE:""",

    "youtube_description": """Write an optimized YouTube video description based on this transcript.
Include: hook (first 2 lines visible before "show more"), content overview, timestamps (if applicable),
relevant links section placeholder, hashtags. 500-800 words. Same language as transcript.

TRANSCRIPT:
{text}

YOUTUBE DESCRIPTION:""",

    "suggested_titles": """Generate 10 creative and compelling titles for this content based on the transcript.
Include a mix of: descriptive, curiosity-driven, SEO-optimized, and emotional titles.
Same language as transcript.

TRANSCRIPT:
{text}

SUGGESTED TITLES:""",

    "suggested_tags": """Generate 20-30 relevant tags/keywords for this content based on the transcript.
Include a mix of: broad topics, specific concepts, names mentioned, trending terms.
Format as a comma-separated list. Same language as transcript.

TRANSCRIPT:
{text}

SUGGESTED TAGS:""",

    "faq": """Create a comprehensive FAQ (Frequently Asked Questions) based on this transcript.
Generate 10-15 questions that listeners/viewers would likely ask, with detailed answers.
Same language as transcript.

TRANSCRIPT:
{text}

FAQ:""",

    "conclusions": """Write a comprehensive conclusions section for this transcript content.
Summarize the main takeaways, final thoughts, and overall significance of the discussion.
Include implications and future considerations. Same language as transcript.

TRANSCRIPT:
{text}

CONCLUSIONS:""",

    "viral_moments": """Analyze the following transcript and identify the 5-10 most viral-worthy
moments for short-form video (Reels, TikTok, YouTube Shorts). For each moment:
- Approximate timestamp (start - end) in the transcript
- Why it's interesting (controversial, funny, insightful, emotional, etc.)
- A short punchy title (5-8 words)
- A hook line that would work as the first 3 seconds of the video

Format as a numbered list. Use the same language as the transcript.

TRANSCRIPT:
{text}

VIRAL MOMENTS:""",

    "best_quotes": """Extract the 10 most quotable phrases or sentences from this transcript.
Focus on lines that are:
- Self-contained (make sense without context)
- Memorable, surprising, or emotional
- Shareable on social media

For each quote, give the quote itself and a brief context note.
Format as a numbered list. Use the same language as the transcript.

TRANSCRIPT:
{text}

BEST QUOTES:""",

    "seo_timestamps": """Create a list of 10-15 timestamped chapters/chapters for YouTube.
Each entry: timestamp (MM:SS) + short title (3-6 words).
Use the actual flow of the transcript to identify natural topic shifts.
Same language as transcript.

TRANSCRIPT:
{text}

TIMESTAMPS:""",
}


class LlamaCppBackend:
    """Optional llama-cpp-python backend — used when Ollama is unavailable."""

    _model_cache: dict = {}

    @staticmethod
    def is_available() -> bool:
        try:
            import llama_cpp  # noqa: F401
            return True
        except (ImportError, RuntimeError, OSError):
            # RuntimeError/OSError when llama.dll not found (incomplete wheel)
            return False

    @staticmethod
    def list_models() -> list[str]:
        models_dir = settings.llamacpp_models_dir
        if not models_dir.exists():
            return []
        return [f.name for f in sorted(models_dir.glob("*.gguf"))]

    @staticmethod
    def _load_model(model_name: str):  # pragma: no cover
        from llama_cpp import Llama
        cache = LlamaCppBackend._model_cache
        if model_name in cache:
            return cache[model_name]
        model_path = settings.llamacpp_models_dir / model_name
        if not model_path.exists():
            raise RuntimeError(f"GGUF model not found: {model_path}")
        logger.info("llamacpp_loading_model", model=model_name)
        llm = Llama(
            model_path=str(model_path),
            n_gpu_layers=settings.llamacpp_n_gpu_layers,
            n_ctx=settings.llamacpp_n_ctx,
            verbose=False,
        )
        # Only keep 1 model in cache to avoid OOM
        cache.clear()
        cache[model_name] = llm
        return llm

    @classmethod
    def generate_sync(cls, prompt: str, system: str | None = None) -> str:  # pragma: no cover
        models = cls.list_models()
        if not models:
            raise RuntimeError("No GGUF models found in data/models/. Download a .gguf file.")
        model_name = models[0]
        llm = cls._load_model(model_name)

        full_prompt = prompt
        if system:
            full_prompt = f"<|system|>\n{system}\n<|user|>\n{prompt}\n<|assistant|>\n"

        output = llm(
            full_prompt,
            max_tokens=settings.llamacpp_max_tokens,
            temperature=0.7,
            echo=False,
        )
        return output["choices"][0]["text"].strip()


class AIService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=settings.ollama_timeout)

    async def check_availability(self) -> tuple[bool, list[str]]:
        try:
            resp = await self.client.get(f"{settings.ollama_host}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                return True, models
        except Exception as e:
            logger.warning("ollama_unavailable", error=str(e))
        return False, []

    def check_llamacpp(self) -> tuple[bool, list[str]]:
        available = LlamaCppBackend.is_available()
        models = LlamaCppBackend.list_models() if available else []
        return available, models

    async def list_models(self) -> list[dict]:
        try:
            resp = await self.client.get(f"{settings.ollama_host}/api/tags")
            if resp.status_code == 200:
                return resp.json().get("models", [])
        except Exception:
            pass
        return []

    async def generate(self, prompt: str, model: str, system: str | None = None) -> str:
        # If model name ends with .gguf, route to llama-cpp-python backend
        if model.endswith(".gguf"):
            return await self._generate_llamacpp(prompt, system)
        return await self._generate_ollama(prompt, model, system)

    async def _generate_ollama(self, prompt: str, model: str, system: str | None = None) -> str:
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 4096,
            },
        }
        if system:
            payload["system"] = system

        try:
            resp = await self.client.post(
                f"{settings.ollama_host}/api/generate",
                json=payload,
                timeout=settings.ollama_timeout,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except httpx.TimeoutException:
            raise RuntimeError(f"Ollama timeout after {settings.ollama_timeout}s")
        except Exception as e:
            raise RuntimeError(f"Ollama error: {str(e)}")

    async def _generate_llamacpp(self, prompt: str, system: str | None = None) -> str:
        if not LlamaCppBackend.is_available():
            raise RuntimeError(
                "llama-cpp-python not installed. Run: pip install llama-cpp-python"
            )
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, LlamaCppBackend.generate_sync, prompt, system
        )

    async def analyze_transcript(
        self,
        transcript_text: str,
        analysis_type: str,
        model: str,
    ) -> tuple[str, float]:
        if analysis_type not in ANALYSIS_PROMPTS:
            raise ValueError(f"Unknown analysis type: {analysis_type}")

        # Some analysis types need more context to be useful. We use a larger
        # window for the segment-aware types (viral_moments, seo_timestamps)
        # so the LLM can see enough of the transcript to make good picks.
        big_context_types = {"viral_moments", "seo_timestamps", "chapters", "timeline"}
        max_chars = 24000 if analysis_type in big_context_types else 12000

        text = transcript_text[:max_chars]
        if len(transcript_text) > max_chars:
            text += "\n\n[...transcript truncated for processing...]"

        prompt = ANALYSIS_PROMPTS[analysis_type].format(text=text)

        start = time.time()
        result = await self.generate(prompt, model)
        elapsed = time.time() - start

        logger.info("analysis_completed",
                   analysis_type=analysis_type,
                   model=model,
                   duration=f"{elapsed:.1f}s",
                   chars=len(result))

        return result, elapsed

    async def chat_with_context(
        self,
        question: str,
        context: str,
        model: str,
        conversation_history: list[dict] | None = None,
    ) -> str:
        system = """You are a helpful assistant that answers questions based ONLY on the provided transcript.
If the answer is not in the transcript, say so clearly.
Be precise and cite relevant parts of the transcript when possible.
Respond in the same language as the question."""

        history_text = ""
        if conversation_history:
            for msg in conversation_history[-6:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                history_text += f"{role}: {msg['content']}\n"

        prompt = f"""TRANSCRIPT CONTEXT:
{context}

{f'PREVIOUS CONVERSATION:{chr(10)}{history_text}{chr(10)}' if history_text else ''}
CURRENT QUESTION: {question}

ANSWER (based only on the transcript above):"""

        return await self.generate(prompt, model, system=system)

    async def close(self):
        await self.client.aclose()


ai_service = AIService()
