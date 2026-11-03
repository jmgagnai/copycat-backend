"""T17 step 3: the two stubbed search routes, through the ASGI client on T05's rolled-back
session. Search itself was dropped, so both answer the empty result."""

import uuid
from typing import Any

from httpx import AsyncClient

from test.conftest import create_notebook, sign_in

EMPTY_SEARCH: dict[str, Any] = {
    "correctedQuery": None,
    "words": [],
    "total": 0,
    "results": [],
}


async def test_search_answers_the_empty_result(client: AsyncClient) -> None:
    await sign_in(client)
    notebook = await create_notebook(client)

    response = await client.get(f"/notebooks/{notebook['id']}/search?q=x")
    assert response.status_code == 200
    assert response.json() == EMPTY_SEARCH
    assert response.json()["total"] == 0

    # The same shape with `exact`, and for Chat Threads.
    response = await client.get(f"/notebooks/{notebook['id']}/search?q=x&exact=true")
    assert response.status_code == 200 and response.json() == EMPTY_SEARCH
    response = await client.get(f"/notebooks/{notebook['id']}/search/threads?q=x")
    assert response.status_code == 200 and response.json() == EMPTY_SEARCH


async def test_search_in_an_unknown_notebook_answers_404(client: AsyncClient) -> None:
    await sign_in(client)
    unknown = uuid.uuid4()

    for path in ("search", "search/threads"):
        response = await client.get(f"/notebooks/{unknown}/{path}?q=x")
        assert response.status_code == 404, path
        assert response.json() == {"message": "Notebook not found."}


async def test_search_requires_a_session(client: AsyncClient) -> None:
    await sign_in(client)
    notebook = await create_notebook(client)
    anonymous = AsyncClient(transport=client._transport, base_url="http://test")
    response = await anonymous.get(f"/notebooks/{notebook['id']}/search?q=x")
    assert response.status_code == 401
