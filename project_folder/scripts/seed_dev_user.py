"""Dev seed: one `ADMIN` role and two app_user rows for local login testing.

Run with:  python -m scripts.seed_dev_user
"""

import asyncio

from sqlalchemy import select

from app.core.enums import RoleCode
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.app_user import AppUser
from app.models.role import Role

SEED_PASSWORD = "Passw0rd!"


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Role).where(Role.code == RoleCode.ADMIN.value))
        role = result.scalar_one_or_none()
        if role is None:
            role = Role(code=RoleCode.ADMIN.value, name="Administrator")
            session.add(role)
            await session.flush()

        for email, username in (
            ("admin@example.com", "admin"),
            ("user@example.com", "user"),
        ):
            existing = await session.execute(select(AppUser).where(AppUser.email == email))
            if existing.scalar_one_or_none() is not None:
                continue
            session.add(
                AppUser(
                    username=username,
                    email=email,
                    role_id=role.id,
                    is_active=True,
                    password_hash=hash_password(SEED_PASSWORD),
                )
            )

        await session.commit()

    print(f"Seed complete. Login with admin@example.com / user@example.com, password={SEED_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
