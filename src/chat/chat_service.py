import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from llm.embeddings import Embedder
from llm.openrouter import ChatCompletionRequest, ChatStreamer

from .chat_dto import ChatMessageResponse
from .citations import (
    CITATION_INSTRUCTIONS,
    ResolvedCitation,
    locate_citations,
    resolve_citation_markers,
)
from .retrieval import DEFAULT_RETRIEVAL_LIMIT, RetrievedChunk, retrieve_chunks
from .streaming import AnswerChunker


@dataclass
class ChatDeps:
    stream: ChatStreamer
    embed: Embedder
    model: str
    retrieval_limit: int = DEFAULT_RETRIEVAL_LIMIT


@dataclass
class GroundedAnswer:
    text: str
    citations: list[ResolvedCitation]


NO_SOURCES_ANSWER = (
    "I have no sources to answer from yet. This Notebook has no Documents that have "
    'finished ingesting — upload one, or wait for an upload to reach the "ready" status, '
    "and ask again."
)

CHAT_SYSTEM_PROMPT = (
    "You answer questions about a specific set of documents a team has collected.\n"
    "\n"
    "Rules:\n"
    "- Answer only from the provided sources. If they do not contain the answer, say so plainly.\n"
    "- Never invent figures, names, dates, or quotations. If a source is ambiguous, say what it does say.\n"
    "- Refer to sources by their filename when it helps the reader check you.\n"
    f"{CITATION_INSTRUCTIONS}\n"
    "- Write prose in Markdown, organised into short paragraphs with headings when the answer has parts.\n"
    "- Be direct. No preamble about being an AI and no restating of the question."
)

HISTORY_MESSAGE_LIMIT = 10


def format_sources(chunks: list[RetrievedChunk]) -> str:
    markers = {chunk.chunk_id: i + 1 for i, chunk in enumerate(chunks)}
    by_source: dict[uuid.UUID, list[RetrievedChunk]] = {}
    for chunk in chunks:
        by_source.setdefault(chunk.document_version_id, []).append(chunk)
    sources: list[str] = []
    for source_chunks in by_source.values():
        first = source_chunks[0]
        parts = [f"### Source: {first.filename}"]
        if first.chat_snippet:
            parts.append(f"About this source: {first.chat_snippet}")
        for chunk in source_chunks:
            location = (
                f" (under {' > '.join(chunk.heading_path)})"
                if chunk.heading_path
                else ""
            )
            parts.append(f"Chunk [{markers[chunk.chunk_id]}]{location}:\n{chunk.text}")
        sources.append("\n\n".join(parts))
    return "\n\n".join(sources)


def format_history(history: list[ChatMessageResponse]) -> str:
    return "\n\n".join(
        f"{'Question' if m.role == 'user' else 'Answer'}: {m.content}"
        for m in history[-HISTORY_MESSAGE_LIMIT:]
    )


def build_user_turn(
    chunks: list[RetrievedChunk], history: list[ChatMessageResponse], question: str
) -> str:
    sections = ["## Sources", format_sources(chunks)]
    if rendered := format_history(history):
        sections += ["## The Chat Thread so far", rendered]
    sections += ["## The question to answer now", question]
    return "\n\n".join(sections)


OnChunk = Callable[[str], Awaitable[None]]


async def stream_answer(
    db: AsyncSession,
    deps: ChatDeps,
    notebook_id: uuid.UUID,
    question: str,
    history: list[ChatMessageResponse],
    on_chunk: OnChunk,
) -> GroundedAnswer:
    (query_embedding,) = await deps.embed([question])
    chunks = await retrieve_chunks(
        db, notebook_id, query_embedding, deps.retrieval_limit
    )
    if not chunks:
        await on_chunk(NO_SOURCES_ANSWER)
        return GroundedAnswer(NO_SOURCES_ANSWER, [])

    request = ChatCompletionRequest(
        deps.model,
        CHAT_SYSTEM_PROMPT,
        build_user_turn(chunks, history, question),
        temperature=0.2,
    )

    chunker = AnswerChunker()
    text = ""
    async for delta in deps.stream(request):
        text += delta
        for piece in chunker.push(delta):
            await on_chunk(piece)
    for piece in chunker.flush():
        await on_chunk(piece)
    if not text.strip():
        raise RuntimeError(f"OpenRouter returned no content for model {deps.model}.")
    return GroundedAnswer(
        text, await locate_citations(db, resolve_citation_markers(text, chunks))
    )
