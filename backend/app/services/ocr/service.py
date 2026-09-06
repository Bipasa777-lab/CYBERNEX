"""
Local OCR service (Phase 8).

PaddleOCR-based, fully on-premise text extraction from images and PDFs.

Sovereignty guarantees:
- OCR inference runs 100% locally. No cloud OCR, no external APIs, no
  upload of images/documents to the internet.
- The PaddleOCR inference engine is initialized once per process and reused
  across pages (lazy loading, cached on the service instance).

Behavior:
- text-based PDF pages are read with PyMuPDF and are NOT sent to OCR;
- pages without meaningful extractable text are rendered (in-memory, PNG)
  and processed with PaddleOCR;
- rendered PNG bytes are decoded with OpenCV in memory — no temporary image
  files are created or left behind.

Supported engine versions:
- PaddleOCR 3.x (``PaddleOCR(..., enable_mkldnn=False)``) — verified working
  on Windows with PaddlePaddle 3.3.x (CPU).
- PaddleOCR 2.x (``use_angle_cls`` API) — supported as a fallback path.
"""

import os
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import fitz  # PyMuPDF

from app.core.logging import logger

try:
    from paddleocr import PaddleOCR
    import paddleocr as _paddleocr_pkg

    PADDLEOCR_AVAILABLE = True
    _PADDLEOCR_MAJOR = int(str(getattr(_paddleocr_pkg, "__version__", "0")).split(".")[0])
except Exception:  # pragma: no cover - depends on environment
    PADDLEOCR_AVAILABLE = False
    _PADDLEOCR_MAJOR = 0

# Reasonable CPU-friendly resolution for OCR page rendering (dots per inch).
OCR_RENDER_DPI = 200


class OCRUnavailableError(RuntimeError):
    """Raised when the local OCR engine is not installed or cannot be initialized."""


class OCRProcessingError(RuntimeError):
    """Raised when OCR inference fails on a provided image.

    The message is intentionally generic and safe to expose; technical
    details are only written to the local log.
    """


class OCRService:
    """Reusable local OCR facade backed by PaddleOCR."""

    def __init__(self) -> None:
        self._ocr_engine: Any = None
        self._paddle_api_major: int = _PADDLEOCR_MAJOR

    # ------------------------------------------------------------------
    # Availability / engine lifecycle
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """True when a local PaddleOCR engine can be (and was) initialized."""
        return self._get_paddle_ocr() is not None

    def _engine_kwargs(self) -> Dict[str, Any]:
        """Kwargs used to construct PaddleOCR, adapted to the installed API.

        The 3.x pipeline needs MKLDNN disabled on Windows/PaddlePaddle 3.3.x:
        the oneDNN backend hits an upstream 'ConvertPirAttribute2RuntimeAttribute'
        crash while running the PP-OCRv6 inference programs, so we force the
        plain 'paddle' run mode (still fully local, just CPU-only).
        """
        if _PADDLEOCR_MAJOR >= 3:
            return {
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
                "lang": "en",
                "enable_mkldnn": False,
            }
        # PaddleOCR 2.x API
        return {"use_angle_cls": True, "lang": "en", "show_log": False}

    def _new_engine(self) -> Any:
        kwargs = self._engine_kwargs()
        try:
            return PaddleOCR(**kwargs)
        except (TypeError, ValueError) as exc:
            # Older 3.x releases may not know 'enable_mkldnn'; retry minimal.
            if _PADDLEOCR_MAJOR >= 3:
                logger.warning(
                    "PaddleOCR init with tuned kwargs failed (%s); retrying minimal config.", exc
                )
                return PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    lang="en",
                )
            raise

    def _get_paddle_ocr(self) -> Any:
        """Lazily build and cache the PaddleOCR engine (once per process)."""
        if self._ocr_engine is not None:
            return self._ocr_engine
        if not PADDLEOCR_AVAILABLE:
            logger.warning("PaddleOCR is not installed; local OCR is unavailable.")
            return None
        try:
            self._ocr_engine = self._new_engine()
            logger.info("PaddleOCR engine initialized.")
        except Exception as exc:
            logger.error(f"Failed to initialize PaddleOCR engine: {exc}")
            self._ocr_engine = None
        return self._ocr_engine

    # ------------------------------------------------------------------
    # Result parsing
    # ------------------------------------------------------------------

    def _extract_v3(self, results: Any) -> Tuple[List[str], List[float]]:
        """Parse PaddleOCR 3.x ``predict`` output (dict-like OCRResult objects)."""
        lines: List[str] = []
        scores: List[float] = []
        for res in results:
            if res is None:
                continue
            texts = None
            score_vals = None
            if hasattr(res, "get"):
                if "rec_texts" in res:
                    texts = res["rec_texts"]
                    score_vals = res.get("rec_scores")
                elif "text" in res:
                    texts = res["text"]
            if texts is None and hasattr(res, "text"):
                texts = res.text
            if isinstance(texts, str):
                texts = [texts]
            if isinstance(score_vals, (int, float)):
                score_vals = [score_vals]
            for index, item in enumerate(texts or []):
                if isinstance(item, str) and item.strip():
                    lines.append(item.strip())
                    if isinstance(score_vals, (list, tuple)) and index < len(score_vals):
                        try:
                            scores.append(float(score_vals[index]))
                        except (TypeError, ValueError):
                            pass
        return lines, scores

    def _extract_v2(self, result: Any) -> Tuple[List[str], List[float]]:
        """Parse PaddleOCR 2.x ``ocr`` output: [[[box, (text, conf)], ...], ...]."""
        lines: List[str] = []
        scores: List[float] = []
        if not result:
            return lines, scores
        first = result[0] if isinstance(result, list) else result
        if not first:
            return lines, scores
        for item in first:
            try:
                text, conf = item[1]
            except (IndexError, TypeError, ValueError):
                continue
            if isinstance(text, str) and text.strip():
                lines.append(text.strip())
                try:
                    scores.append(float(conf))
                except (TypeError, ValueError):
                    pass
        return lines, scores

    # ------------------------------------------------------------------
    # Core recognition
    # ------------------------------------------------------------------

    def _decode_image(self, image: Any) -> np.ndarray:
        """Convert an image (PNG bytes or ndarray) into a BGR ndarray in memory."""
        if isinstance(image, np.ndarray):
            arr = image
            if arr.ndim == 2:  # grayscale -> BGR
                return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
            if arr.ndim == 3 and arr.shape[2] == 4:  # RGBA -> BGR
                return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
            if arr.ndim == 3 and arr.shape[2] == 3:
                # PaddleOCR historically loads images with cv2.imread (BGR).
                return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            raise OCRProcessingError("Unsupported image array shape for OCR.")
        if isinstance(image, (bytes, bytearray, memoryview)):
            raw = np.frombuffer(bytes(image), dtype=np.uint8)
            arr = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if arr is None:
                raise OCRProcessingError("Could not decode the provided image bytes.")
            return arr
        if isinstance(image, str):  # convenience for local image file paths
            if not os.path.isfile(image):
                raise OCRProcessingError("Image file not found on local storage.")
            arr = cv2.imread(image, cv2.IMREAD_COLOR)
            if arr is None:
                raise OCRProcessingError("Could not read the provided image file.")
            return arr
        raise OCRProcessingError("Unsupported image input type for OCR.")

    def _text_and_score(self, image: Any) -> Tuple[str, Optional[float]]:
        """Run OCR on an in-memory image; returns (joined_text, mean_confidence)."""
        arr = self._decode_image(image)
        engine = self._get_paddle_ocr()
        if engine is None:
            raise OCRUnavailableError("Local OCR engine (PaddleOCR) is unavailable.")

        try:
            if self._paddle_api_major >= 3:
                results = engine.predict(arr)
                lines, scores = self._extract_v3(results)
            else:
                result = engine.ocr(arr, cls=True)
                lines, scores = self._extract_v2(result)
        except OCRUnavailableError:
            raise
        except Exception as exc:
            logger.error(f"PaddleOCR inference failed: {type(exc).__name__}")
            raise OCRProcessingError("OCR inference failed on the provided image.") from exc

        text = "\n".join(lines)
        mean_score = float(np.mean(scores)) if scores else None
        return text, mean_score

    def ocr_image(self, image: Any) -> str:
        """Extract text from an image (PNG bytes or ndarray), fully local.

        This is the primary reusable entry point of the OCR service.
        """
        text, _ = self._text_and_score(image)
        return text

    def extract_text_from_image(self, image: Any) -> str:
        """Alias of :meth:`ocr_image` for clarity in calling code."""
        return self.ocr_image(image)

    def ocr_image_bytes(self, image_bytes: bytes) -> str:
        """Extract text from encoded image bytes (PNG/JPEG), fully local."""
        return self.ocr_image(image_bytes)

    # ------------------------------------------------------------------
    # File-level pipeline (kept for RAG ingestion + /api/v1/ocr)
    # ------------------------------------------------------------------

    def extract_text(self, file_path: str, min_density_chars: int = 50) -> Dict[str, Any]:
        """High-level local text extraction for a stored file.

        PDF   -> PyMuPDF pages first; pages with insufficient text are rendered
                 and run through PaddleOCR.
        IMAGE -> PaddleOCR directly.
        TEXT  -> read as-is.

        Output contract (unchanged from Phase 7 scaffolding):
        {"text": str, "pages": int, "confidence": float, "engine": str}
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found for OCR: {file_path}")

        ext = file_path.rsplit(".", 1)[-1].lower() if "." in os.path.basename(file_path) else ""

        if ext == "pdf":
            return self._extract_pdf(file_path, min_density_chars)

        if ext in ("png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"):
            try:
                with open(file_path, "rb") as handle:
                    image_bytes = handle.read()
                text, mean_score = self._text_and_score(image_bytes)
                return {
                    "text": text,
                    "pages": 1,
                    "confidence": round(mean_score, 4) if mean_score is not None else 0.0,
                    "engine": "PaddleOCR",
                }
            except OCRUnavailableError:
                return {"text": "", "pages": 1, "confidence": 0.0, "engine": "OCR_UNAVAILABLE"}
            except Exception as exc:
                logger.error(f"Image OCR failed for '{file_path}': {type(exc).__name__}")
                return {"text": "", "pages": 1, "confidence": 0.0, "engine": "Error"}

        # Fallback: plain text file reading.
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read()
            return {"text": content, "pages": 1, "confidence": 1.0, "engine": "TextReader"}
        except Exception as exc:
            logger.error(f"Text read failed for '{file_path}': {type(exc).__name__}")
            return {"text": "", "pages": 0, "confidence": 0.0, "engine": "Error"}

    def _extract_pdf(self, file_path: str, min_density_chars: int) -> Dict[str, Any]:
        """PyMuPDF-first, page-aware OCR fallback for PDF files."""
        # Deferred import avoids a circular dependency (pdf_tool imports this service).
        from app.tools.pdf_tool import clean_page_text

        filename = os.path.basename(file_path)
        try:
            with open(file_path, "rb") as handle:
                pdf_bytes = handle.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            logger.error(f"Failed to open PDF '{filename}' for OCR: {type(exc).__name__}")
            return {"text": "", "pages": 0, "confidence": 0.0, "engine": "Error"}

        try:
            if doc.needs_pass:
                logger.warning(f"PDF '{filename}' is password protected; OCR skipped.")
                return {"text": "", "pages": len(doc), "confidence": 0.0, "engine": "Error"}

            zoom = OCR_RENDER_DPI / 72.0
            matrix = fitz.Matrix(zoom, zoom)

            parts: List[str] = []
            ocr_used = False
            engine_unavailable = not self.is_available
            score_values: List[float] = []

            for index, page in enumerate(doc):
                page_number = index + 1
                extracted = clean_page_text(page.get_text("text"))
                if len(extracted) >= min_density_chars:
                    parts.append(f"--- Page {page_number} ---\n{extracted}")
                    continue

                # Page has little/no meaningful text -> needs OCR.
                if engine_unavailable:
                    parts.append(f"--- Page {page_number} ---\n")
                    continue

                try:
                    pix = page.get_pixmap(matrix=matrix, alpha=False)
                    ocr_text, mean_score = self._text_and_score(pix.tobytes("png"))
                except Exception as exc:
                    logger.error(
                        f"OCR failed for page {page_number} of '{filename}': {type(exc).__name__}"
                    )
                    parts.append(f"--- Page {page_number} ---\n")
                    continue

                if mean_score is not None:
                    score_values.append(mean_score)
                if ocr_text.strip():
                    ocr_used = True
                    parts.append(f"--- Page {page_number} ---\n{ocr_text}")
                else:
                    parts.append(f"--- Page {page_number} ---\n")

            full_text = "\n\n".join(parts).strip()
            if engine_unavailable:
                engine = "OCR_UNAVAILABLE"
            elif ocr_used:
                engine = "PyMuPDF + PaddleOCR"
            else:
                engine = "PyMuPDF"

            if score_values:
                confidence = round(float(np.mean(score_values)), 4)
            else:
                confidence = 0.95 if full_text else 0.0

            return {
                "text": full_text,
                "pages": len(doc),
                "confidence": confidence,
                "engine": engine,
            }
        finally:
            doc.close()


# Process-wide singleton so the PaddleOCR engine (model weights) is loaded once
# and reused across requests/pages — never re-initialized per page.
ocr_service = OCRService()