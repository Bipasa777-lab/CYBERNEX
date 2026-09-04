"""Pydantic schemas for PDF processing (Phase 7)."""

from typing import List

from pydantic import BaseModel


class PDFPageSchema(BaseModel):
    """A single extracted PDF page.

    page_number is 1-based. has_text=False means the page contained no
    extractable text (scanned/image-only); no OCR is performed here — that is
    handled by the OCR module in Phase 8.
    """

    page_number: int
    text: str
    character_count: int
    has_text: bool


class PDFExtractionResponse(BaseModel):
    """Page-level text extraction result for an uploaded PDF."""

    filename: str
    page_count: int
    pages: List[PDFPageSchema]