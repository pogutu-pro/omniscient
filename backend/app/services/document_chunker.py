"""Turning a past-paper file into chunks small enough to embed usefully.

Two steps, deliberately kept pure so both are testable without a database,
a model, or a network:

- `extract_pages` pulls text out of a PDF (or accepts plain text as-is).
- `chunk_pages` slices those pages into overlapping windows.

The overlap is not decoration. A question that straddles a window boundary
is invisible to both halves if you split with no overlap, and that is
exactly the case retrieval is most likely to be asked about.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass


class DocumentExtractionError(RuntimeError):
    """Raised when a document's text could not be read."""


@dataclass(frozen=True)
class Page:
    number: int  # 1-based, as a reader would cite it
    text: str


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    page_start: int | None
    page_end: int | None


_WHITESPACE_RUN = re.compile(r"[ \t\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")
# A scanned exam paper is often mostly images; if extraction yields almost
# nothing, the file is effectively unreadable and indexing it would
# silently create a paper that can never be retrieved.
_MIN_USABLE_CHARS = 200


def _normalise(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE_RUN.sub(" ", text)
    return _BLANK_LINES.sub("\n\n", text).strip()


def extract_pages(data: bytes, filename: str = "") -> list[Page]:
    """Extract per-page text from PDF bytes, or pass plain text through.

    Synchronous and CPU-bound: callers should run it via
    `asyncio.to_thread` (see `extract_pages_async`).
    """
    if data[:4] == b"%PDF":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise DocumentExtractionError("pypdf is not installed; cannot read PDF past papers") from exc
        try:
            # PdfReader(io.BytesIO(...)) keeps the whole file in memory,
            # which is what we want: it is already in memory, and papers
            # are a few MB.
            import io

            reader = PdfReader(io.BytesIO(data))
            pages = [
                Page(number=i, text=_normalise(page.extract_text() or ""))
                for i, page in enumerate(reader.pages, start=1)
            ]
        except Exception as exc:
            # Almost always one of two things, and the operator needs to
            # be told which: a structurally broken file (truncated upload,
            # a bad scanner export, a file that is only a shell around an
            # image), or something pypdf cannot parse at all. The raw
            # pypdf message ("negative seek value -1") identifies neither.
            raise DocumentExtractionError(
                f"{filename or 'PDF'} is not a readable PDF ({exc}). It is most likely truncated "
                "or corrupt — re-export or re-scan it. If it opens fine in a normal PDF viewer "
                "but fails here, send it to a maintainer: that is a parser gap, not a bad file."
            ) from exc
    else:
        pages = [Page(number=1, text=_normalise(data.decode("utf-8", errors="replace")))]

    pages = [p for p in pages if p.text]
    total = sum(len(p.text) for p in pages)
    if total < _MIN_USABLE_CHARS:
        raise DocumentExtractionError(
            f"{filename or 'Document'} yielded only {total} characters of text. It is probably a "
            "scanned image with no text layer, which cannot be indexed — run OCR on it first."
        )
    return pages


async def extract_pages_async(data: bytes, filename: str = "") -> list[Page]:
    return await asyncio.to_thread(extract_pages, data, filename)


def chunk_pages(
    pages: list[Page],
    *,
    chunk_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[Chunk]:
    """Slice pages into overlapping character windows.

    Windows are aligned to page boundaries where possible: a chunk that
    stops mid-page and restarts on the next one makes the recorded page
    range a lie, and a wrong citation is worse than no citation. So a
    window accumulates whole pages until the next page would overflow it,
    which means a single very long page still gets split by force.
    """
    if chunk_chars <= 0:
        raise ValueError("chunk_chars must be positive")
    overlap_chars = max(0, min(overlap_chars, chunk_chars - 1))

    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_len = 0
    first_page: int | None = None
    last_page: int | None = None

    def flush() -> None:
        nonlocal buffer, buffer_len, first_page, last_page
        text = "\n\n".join(buffer).strip()
        if text:
            chunks.append(Chunk(index=len(chunks), text=text, page_start=first_page, page_end=last_page))
        buffer = []
        buffer_len = 0
        first_page = None
        last_page = None

    for page in pages:
        # A page longer than the whole window has to be cut on its own.
        if len(page.text) > chunk_chars:
            flush()
            for piece in _hard_split(page.text, chunk_chars, overlap_chars):
                chunks.append(Chunk(index=len(chunks), text=piece, page_start=page.number, page_end=page.number))
            continue

        if buffer_len and buffer_len + len(page.text) + 2 > chunk_chars:
            # Carry a tail of the previous window forward so a question
            # spanning the boundary is still retrievable from one chunk.
            tail = buffer[-1][-overlap_chars:] if overlap_chars else ""
            # Capture the page before flushing: flush() clears it, and
            # reading it afterwards would record a start page of None and
            # hand the model a citation with no page at all.
            carried_from = last_page
            flush()
            if tail:
                buffer = [tail]
                buffer_len = len(tail)
                first_page = carried_from
        if not buffer:
            first_page = page.number
        buffer.append(page.text)
        buffer_len += len(page.text) + 2
        last_page = page.number

    flush()
    return chunks


def _hard_split(text: str, size: int, overlap: int) -> list[str]:
    step = size - overlap if overlap < size else size
    return [text[i : i + size] for i in range(0, len(text), step) if text[i : i + size].strip()]
