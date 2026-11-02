from dataclasses import dataclass

from settings import settings


@dataclass(frozen=True)
class TaskModels:
    """Which OpenRouter model runs which generation task: server-side configuration only,
    never user-selectable (NBK-1)."""

    metadata: str = "qwen/qwen3-30b-a3b-instruct-2507"
    section_summary: str = "mistralai/mistral-small-3.2-24b-instruct"
    chat_snippet: str = "qwen/qwen3-30b-a3b-instruct-2507"
    executive_summary: str = "qwen/qwen3-235b-a22b-2507"
    abstract: str = "qwen/qwen3-30b-a3b-instruct-2507"
    chat_answer: str = "qwen/qwen3-235b-a22b-2507"


def resolve_task_models() -> TaskModels:
    """The defaults, each overridden by its OPENROUTER_MODEL_* setting when that is non-empty."""
    d = TaskModels()
    return TaskModels(
        metadata=settings.OPENROUTER_MODEL_METADATA or d.metadata,
        section_summary=settings.OPENROUTER_MODEL_SECTION_SUMMARY or d.section_summary,
        chat_snippet=settings.OPENROUTER_MODEL_CHAT_SNIPPET or d.chat_snippet,
        executive_summary=settings.OPENROUTER_MODEL_EXECUTIVE_SUMMARY
        or d.executive_summary,
        abstract=settings.OPENROUTER_MODEL_ABSTRACT or d.abstract,
        chat_answer=settings.OPENROUTER_MODEL_CHAT_ANSWER or d.chat_answer,
    )


DEFAULT_EMBEDDING_MODEL = "qwen/qwen3-embedding-4b"
EMBEDDING_DIMENSIONS = 2560


def resolve_embedding_model() -> str:
    return settings.OPENROUTER_MODEL_EMBEDDING or DEFAULT_EMBEDDING_MODEL
