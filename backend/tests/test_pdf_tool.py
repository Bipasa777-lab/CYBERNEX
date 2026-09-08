"""Phase 7 tests: PDF tool (PyMuPDF) and the /api/v1/pdf/extract endpoint.

Synthetic PDFs are generated locally with PyMuPDF; no confidential industrial
documents are used.
"""

import io

import fitz
import pytest

from app.services.ocr.service import PADDLEOCR_AVAILABLE
from app.tools.pdf_tool import PDFExtractionError, clean_page_text, extract_pdf_text

requires_ocr = pytest.mark.skipif(
    not PADDLEOCR_AVAILABLE,
    reason="PaddleOCR is not installed in this environment",
)

# ---------------------------------------------------------------------------
# Synthetic PDF helpers
# ---------------------------------------------------------------------------

BLANK_PAGE = object()  # sentinel: completely empty page (no text, no images)
IMAGE_PAGE = object()  # sentinel: page containing only an image (no text)


def _tiny_pixmap():
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8))
    pix.clear_with(140)
    return pix


def _pdf_bytes(page_contents):
    doc = fitz.open()
    for content in page_contents:
        page = doc.new_page()
        if isinstance(content, str):
            page.insert_text((72, 72), content, fontsize=11)
        elif content is IMAGE_PAGE:
            page.insert_image(fitz.Rect(36, 36, 136, 136), pixmap=_tiny_pixmap())
        # BLANK_PAGE: leave the page without any content
    data = doc.tobytes()
    doc.close()
    return data


def _make_pdf(path, page_contents):
    path.write_bytes(_pdf_bytes(page_contents))
    return str(path)


def _upload_pdf(client, name, data, mime="application/pdf"):
    return client.post(
        "/api/v1/pdf/extract",
        files={"file": (name, io.BytesIO(data), mime)},
    )


# ---------------------------------------------------------------------------
# Unit tests: app.tools.pdf_tool
# ---------------------------------------------------------------------------


def test_extract_single_page_text_pdf(tmp_path):
    path = _make_pdf(tmp_path / "single.pdf", ["Inspection Report: boiler pressure nominal."])
    result = extract_pdf_text(path)

    assert result["filename"] == "single.pdf"
    assert result["page_count"] == 1
    assert len(result["pages"]) == 1

    page = result["pages"][0]
    assert page["page_number"] == 1
    assert "Inspection Report" in page["text"]
    assert page["has_text"] is True
    assert page["character_count"] == len(page["text"])


def test_extract_multipage_pdf_page_numbering(tmp_path):
    path = _make_pdf(tmp_path / "multi.pdf", ["Alpha page", "Bravo page", "Charlie page"])
    result = extract_pdf_text(path)

    assert result["page_count"] == 3
    assert [p["page_number"] for p in result["pages"]] == [1, 2, 3]
    assert "Alpha" in result["pages"][0]["text"]
    assert "Bravo" in result["pages"][1]["text"]
    assert "Charlie" in result["pages"][2]["text"]


def test_extract_empty_and_image_only_pages_no_ocr(tmp_path):
    path = _make_pdf(
        tmp_path / "mixed.pdf",
        ["Alpha page", BLANK_PAGE, IMAGE_PAGE, "Delta page"],
    )
    result = extract_pdf_text(path)

    assert result["page_count"] == 4
    blank = result["pages"][1]
    image_only = result["pages"][2]

    for page in (blank, image_only):
        assert page["text"] == ""
        assert page["character_count"] == 0
        assert page["has_text"] is False

    assert result["pages"][0]["has_text"] is True
    assert result["pages"][3]["has_text"] is True


def test_clean_page_text_normalizes_noise():
    raw = "  Title \r\n\r\n\r\n\r\nBody line with trailing   \n\u00a0\nEnd"
    cleaned = clean_page_text(raw)
    assert cleaned == "  Title\n\nBody line with trailing\n\nEnd"


def test_clean_page_text_empty_input():
    assert clean_page_text("") == ""
    assert clean_page_text("\n\n   \n\n") == ""


def test_extract_invalid_pdf_raises(tmp_path):
    path = tmp_path / "corrupted.pdf"
    path.write_bytes(b"this is definitely not a pdf document")
    with pytest.raises(PDFExtractionError):
        extract_pdf_text(str(path))


def test_extract_empty_file_raises(tmp_path):
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")
    with pytest.raises(PDFExtractionError):
        extract_pdf_text(str(path))


def test_extract_missing_file_raises(tmp_path):
    with pytest.raises(PDFExtractionError):
        extract_pdf_text(str(tmp_path / "does_not_exist.pdf"))


# ---------------------------------------------------------------------------
# API tests: POST /api/v1/pdf/extract
# ---------------------------------------------------------------------------


def test_api_pdf_extract_valid_pdf(client):
    data = _pdf_bytes(["Workbench extraction fixture."])
    res = _upload_pdf(client, "fixture_report.pdf", data)
    assert res.status_code == 200

    body = res.json()
    assert body["filename"] == "fixture_report.pdf"
    assert body["page_count"] == 1

    page = body["pages"][0]
    assert page["page_number"] == 1
    assert "Workbench extraction fixture" in page["text"]
    assert page["has_text"] is True
    assert page["character_count"] == len(page["text"])


def test_api_pdf_extract_multipage_numbering(client):
    data = _pdf_bytes(["One text", "Two text", "Three text"])
    res = _upload_pdf(client, "multipage_fixture.pdf", data)
    assert res.status_code == 200

    body = res.json()
    assert body["page_count"] == 3
    assert [p["page_number"] for p in body["pages"]] == [1, 2, 3]
    assert "Two text" in body["pages"][1]["text"]


def test_api_pdf_extract_response_structure(client):
    data = _pdf_bytes(["Structure probe."])
    res = _upload_pdf(client, "structure_fixture.pdf", data)
    assert res.status_code == 200

    body = res.json()
    assert set(body.keys()) == {"filename", "page_count", "pages"}
    assert set(body["pages"][0].keys()) == {
        "page_number", "text", "character_count", "has_text"
    }


@requires_ocr
def test_api_pdf_extract_page_without_text(client):
    data = _pdf_bytes(["Readable text", BLANK_PAGE, IMAGE_PAGE])
    res = _upload_pdf(client, "scanned_fixture.pdf", data)
    assert res.status_code == 200

    body = res.json()
    assert body["page_count"] == 3
    assert body["pages"][1]["has_text"] is False
    assert body["pages"][1]["text"] == ""
    assert body["pages"][2]["has_text"] is False
    assert body["pages"][0]["has_text"] is True


def test_api_pdf_extract_rejects_non_pdf(client):
    res = _upload_pdf(
        client,
        "notes.txt",
        b"plain text, not a pdf",
        mime="text/plain",
    )
    assert res.status_code == 400
    assert "PDF" in res.json()["detail"]


def test_api_pdf_extract_rejects_corrupted_pdf(client):
    res = _upload_pdf(client, "broken.pdf", b"definitely not a real pdf body")
    assert res.status_code == 422
    assert "detail" in res.json()


def test_api_pdf_extract_requires_file(client):
    res = client.post("/api/v1/pdf/extract")
    assert res.status_code == 422  # FastAPI validation: required file missing