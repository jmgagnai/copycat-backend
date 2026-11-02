async def test_health(client):
    assert (await client.get("/swagger/json")).status_code == 200
