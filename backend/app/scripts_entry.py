"""CLI entrypoint: `python -m app.scripts_entry seed [--if-empty]`."""
from __future__ import annotations

import argparse
import asyncio

from app.core.config import get_settings
from app.db.seed import is_seeded, seed
from app.db.session import AsyncSessionLocal


async def _run_seed(if_empty: bool) -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        if if_empty and await is_seeded(session):
            print("Database already has data — skipping seed (use `seed` without --if-empty to force).")
            return
        await seed(session, settings)
        print("Seed data inserted.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.scripts_entry")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Insert demo/mock data")
    seed_parser.add_argument("--if-empty", action="store_true", help="Only seed if the database has no students yet")

    args = parser.parse_args()
    if args.command == "seed":
        asyncio.run(_run_seed(args.if_empty))


if __name__ == "__main__":
    main()
