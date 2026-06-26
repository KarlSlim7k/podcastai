import math
import re
from typing import List
from app.utils.logger import get_logger

logger = get_logger(__name__)

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


def _tokenize(text: str) -> list[str]:
    return re.findall(r'\w+', text.lower())


def _tf_idf_score(query_tokens: list[str], chunk: str) -> float:
    chunk_tokens = _tokenize(chunk)
    if not chunk_tokens:
        return 0.0

    tf: dict[str, float] = {}
    for token in chunk_tokens:
        tf[token] = tf.get(token, 0) + 1
    for token in tf:
        tf[token] /= len(chunk_tokens)

    score = 0.0
    for qt in query_tokens:
        if qt in tf:
            score += tf[qt]

    return score


class RAGService:
    def chunk_text(self, text: str) -> list[str]:
        words = text.split()
        chunks = []
        step = CHUNK_SIZE - CHUNK_OVERLAP

        for i in range(0, len(words), step):
            chunk_words = words[i : i + CHUNK_SIZE]
            if chunk_words:
                chunks.append(" ".join(chunk_words))

        return chunks

    def chunk_segments(self, segments: list[dict]) -> list[dict]:
        chunks = []
        current_text = []
        current_start = None
        current_end = None
        current_words = 0

        for seg in segments:
            words = seg["text"].split()
            if current_start is None:
                current_start = seg["start"]

            current_text.append(seg["text"])
            current_end = seg["end"]
            current_words += len(words)

            if current_words >= CHUNK_SIZE // 5:
                chunks.append({
                    "text": " ".join(current_text),
                    "start": current_start,
                    "end": current_end,
                })
                overlap_segs = current_text[-2:] if len(current_text) > 2 else []
                current_text = overlap_segs
                current_start = current_end
                current_words = sum(len(t.split()) for t in current_text)

        if current_text:
            chunks.append({
                "text": " ".join(current_text),
                "start": current_start,
                "end": current_end,
            })

        return chunks

    def retrieve(
        self,
        query: str,
        transcript_text: str,
        segments: list[dict] | None = None,
        top_k: int = 5,
    ) -> tuple[str, list[dict]]:
        query_tokens = _tokenize(query)

        if segments:
            chunks = self.chunk_segments(segments)
            scored = []
            for chunk in chunks:
                score = _tf_idf_score(query_tokens, chunk["text"])
                scored.append((score, chunk))
        else:
            text_chunks = self.chunk_text(transcript_text)
            scored = []
            for chunk in text_chunks:
                score = _tf_idf_score(query_tokens, chunk)
                scored.append((score, {"text": chunk, "start": None, "end": None}))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        context_parts = []
        for score, chunk in top:
            if score > 0:
                if chunk.get("start") is not None:
                    start = int(chunk["start"] // 60)
                    end = int(chunk["end"] // 60)
                    context_parts.append(f"[{start}:{int(chunk['start']%60):02d} - {end}:{int(chunk['end']%60):02d}]\n{chunk['text']}")
                else:
                    context_parts.append(chunk["text"])

        if not context_parts:
            context_text = transcript_text[:3000]
        else:
            context_text = "\n\n---\n\n".join(context_parts)

        return context_text, [c for _, c in top]


rag_service = RAGService()
