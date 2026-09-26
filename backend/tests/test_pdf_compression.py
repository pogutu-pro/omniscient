"""PDF compression must be a safe no-op when it cannot help.

The upload path may never fail, or grow a file, because of the compression
step. These tests pin that contract. Actually shrinking a PDF needs
ghostscript plus a large, compressible input, neither of which the test
runner guarantees, so that path is exercised in production rather than
here — but every degradation path is covered.
"""
from __future__ import annotations

from app.services.pdf_compression import compress_pdf


def test_non_pdf_is_returned_unchanged():
    assert compress_pdf(b"just some text, no pdf magic here") == b"just some text, no pdf magic here"


def test_undersized_pdf_is_returned_unchanged():
    # Below the size floor, so ghostscript is never even invoked.
    small = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    assert compress_pdf(small) == small


def test_unreadable_pdf_is_returned_byte_for_byte():
    # Above the floor, so ghostscript (when present) is tried and fails on
    # the malformed body. The original must come back untouched rather than
    # the call raising or returning something smaller-but-broken.
    bogus = b"%PDF-1.4 broken payload " * 20000
    assert compress_pdf(bogus) == bogus


def test_empty_input_is_a_no_op():
    assert compress_pdf(b"") == b""
