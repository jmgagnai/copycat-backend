from httpx import AsyncClient

from test.conftest import sign_in


async def test_register_login_and_me(client: AsyncClient) -> None:
    user = await sign_in(client)
    assert user["email"] == "ada@example.com" and "createdAt" in user
    me = await client.get("/auth/me")
    assert me.status_code == 200 and me.json()["id"] == user["id"]


async def test_register_refuses_a_taken_email(client: AsyncClient) -> None:
    await sign_in(client)
    response = await client.post(
        "/auth/register", json={"email": "ada@example.com", "password": "another one"}
    )
    assert response.status_code == 409
    assert response.json() == {"message": "An account with this email already exists."}


async def test_login_refuses_a_wrong_password(client: AsyncClient) -> None:
    await sign_in(client)
    response = await client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "wrong"}
    )
    assert response.status_code == 401


async def test_me_requires_a_session(client: AsyncClient) -> None:
    assert (await client.get("/auth/me")).status_code == 401


async def test_logout_clears_the_session(client: AsyncClient) -> None:
    await sign_in(client)
    assert (await client.get("/auth/me")).status_code == 200
    assert (await client.post("/auth/logout")).status_code == 204
    assert (await client.get("/auth/me")).status_code == 401
