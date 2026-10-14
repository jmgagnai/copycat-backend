from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SearchNotebookResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    corrected_query: str | None = Field(
        default=...,
        alias="correctedQuery",
        description="The query actually searched, its misspelt words corrected to words the Notebook holds; null when it was searched as typed.",
    )
    words: list[str] = Field(
        default=...,
        description="The words searched for — as corrected, without `or` or excluded words — to mark where a result opens.",
    )
    total: int = Field(
        default=...,
        description="How many matched in all; more than the results when the list was cut.",
    )
    results: list[dict[str, Any]] = Field(default=...)


class SearchChatThreadsResponse(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=False,
        populate_by_name=True,
    )
    corrected_query: str | None = Field(
        default=...,
        alias="correctedQuery",
        description="The query actually searched, its misspelt words corrected to words the Notebook holds; null when it was searched as typed.",
    )
    words: list[str] = Field(
        default=...,
        description="The words searched for — as corrected, without `or` or excluded words — to mark where a result opens.",
    )
    total: int = Field(
        default=...,
        description="How many matched in all; more than the results when the list was cut.",
    )
    results: list[dict[str, Any]] = Field(default=...)
