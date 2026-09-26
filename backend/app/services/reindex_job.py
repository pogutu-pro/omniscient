"""Process-wide state for the past-paper reindex job.

The reindex is a background job: it can take minutes for a full library,
and an admin should not have to hold an HTTP request open for it. State
lives in this module rather than in the database because it describes a
single running process, not a fact about the world.

The consequence is deliberate and worth being explicit about: **this is
per-process state, exactly like the in-memory rate limiter.** With one
backend container (the current deployment) that is correct. If the backend
is ever scaled to several replicas, a reindex started on one replica is
invisible to the others and two could run at once. Fix that by moving
this to Redis or a Postgres advisory lock before scaling out — do not
pretend it is safe as-is.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.core.logging import get_logger

logger = get_logger(component="reindex_job")


@dataclass
class ReindexState:
    running: bool = False
    task: asyncio.Task | None = None
    last_report: dict | None = None
    last_error: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def claim(self) -> bool:
        """Reserve the single reindex slot. False if one is already going."""
        if self.running:
            return False
        self.running = True
        return True

    def release(self) -> None:
        self.running = False
        self.task = None


state = ReindexState()


def start_reindex(coro_factory) -> bool:
    """Kick off a reindex, refusing if one is already running.

    `coro_factory` must be a callable returning a coroutine rather than a
    coroutine itself: building the coroutine eagerly would open a
    database session that then sits idle waiting for the event loop to
    schedule it, and if the job were then refused, that session would leak.
    """
    if not state.claim():
        return False

    async def runner() -> None:
        try:
            report = await coro_factory()
            state.last_report = report.as_dict() if hasattr(report, "as_dict") else dict(report)
            state.last_error = None
            logger.info("reindex_finished", **state.last_report)
        except asyncio.CancelledError:
            state.last_error = "Cancelled (the backend restarted mid-run)"
            logger.warning("reindex_cancelled")
            raise
        except Exception as exc:
            state.last_error = str(exc)
            logger.error("reindex_failed", error=str(exc)[:300])
        finally:
            state.release()

    state.task = asyncio.create_task(runner(), name="past-paper-reindex")
    return True
