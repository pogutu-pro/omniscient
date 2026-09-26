"""CLI entrypoint:

    python -m app.scripts_entry seed [--if-empty]
    python -m app.scripts_entry promote-admin <email>
    python -m app.scripts_entry reindex-past-papers [--force] [--concurrency N] [--paper-id ID ...]
    python -m app.scripts_entry import-timetable <file.xlsx> [options]
    python -m app.scripts_entry ingest-knowledge <file.pdf> [--force] [--dry-run] [--query "..."]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

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


async def _reindex_past_papers(force: bool, concurrency: int, paper_ids: list[str] | None) -> int:
    """Build or refresh the past-paper vector index. Returns an exit code.

    This is the path CI/CD and cron use: it needs no HTTP request and no
    admin session, so it can be run from the deploy job right after a
    migration and from a scheduled timer afterwards.
    """
    settings = get_settings()
    if not settings.embedding_enabled:
        print("EMBEDDING_ENABLED is false; nothing to do.", file=sys.stderr)
        return 2

    from app.services.embedding_service import EmbeddingService
    from app.services.paper_index_service import PaperIndexService
    from app.services.storage.factory import get_storage_backend

    storage = get_storage_backend(settings)
    embeddings = EmbeddingService(settings)
    async with AsyncSessionLocal() as session:
        service = PaperIndexService(session, storage, embeddings, settings)
        report = await service.reindex_all(force=force, paper_ids=paper_ids, concurrency=concurrency)

    for failure in report.failures:
        print(f"  FAILED {failure.file_name}: {failure.error}", file=sys.stderr)
    print(
        f"Indexed {report.papers_processed} paper(s), "
        f"{report.chunks_written} chunk(s); {len(report.failures)} failure(s)."
    )
    # A partial failure is worth a non-zero exit so CI notices, but it is
    # not worth discarding the papers that did succeed.
    return 1 if report.failures else 0


async def _import_timetable(
    path: str,
    programme_code: str,
    academic_year: str | None,
    overwrite: bool,
    prune: bool,
    dry_run: bool,
) -> int:
    """Ingest a departmental teaching timetable workbook. Returns an exit code.

    The workbook is a draft the department keeps revising, so the report is
    printed in full: the counts say what changed, and the warnings name the
    cells a human still has to check. A dry run parses and reports without
    touching the database, which is how a new draft should be inspected
    first.
    """
    from app.services.timetable_import import (
        TimetableImportError,
        import_timetable,
        parse_timetable_workbook,
    )

    try:
        parsed = parse_timetable_workbook(path, academic_year)
    except (TimetableImportError, FileNotFoundError) as exc:
        print(f"Could not read {path}: {exc}", file=sys.stderr)
        return 2

    print(f"{path}")
    trimester = f" - Semester {parsed.official_trimester}" if parsed.official_trimester else ""
    print(f"  term: {parsed.term_label} ({parsed.academic_year}{trimester})")
    print(f"  parsed {len(parsed.courses)} course(s) and {len(parsed.sessions)} session(s)")

    if dry_run:
        for warning in parsed.warnings:
            print(f"  ! {warning}", file=sys.stderr)
        print("  Dry run: nothing was written.")
        return 0

    async with AsyncSessionLocal() as session:
        try:
            report = await import_timetable(
                session,
                parsed,
                programme_code,
                overwrite_course_detail=overwrite,
                prune=prune,
            )
        except TimetableImportError as exc:
            print(f"Import failed: {exc}", file=sys.stderr)
            return 2

    print(f"  {report.summary()}")
    for warning in report.warnings:
        print(f"  ! {warning}", file=sys.stderr)
    return 0


async def _ingest_knowledge(path: str, force: bool, dry_run: bool, query: str | None) -> int:
    """Load the OMNISCIENT dataset into the knowledge tables.

    Safe to run on every deploy: the source hash short-circuits an unchanged
    file, so a deploy that re-runs migrations does not re-parse 119 pages for
    nothing. `--query` runs a real search against the loaded corpus and
    prints what the assistant would be given, which is the only honest way to
    check an ingest: row counts prove the write, a search proves the answer.
    """
    from app.repositories.knowledge_repository import SqlKnowledgeRepository
    from app.services.knowledge_ingest import KnowledgeIngestError, ingest_knowledge_pdf
    from app.services.knowledge_search import format_for_llm, search_knowledge

    pdf_path = Path(path)
    if not pdf_path.is_file():
        print(f"No such file: {pdf_path}", file=sys.stderr)
        return 2

    async with AsyncSessionLocal() as session:
        repository = SqlKnowledgeRepository(session)
        try:
            report = await ingest_knowledge_pdf(repository, pdf_path, force=force)
        except KnowledgeIngestError as exc:
            print(f"Ingest failed: {exc}", file=sys.stderr)
            return 2
        for warning in report.warnings:
            print(f"  ! {warning}", file=sys.stderr)

        if dry_run:
            await session.rollback()
            print(
                f"[dry run] would {report.summary()} — no changes committed."
                if report.changed
                else report.summary()
            )
            return 0

        await session.commit()
        print(report.summary())

        if query:
            answer = await search_knowledge(repository, query)
            print()
            print(f"Query: {query}")
            print(format_for_llm(answer))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.scripts_entry")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Insert demo/mock data")
    seed_parser.add_argument("--if-empty", action="store_true", help="Only seed if the database has no students yet")

    promote_parser = subparsers.add_parser("promote-admin", help="Grant an existing student admin access")
    promote_parser.add_argument("email", help="Email of the student to promote")

    reindex_parser = subparsers.add_parser(
        "reindex-past-papers", help="Build or refresh the past-paper vector index (RAG)"
    )
    reindex_parser.add_argument(
        "--force", action="store_true", help="Re-embed papers that already have chunks instead of skipping them"
    )
    reindex_parser.add_argument(
        "--concurrency", type=int, default=1, help="Papers to process at once (default 1; higher is not faster)"
    )
    reindex_parser.add_argument(
        "--paper-id", action="append", dest="paper_ids", help="Limit to this paper id (repeatable)"
    )

    timetable_parser = subparsers.add_parser(
        "import-timetable", help="Ingest a departmental teaching timetable workbook (.xlsx)"
    )
    timetable_parser.add_argument("path", help="Path to the timetable workbook")
    timetable_parser.add_argument(
        "--programme", default="BCS", help="Programme code to file the courses under (default: BCS)"
    )
    timetable_parser.add_argument(
        "--academic-year",
        default=None,
        help='Override the term read from the sheet, e.g. "2026/2027"',
    )
    timetable_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing course names, lecturers, hours and class sizes instead of only filling in blanks",
    )
    timetable_parser.add_argument(
        "--prune",
        action="store_true",
        help="Delete this term's sessions for the imported year groups that the sheet no longer lists",
    )
    timetable_parser.add_argument(
        "--dry-run", action="store_true", help="Parse and report without writing anything"
    )

    knowledge_parser = subparsers.add_parser(
        "ingest-knowledge", help="Load the OMNISCIENT dataset PDF into the knowledge tables"
    )
    knowledge_parser.add_argument("path", help="Path to the dataset PDF")
    knowledge_parser.add_argument(
        "--force", action="store_true", help="Re-ingest even if the source hash is unchanged"
    )
    knowledge_parser.add_argument(
        "--dry-run", action="store_true", help="Parse and report without committing"
    )
    knowledge_parser.add_argument(
        "--query",
        default=None,
        help='After ingesting, search the corpus and print the context the assistant would receive, e.g. --query "deans email"',
    )

    args = parser.parse_args()
    if args.command == "seed":
        asyncio.run(_run_seed(args.if_empty))
    elif args.command == "promote-admin":
        asyncio.run(_promote_admin(args.email))
    elif args.command == "reindex-past-papers":
        raise SystemExit(
            asyncio.run(_reindex_past_papers(args.force, args.concurrency, args.paper_ids))
        )
    elif args.command == "import-timetable":
        raise SystemExit(
            asyncio.run(
                _import_timetable(
                    args.path,
                    args.programme,
                    args.academic_year,
                    args.overwrite,
                    args.prune,
                    args.dry_run,
                )
            )
        )
    elif args.command == "ingest-knowledge":
        raise SystemExit(
            asyncio.run(_ingest_knowledge(args.path, args.force, args.dry_run, args.query))
        )


if __name__ == "__main__":
    main()
