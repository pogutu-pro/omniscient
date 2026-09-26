"""Shrink uploaded PDFs before they are stored in R2.

A past paper is uploaded once and downloaded many times, so the bytes
saved here are saved on every download — which matters on Cloudflare R2,
where storage is cheap but bouncing a 40 MB scan to every student is not.

Two rules keep this safe rather than merely smaller:

- It only ever replaces the original when the result is a *meaningful*
  amount smaller. Ghostscript occasionally produces a larger file for an
  already-optimised PDF, and a "compression" step that grows a file is
  worse than no step at all.
- It refuses a result that has lost the text layer. Retrieval indexes
  papers by extracting their text, so a scan compressed down to
  unsearchable pixels would silently poison the RAG index. If the
  original had extractable text and the compressed copy has lost most of
  it, the original is kept.

Everything degrades to a no-op: no ghostscript, an unreadable PDF, a
timeout, or any unexpected failure returns the input unchanged. Upload
never fails because compression did.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(component="pdf_compression")

# Resolved once at import. `None` means the runtime has no ghostscript and
# every call is a passthrough, which is how the test environment behaves.
_GHOSTSCRIPT = shutil.which("gs")

# Below this, the download is already cheap and the CPU is not worth it.
_MIN_BYTES = 150 * 1024

# Only replace the original if it shrank by at least this fraction.
_MIN_SAVING = 0.15

# Keep the compressed copy only if it retains at least this fraction of the
# original's extracted text.
_TEXT_FLOOR = 0.6

_TIMEOUT_SECONDS = 120


def _looks_like_pdf(content: bytes) -> bool:
    return content[:5] == b"%PDF-"


def _read_stats(content: bytes) -> tuple[int, int] | None:
    """(page count, extracted text length), or None if the PDF is unreadable.

    None means "cannot be verified". A PDF we cannot parse is never
    replaced: ghostscript will happily turn an unreadable file into a tiny
    valid-but-empty one, and accepting that would destroy the paper. Zero
    text on a *readable* PDF is fine — that is just a scanned paper with no
    text layer, which is exactly what we want to shrink.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        pages = len(reader.pages)
        if pages == 0:
            return None
        text = sum(len(page.extract_text() or "") for page in reader.pages)
        return pages, text
    except Exception:  # noqa: BLE001 - any pypdf failure means "unknown"
        return None


def _run_ghostscript(content: bytes) -> bytes | None:
    if _GHOSTSCRIPT is None:
        return None

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "in.pdf"
        output = Path(tmp) / "out.pdf"
        source.write_bytes(content)
        command = [
            _GHOSTSCRIPT,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.5",
            # /ebook ≈ 150 dpi: the sweet spot for a scanned paper — legible
            # on screen, a fraction of the size, text layer preserved.
            "-dPDFSETTINGS=/ebook",
            "-dDetectDuplicateImages=true",
            "-dCompressFonts=true",
            "-dSubsetFonts=true",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={output}",
            str(source),
        ]
        try:
            result = subprocess.run(command, capture_output=True, timeout=_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("pdf_compression_failed", error=str(exc))
            return None
        if result.returncode != 0 or not output.is_file():
            logger.warning(
                "pdf_compression_ghostscript_error",
                returncode=result.returncode,
                stderr=(result.stderr or b"")[-200:].decode(errors="replace"),
            )
            return None
        return output.read_bytes()


def compress_pdf(content: bytes) -> bytes:
    """Return a smaller PDF, or the original when shrinking is not a win."""
    if not content or not _looks_like_pdf(content) or len(content) < _MIN_BYTES:
        return content

    original_stats = _read_stats(content)
    if original_stats is None:
        # Unreadable input: ghostscript might emit a tiny empty PDF and we
        # would have no way to tell it was wrong. Leave it alone.
        return content
    original_pages, original_text = original_stats

    compressed = _run_ghostscript(content)
    if compressed is None or len(compressed) >= len(content) * (1 - _MIN_SAVING):
        return content

    compressed_stats = _read_stats(compressed)
    if compressed_stats is None:
        return content
    compressed_pages, compressed_text = compressed_stats

    if compressed_pages != original_pages:
        logger.warning(
            "pdf_compression_rejected",
            reason="page_count_changed",
            original_pages=original_pages,
            compressed_pages=compressed_pages,
        )
        return content

    if original_text > 0 and compressed_text < original_text * _TEXT_FLOOR:
        logger.warning(
            "pdf_compression_rejected",
            reason="text_layer_degraded",
            original_bytes=len(content),
            compressed_bytes=len(compressed),
        )
        return content

    logger.info(
        "pdf_compressed",
        original_bytes=len(content),
        compressed_bytes=len(compressed),
    )
    return compressed


# --- Word documents ---------------------------------------------------------
#
# A .docx is a zip, so it is already compressed and re-deflating it rarely
# buys much. It is still worth doing: writers that store images without
# compression, or leave stale revision parts behind, produce files that a
# fresh zip shrinks noticeably, and the same "keep the original unless it
# actually got smaller" rule applies.

_OFFICE_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _looks_like_docx(content: bytes, filename: str) -> bool:
    if filename.lower().endswith(".docx"):
        return True
    return content[:2] == b"PK" and b"word/document.xml" in content


def _recompress_zip(content: bytes) -> bytes | None:
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as source:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as target:
                for item in source.infolist():
                    target.writestr(item, source.read(item.filename))
            return buffer.getvalue()
    except (zipfile.BadZipFile, OSError) as exc:
        logger.warning("docx_compression_failed", error=str(exc))
        return None


def compress_docx(content: bytes) -> bytes:
    """Return a smaller DOCX, or the original when re-zipping is not a win."""
    if not content or not _looks_like_docx(content, "") or len(content) < _MIN_BYTES:
        return content

    recompressed = _recompress_zip(content)
    if recompressed is None or len(recompressed) >= len(content) * (1 - _MIN_SAVING):
        return content

    logger.info(
        "docx_compressed",
        original_bytes=len(content),
        compressed_bytes=len(recompressed),
    )
    return recompressed


def compress_upload(content: bytes, *, filename: str = "", content_type: str = "") -> bytes:
    """Dispatch on the file type. Anything unrecognised is returned as-is."""
    lowered_type = (content_type or "").lower()
    lowered_name = (filename or "").lower()

    if lowered_type == "application/pdf" or lowered_name.endswith(".pdf") or content[:5] == b"%PDF-":
        return compress_pdf(content)
    if lowered_type in _OFFICE_CONTENT_TYPES or lowered_name.endswith(".docx") or _looks_like_docx(content, filename):
        return compress_docx(content)
    return content
