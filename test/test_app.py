from httpx import AsyncClient


async def test_health(client: AsyncClient):
    assert (await client.get("/swagger/json")).status_code == 200
