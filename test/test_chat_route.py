import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from chat.chat_service import NO_SOURCES_ANSWER, ChatDeps
from llm.openrouter import ChatCompletionRequest
from settings import settings
from test.conftest import create_notebook, sign_in
from test.test_chat_retrieval import unit_vector


async def create_thread(
    client: AsyncClient, notebook_id: str, title: str = "Questions"
) -> dict[str, Any]:
    response = await client.post(
        f"/notebooks/{notebook_id}/threads", json={"title": title}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_thread_crud_with_author_only_deletion(client: AsyncClient) -> None:
    ada = await sign_in(client)
    notebook = await create_notebook(client)
    threads_url = f"/notebooks/{notebook['id']}/threads"

    thread = await create_thread(client, notebook["id"])
    assert thread["author"] == {"id": ada["id"], "email": "ada@example.com"}
    assert thread["notebookId"] == notebook["id"] and thread["title"] == "Questions"
    assert [t["id"] for t in (await client.get(threads_url)).json()] == [thread["id"]]

    renamed = await client.patch(
        f"{threads_url}/{thread['id']}", json={"title": "Renamed"}
    )
    assert renamed.status_code == 200 and renamed.json()["title"] == "Renamed"
    assert (await client.get(f"{threads_url}/{thread['id']}/messages")).json() == []

    await sign_in(client, "grace@example.com")
    assert (await client.delete(f"{threads_url}/{thread['id']}")).status_code == 403
    assert (
        await client.post(f"{threads_url}/{thread['id']}/restore")
    ).status_code == 403

    await client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "correct horse"}
    )
    assert (await client.delete(f"{threads_url}/{thread['id']}")).status_code == 204
    assert (await client.get(threads_url)).json() == []
    assert (await client.delete(f"{threads_url}/{thread['id']}")).status_code == 404
    assert (
        await client.get(f"{threads_url}/{thread['id']}/messages")
    ).status_code == 404


async def test_unknown_notebook_and_thread_answer_404(client: AsyncClient) -> None:
    await sign_in(client)
    notebook = await create_notebook(client)
    unknown = uuid.uuid4()

    assert (await client.get(f"/notebooks/{unknown}/threads")).status_code == 404
    assert (
        await client.post(f"/notebooks/{unknown}/threads", json={"title": "T"})
    ).status_code == 404
    response = await client.get(
        f"/notebooks/{notebook['id']}/threads/{unknown}/messages"
    )
    assert response.status_code == 404
    assert response.json() == {"message": "Chat Thread not found."}
    assert (
        await client.patch(
            f"/notebooks/{notebook['id']}/threads/{unknown}", json={"title": "T"}
        )
    ).status_code == 404


async def test_an_administrator_restores_a_deleted_thread(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "Grace@example.com")
    await sign_in(client)
    notebook = await create_notebook(client)
    thread = await create_thread(client, notebook["id"])
    thread_url = f"/notebooks/{notebook['id']}/threads/{thread['id']}"
    assert (await client.delete(thread_url)).status_code == 204

    assert (await client.post(f"{thread_url}/restore")).status_code == 403

    await sign_in(client, "grace@example.com")
    restored = await client.post(f"{thread_url}/restore")
    assert restored.status_code == 200 and restored.json()["id"] == thread["id"]
    assert [
        t["id"]
        for t in (await client.get(f"/notebooks/{notebook['id']}/threads")).json()
    ] == [thread["id"]]
    assert (await client.post(f"{thread_url}/restore")).status_code == 404


async def fake_embed(texts: list[str]) -> list[list[float]]:
    return [unit_vector(0) for _ in texts]


async def fake_stream(request: ChatCompletionRequest) -> AsyncIterator[str]:
    yield "An answer [1]."


def install_chat_deps(client: AsyncClient, deps: ChatDeps | None) -> None:
    transport = client._transport
    assert isinstance(transport, ASGITransport)
    transport.app.state.chat = deps  # type: ignore[attr-defined]


async def test_asking_answers_503_without_openrouter(client: AsyncClient) -> None:
    await sign_in(client)
    notebook = await create_notebook(client)
    thread = await create_thread(client, notebook["id"])
    response = await client.post(
        f"/notebooks/{notebook['id']}/threads/{thread['id']}/messages",
        json={"content": "hi"},
    )
    assert response.status_code == 503
    assert response.json()["message"].startswith("Chat is not configured")


async def test_asking_in_an_unknown_thread_answers_404_first(
    client: AsyncClient,
) -> None:
    await sign_in(client)
    notebook = await create_notebook(client)
    response = await client.post(
        f"/notebooks/{notebook['id']}/threads/{uuid.uuid4()}/messages",
        json={"content": "hi"},
    )
    assert response.status_code == 404


async def test_asking_records_the_exchange(client: AsyncClient) -> None:
    install_chat_deps(client, ChatDeps(stream=fake_stream, embed=fake_embed, model="m"))
    ada = await sign_in(client)
    notebook = await create_notebook(client)
    thread = await create_thread(client, notebook["id"])
    messages_url = f"/notebooks/{notebook['id']}/threads/{thread['id']}/messages"

    response = await client.post(messages_url, json={"content": "What?"})
    assert response.status_code == 201, response.text
    exchange = response.json()
    assert exchange["question"]["content"] == "What?"
    assert exchange["question"]["role"] == "user"
    assert exchange["answer"]["content"] == NO_SOURCES_ANSWER
    assert exchange["answer"]["role"] == "assistant"
    assert exchange["question"]["askedBy"]["id"] == ada["id"]
    assert exchange["answer"]["askedBy"]["id"] == ada["id"]
    assert exchange["answer"]["citations"] == []
    assert exchange["answer"]["threadId"] == thread["id"]

    messages = (await client.get(messages_url)).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert [m["id"] for m in messages] == [
        exchange["question"]["id"],
        exchange["answer"]["id"],
    ]


async def test_a_failed_answer_records_nothing(client: AsyncClient) -> None:
    async def broken_embed(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding service down")

    install_chat_deps(
        client, ChatDeps(stream=fake_stream, embed=broken_embed, model="m")
    )
    await sign_in(client)
    notebook = await create_notebook(client)
    thread = await create_thread(client, notebook["id"])
    messages_url = f"/notebooks/{notebook['id']}/threads/{thread['id']}/messages"

    response = await client.post(messages_url, json={"content": "What?"})
    assert response.status_code == 502
    assert (await client.get(messages_url)).json() == []
