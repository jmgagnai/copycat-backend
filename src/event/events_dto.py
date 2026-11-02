import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AppEvent(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=False, populate_by_name=True)
    id: uuid.UUID
    type: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    occurred_at: datetime.datetime = Field(alias="occurredAt")
    data: dict[str, Any]


class AppEventDraft(BaseModel):
    type: str
    topic: str
    data: dict[str, Any]


def notebook_topic(notebook_id: uuid.UUID | str) -> str:
    return f"notebook:{notebook_id}"
