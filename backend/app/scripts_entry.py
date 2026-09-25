"""CLI entrypoint:

    python -m app.scripts_entry seed [--if-empty]
    python -m app.scripts_entry promote-admin <email>
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.db.seed import is_seeded, seed
from app.db.session import AsyncSessionLocal
from app.models.student import Student


async def _run_seed(if_empty: bool) -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        if if_empty and await is_seeded(session):
            print("Database already has data — skipping seed (use `seed` without --if-empty to force).")
            return
        await seed(session, settings)
        print("Seed data inserted.")


async def _promote_admin(email: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Student).where(Student.email == email))
        student = result.scalar_one_or_none()
        if not student:
            print(f"No student found with email {email!r}. They must register first.")
            return
        student.is_admin = True
        await session.commit()
        print(f"{email} is now an admin.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.scripts_entry")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Insert demo/mock data")
    seed_parser.add_argument("--if-empty", action="store_true", help="Only seed if the database has no students yet")

    promote_parser = subparsers.add_parser("promote-admin", help="Grant an existing student admin access")
    promote_parser.add_argument("email", help="Email of the student to promote")

    args = parser.parse_args()
    if args.command == "seed":
        asyncio.run(_run_seed(args.if_empty))
    elif args.command == "promote-admin":
        asyncio.run(_promote_admin(args.email))


if __name__ == "__main__":
    main()
