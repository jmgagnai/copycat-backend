import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from test.conftest import create_notebook, sign_in


async def upload(
    client: AsyncClient,
    notebook_id: str,
    filename: str = "notes.txt",
    content: bytes = b"hello world",
) -> dict[str, Any]:
    response = await client.post(
        f"/notebooks/{notebook_id}/documents",
        files={"file": (filename, content, "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_list_shows_live_documents_oldest_first(client: AsyncClient) -> None:
    await sign_in(client)
    notebook = await create_notebook(client)
    a = await upload(client, notebook["id"], "a.txt")
    b = await upload(client, notebook["id"], "b.txt")

    items = (await client.get(f"/notebooks/{notebook['id']}/documents")).json()
    assert [i["id"] for i in items] == [a["id"], b["id"]]
    for item in items:
        assert (
            item["status"] == "queued"
            and item["failure"] is None
            and item["abstract"] is None
        )
        assert item["latestVersion"]["versionNumber"] == 1
    assert (await client.get(f"/notebooks/{uuid.uuid4()}/documents")).status_code == 404


async def test_reuploading_a_filename_adds_a_version(client: AsyncClient) -> None:
    await sign_in(client)
    notebook = await create_notebook(client)
    first = await upload(client, notebook["id"], content=b"v1")
    second = await upload(client, notebook["id"], content=b"v2")
    assert second["id"] == first["id"]
    assert (
        first["latestVersion"]["versionNumber"] == 1
        and second["latestVersion"]["versionNumber"] == 2
    )
    assert len((await client.get(f"/notebooks/{notebook['id']}/documents")).json()) == 1


async def test_upload_lists_reads_and_downloads_a_document(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client)
    notebook = await create_notebook(client)
    document = await upload(client, notebook["id"])
    assert (
        document["status"] == "queued"
        and document["latestVersion"]["versionNumber"] == 1
    )
    assert document["failure"] is None and document["abstract"] is None
    assert app.state.jobs.enqueued == [
        (uuid.UUID(document["id"]), uuid.UUID(document["latestVersion"]["id"]))
    ]

    base = f"/notebooks/{notebook['id']}/documents/{document['id']}"
    version_id = document["latestVersion"]["id"]

    detail = await client.get(base)
    assert detail.status_code == 200
    assert (
        detail.json()["executiveSummary"] is None
        and detail.json()["chatSnippet"] is None
        and detail.json()["metadata"] is None
    )

    version = await client.get(f"{base}/versions/{version_id}")
    assert version.status_code == 200
    assert (
        version.json()["isLatestVersion"] is True
        and version.json()["latestVersionNumber"] == 1
    )
    assert (
        version.json()["version"]["id"] == version_id
        and version.json()["documentId"] == document["id"]
    )

    content = await client.get(f"{base}/versions/{version_id}/content")
    assert content.json() == {"versionId": version_id, "markdown": None}

    download = await client.get(f"{base}/versions/{version_id}/download")
    assert download.status_code == 200 and download.content == b"hello world"
    assert download.headers["content-type"].startswith("text/plain")
    assert download.headers["content-disposition"] == 'attachment; filename="notes.txt"'

    newer = await upload(client, notebook["id"], content=b"v2")
    version = await client.get(f"{base}/versions/{version_id}")
    assert (
        version.json()["isLatestVersion"] is False
        and version.json()["latestVersionNumber"] == 2
    )
    assert (await client.get(f"{base}/versions/{uuid.uuid4()}")).status_code == 404

    assert (await client.delete(base)).status_code == 204
    assert (await client.get(base)).status_code == 404
    for suffix in ("", "/content", "/download"):
        assert (
            await client.get(f"{base}/versions/{version_id}{suffix}")
        ).status_code == 200

    await db.execute(
        text("UPDATE notebooks SET deleted_at = now() WHERE id = :id"),
        {"id": notebook["id"]},
    )
    for suffix in ("", "/content", "/download"):
        assert (
            await client.get(f"{base}/versions/{version_id}{suffix}")
        ).status_code == 404
    assert (
        await client.get(f"{base}/versions/{newer['latestVersion']['id']}")
    ).status_code == 404


async def test_delete_and_restore_a_document(client: AsyncClient) -> None:
    await sign_in(client)
    notebook = await create_notebook(client)
    document = await upload(client, notebook["id"], "a.txt")
    base = f"/notebooks/{notebook['id']}/documents/{document['id']}"

    assert (await client.delete(base)).status_code == 204
    assert (await client.get(base)).status_code == 404
    assert (await client.delete(base)).status_code == 404
    assert document["id"] not in [
        d["id"]
        for d in (await client.get(f"/notebooks/{notebook['id']}/documents")).json()
    ]

    restored = await client.post(f"{base}/restore")
    assert restored.status_code == 200
    assert (
        restored.json()["id"] == document["id"]
        and restored.json()["latestVersion"]["versionNumber"] == 1
    )
    assert (await client.get(base)).status_code == 200

    assert (await client.delete(base)).status_code == 204
    replacement = await upload(client, notebook["id"], "a.txt")
    assert replacement["id"] != document["id"]
    conflict = await client.post(f"{base}/restore")
    assert conflict.status_code == 409
    assert '"a.txt"' in conflict.json()["message"]
    assert [
        d["id"]
        for d in (await client.get(f"/notebooks/{notebook['id']}/documents")).json()
    ] == [replacement["id"]]

    assert (
        await client.post(
            f"/notebooks/{notebook['id']}/documents/{uuid.uuid4()}/restore"
        )
    ).status_code == 404


async def test_upload_refuses_unsupported_types_and_unknown_notebooks(
    client: AsyncClient,
) -> None:
    await sign_in(client)
    notebook = await create_notebook(client)

    response = await client.post(
        f"/notebooks/{notebook['id']}/documents",
        files={"file": ("book.xls", b"x", "application/octet-stream")},
    )
    assert response.status_code == 400 and "Legacy Excel" in response.json()["message"]
    assert (await client.get(f"/notebooks/{notebook['id']}/documents")).json() == []

    response = await client.post(
        f"/notebooks/{uuid.uuid4()}/documents",
        files={"file": ("a.txt", b"x", "text/plain")},
    )
    assert response.status_code == 404 and response.json() == {
        "message": "Notebook not found."
    }

    assert (await client.post("/auth/logout")).status_code == 204
    assert (
        await client.get(f"/notebooks/{notebook['id']}/documents")
    ).status_code == 401
