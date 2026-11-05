import uuid

from httpx import AsyncClient

from test.conftest import create_notebook, sign_in


async def _listed_ids(client: AsyncClient) -> list[str]:
    response = await client.get("/notebooks")
    assert response.status_code == 200
    return [n["id"] for n in response.json()]


async def test_notebook_crud_and_restore(client: AsyncClient) -> None:
    await sign_in(client)
    notebook = await create_notebook(client, "Research")
    assert (
        set(notebook) == {"id", "title", "createdAt"}
        and notebook["title"] == "Research"
    )
    assert notebook["id"] in await _listed_ids(client)

    renamed = await client.patch(
        f"/notebooks/{notebook['id']}", json={"title": "Renamed"}
    )
    assert renamed.status_code == 200 and renamed.json()["title"] == "Renamed"

    assert (await client.delete(f"/notebooks/{notebook['id']}")).status_code == 204
    assert notebook["id"] not in await _listed_ids(client)
    second_delete = await client.delete(f"/notebooks/{notebook['id']}")
    assert second_delete.status_code == 404 and second_delete.json() == {
        "message": "Notebook not found."
    }
    assert (
        await client.patch(f"/notebooks/{notebook['id']}", json={"title": "x"})
    ).status_code == 404

    restored = await client.post(f"/notebooks/{notebook['id']}/restore")
    assert restored.status_code == 200 and restored.json()["title"] == "Renamed"
    assert notebook["id"] in await _listed_ids(client)
    assert (
        await client.post(f"/notebooks/{notebook['id']}/restore")
    ).status_code == 404


async def test_notebooks_require_a_session(client: AsyncClient) -> None:
    assert (await client.get("/notebooks")).status_code == 401
    assert (await client.post("/notebooks", json={"title": "x"})).status_code == 401
    assert (
        await client.patch(f"/notebooks/{uuid.uuid4()}", json={"title": "x"})
    ).status_code == 401
