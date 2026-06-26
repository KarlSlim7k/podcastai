import pytest
from app.services.rag_service import RAGService, CHUNK_SIZE, CHUNK_OVERLAP


@pytest.fixture
def rag():
    return RAGService()


class TestChunkText:
    def test_short_text(self, rag):
        text = "Hello world this is a test."
        chunks = rag.chunk_text(text)
        assert len(chunks) >= 1
        assert "Hello" in chunks[0]

    def test_long_text_creates_multiple_chunks(self, rag):
        words = ["word"] * (CHUNK_SIZE * 3)
        text = " ".join(words)
        chunks = rag.chunk_text(text)
        assert len(chunks) > 1

    def test_overlap_exists(self, rag):
        words = [f"word{i}" for i in range(CHUNK_SIZE * 2)]
        text = " ".join(words)
        chunks = rag.chunk_text(text)
        if len(chunks) >= 2:
            last_words_chunk1 = set(chunks[0].split()[-CHUNK_OVERLAP:])
            first_words_chunk2 = set(chunks[1].split()[:CHUNK_OVERLAP])
            assert len(last_words_chunk1 & first_words_chunk2) > 0

    def test_empty_text(self, rag):
        chunks = rag.chunk_text("")
        assert chunks == []


class TestRetrieve:
    def test_retrieves_relevant_chunk(self, rag):
        transcript = (
            "We talked about machine learning for a long time. "
            "Then we discussed cooking recipes. "
            "After that we covered Python programming. "
            "Finally we ended with sports news. "
        ) * 20

        context, chunks = rag.retrieve(
            query="What did they say about machine learning?",
            transcript_text=transcript,
            top_k=3,
        )
        assert "machine learning" in context.lower()

    def test_returns_context_string(self, rag):
        text = "The speaker talked about artificial intelligence and its impact on society."
        context, chunks = rag.retrieve(query="artificial intelligence", transcript_text=text)
        assert isinstance(context, str)
        assert len(context) > 0

    def test_empty_transcript_fallback(self, rag):
        context, chunks = rag.retrieve(query="anything", transcript_text="")
        assert isinstance(context, str)


class TestChunkSegments:
    def test_segments_are_chunked(self, rag):
        segments = [
            {"start": i * 10.0, "end": (i + 1) * 10.0, "text": f"Segment {i} with some content here."}
            for i in range(50)
        ]
        chunks = rag.chunk_segments(segments)
        assert len(chunks) >= 1
        for c in chunks:
            assert "text" in c
            assert "start" in c
            assert "end" in c
