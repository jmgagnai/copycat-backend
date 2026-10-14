from __future__ import annotations

from fastapi import APIRouter, Response

router = APIRouter(tags=["events"])


@router.get(
    "/events",
    summary="Subscribe to live app events over server-sent events. Generic: every event type (ingestion progress, and later chat streaming) arrives on this one stream.",
)
async def stream_events(
    *,
    topic: str | list[str] | None = None,
    # TODO: add authentication dependency, e.g.: current_user = Depends(get_auth_context)
) -> Response:
    raise NotImplementedError
