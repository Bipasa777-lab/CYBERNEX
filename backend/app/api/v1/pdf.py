"""PDF processing endpoints (Phase 7).

Accepts a PDF upload, writes it to a temporary local file, extracts page-level
text via app.tools.pdf_tool (PyMuPDF, fully local) and returns structured JSON.

- Scanned/image-only pages are returned with text="" and has_text=false;
  OCR is intentionally NOT performed here (Phase 8 boundary).
- Uploaded files are temporary and always cleaned up; nothing is sent
  outside the machine.
"""

import os
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.core.logging import logger
from app.schemas.pdf import PDFExtractionResponse
from app.tools.pdf_tool import PDFExtractionError, extract_pdf_text

settings = get_settings()
router = APIRouter(prefix="/pdf", tags=["PDF"])

UPLOAD_CHUNK_SIZE_BYTES = 1024 * 1024  # stream uploads in 1 MB chunks


@router.post(
    "/extract",
    response_model=PDFExtractionResponse,
    summary="Extract Page-Level Text from PDF",
)
async def extract_pdf(file: UploadFile = File(...)):
    """Extract text page-by-page from an uploaded text-based PDF."""
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext != "pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only PDF files are accepted.",
        )

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    logger.info(f"PDF extraction requested for '{filename}'.")

    tmp_fd, tmp_path = tempfile.mkstemp(prefix="cybernex_pdf_", suffix=".pdf")
    try:
        with os.fdopen(tmp_fd, "wb") as buffer:
            size_bytes = 0
            while chunk := await file.read(UPLOAD_CHUNK_SIZE_BYTES):
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            "PDF exceeds the maximum upload size of "
                            f"{settings.MAX_UPLOAD_SIZE_MB} MB."
                        ),
                    )
                buffer.write(chunk)

        try:
            result = extract_pdf_text(tmp_path)
        except PDFExtractionError as exc:
            logger.warning(f"PDF extraction failed for '{filename}': {exc}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )
    finally:
        await file.close()
        try:
            os.remove(tmp_path)
        except OSError:
            pass  # temporary file cleanup is best-effort

    logger.info(
        f"PDF extraction endpoint completed for '{filename}' "
        f"({result['page_count']} pages, {size_bytes} bytes)."
    )

    return PDFExtractionResponse(
        filename=filename,
        page_count=result["page_count"],
        pages=result["pages"],
    )