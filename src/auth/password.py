import asyncio

import bcrypt


async def hash_password(password: str) -> str:
    return (
        await asyncio.to_thread(
            bcrypt.hashpw, password.encode(), bcrypt.gensalt(rounds=10)
        )
    ).decode()


async def verify_password(password: str, hashed: str) -> bool:
    return await asyncio.to_thread(bcrypt.checkpw, password.encode(), hashed.encode())
