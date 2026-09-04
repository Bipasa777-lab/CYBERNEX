"""
PDF processing tool (Phase 7).

Local, page-level text extraction for text-based PDFs using PyMuPDF (fitz).

Sovereignty guarantees:
- Runs 100% locally. No cloud APIs, no external services, no network calls.
- Does NOT perform OCR: pages without extractable text are returned with
  text="" and has_text=False (OCR belongs to Phase 8).

Output contract (consumed by the API layer now; future OCR/RAG/LangGraph
phases can consume the same plain-dict structure directly):

{
    "filename": "inspection_report.pdf",
    "page_count": 3,
    "pages": [
        {"page_number": 1, "text": "...", "character_count": 512, "has_text": True},
        {"page_number": 2, "text": "...", "character_count": 87,  "has_text": True},
        {"page_number": 3, "text": "",    "character_count": 0,   "has_text": False}
    ]
}
"""

import os
import time
from typing import Any, Dict, List

import fitz  # PyMuPDF

from app.core.logging import logger


class PDFExtractionError(Exception):
    """Raised when a PDF cannot be opened, decrypted, or processed locally.

    The message is intentionally generic and safe to expose to API clients;
    internal details are only written to the local log.
    """


def clean_page_text(raw_text: str) -> str:
    """Lightweight whitespace normalization for an extracted page.

    Preserves document structure (headings, paragraphs, numbers, units,
    tables/line layout as provided by PyMuPDF) while removing obvious noise:
    - normalizes CRLF / CR line endings to LF
    - normalizes non-breaking spaces to regular spaces
    - strips trailing whitespace per line (leading indentation is kept so
      table alignment survives)
    - collapses repeated blank lines to a single blank line
    - drops leading/trailing blank lines
    """
    if not raw_text:
        return ""

    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")

    lines = [line.rstrip() for line in text.split("\n")]

    cleaned: List[str] = []
    blank_run = 0
    for line in lines:
        if not line:
            blank_run += 1
            if blank_run == 1:
                cleaned.append(line)
        else:
            blank_run = 0
            cleaned.append(line)

    while cleaned and not cleaned[0]:
        cleaned.pop(0)
    while cleaned and not cleaned[-1]:
        cleaned.pop()

    return "\n".join(cleaned)


def extract_pdf_text(file_path: str) -> Dict[str, Any]:
    """Extract text from a text-based PDF page by page, fully locally.

    Args:
        file_path: Path to the PDF file on the local filesystem.

    Returns:
        Structured dict with the document filename, page_count and a list of
        per-page dicts (1-based page_number, cleaned text, character_count,
        has_text). Pages without extractable text (scanned/image-only) come
        back with text="" and has_text=False; no OCR is attempted here.

    Raises:
        PDFExtractionError: If the file is missing, empty, corrupted,
            password protected, or otherwise unreadable as a PDF.
    """
    started = time.perf_counter()

    if not os.path.isfile(file_path):
        raise PDFExtractionError("PDF file not found on local storage.")

    filename = os.path.basename(file_path)
    logger.info(f"PDF processing started for '{filename}'.")

    # Read locally and open from memory so PyMuPDF never holds an OS file
    # handle on our file. This keeps temporary-file cleanup deterministic,
    # even when the document is corrupted (failed fitz.open on a path can
    # leak the handle on Windows and block deletion).
    try:
        with open(file_path, "rb") as handle:
            pdf_bytes = handle.read()
    except OSError as exc:
        logger.error(f"Failed to read PDF file '{filename}': {type(exc).__name__}")
        raise PDFExtractionError("PDF file could not be read from local storage.") from exc

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        logger.error(f"Failed to open PDF '{filename}': {type(exc).__name__}")
        raise PDFExtractionError("Invalid or corrupted PDF file.") from exc

    try:
        if doc.needs_pass:
            logger.warning(f"PDF '{filename}' is password protected.")
            raise PDFExtractionError("PDF is password protected and cannot be read.")

        pages: List[Dict[str, Any]] = []
        for index, page in enumerate(doc):
            page_number = index + 1  # expose 1-based page numbers
            text = clean_page_text(page.get_text("text"))
            pages.append(
                {
                    "page_number": page_number,
                    "text": text,
                    "character_count": len(text),
                    "has_text": bool(text),
                }
            )

        result: Dict[str, Any] = {
            "filename": filename,
            "page_count": len(pages),
            "pages": pages,
        }

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            f"PDF processing completed for '{filename}': {len(pages)} pages "
            f"({duration_ms:.1f} ms)."
        )
        return result
    except PDFExtractionError:
        raise
    except Exception as exc:
        logger.error(f"Failed while reading PDF '{filename}': {type(exc).__name__}")
        raise PDFExtractionError("PDF could not be processed.") from exc
    finally:
        doc.close()