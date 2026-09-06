import io
import os
import zipfile
import pytest
from app.services.documents.generator import doc_generator, sanitize_xml_text


def test_sanitize_xml_text_edge_cases():
    # Null byte, bell, backspace, formfeed, vertical tab, unicode emoji, valid text
    sample = "Title\x00\x07\x08With\x0cPageBreak\x0bAndVerticalTab\x1fEnd \U0001F680"
    cleaned = sanitize_xml_text(sample)
    assert "\x00" not in cleaned
    assert "\x07" not in cleaned
    assert "\x08" not in cleaned
    assert "\x1f" not in cleaned
    assert "TitleWith" in cleaned
    assert "PageBreak\nAndVerticalTab" in cleaned
    assert "\U0001F680" in cleaned


def test_docx_regression_valid_zip_structure():
    """
    Ensures generated .docx is a valid ZIP package and contains OpenXML required files.
    """
    sections = [
        {
            "title": "Executive Summary",
            "content": "Line 1 with \x0cformfeed and \x00null byte.\n\nParagraph 2."
        },
        {
            "title": "OCR Findings",
            "content": "Sl. No. 252601611969\nBRAINWARE UNIVERSITY\nGRADE CARD"
        }
    ]
    res = doc_generator.generate_docx(
        title="Standalone Regression Report",
        sections=sections,
        output_name="test_standalone_deliverable.docx"
    )

    path = res["file_path"]
    assert os.path.exists(path)
    assert zipfile.is_zipfile(path)

    with zipfile.ZipFile(path, "r") as zf:
        members = zf.namelist()
        assert "word/document.xml" in members
        assert "[Content_Types].xml" in members
        assert "_rels/.rels" in members

        doc_xml = zf.read("word/document.xml").decode("utf-8")
        assert "Executive Summary" in doc_xml
        assert "BRAINWARE UNIVERSITY" in doc_xml
        assert "GRADE CARD" in doc_xml


def test_download_endpoint_docx_media_type(client):
    """
    Verifies that the /documents/{doc_id}/download endpoint returns
    application/vnd.openxmlformats-officedocument.wordprocessingml.document
    and valid DOCX ZIP payload.
    """
    from tests.conftest import TestingSessionLocal
    from app.db import models
    import uuid

    db = TestingSessionLocal()
    try:
        # Generate docx
        doc_res = doc_generator.generate_docx(
            title="Download Mime Test",
            sections=[{"title": "Section A", "content": "Content A"}],
            output_name=f"Report_{uuid.uuid4().hex[:6]}.docx"
        )
        doc_id = doc_res["id"]

        # Insert GeneratedOutput record
        out_record = models.GeneratedOutput(
            id=doc_id,
            name=doc_res["name"],
            file_type="DOCX",
            size=doc_res["size"],
            status="Verified",
            summary=doc_res["summary"],
            download_url=doc_res["download_url"],
            file_path=doc_res["file_path"]
        )
        db.add(out_record)
        db.commit()

        # Call download endpoint
        response = client.get(f"/api/v1/documents/{doc_id}/download")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        # Check binary ZIP structure
        payload = response.content
        assert zipfile.is_zipfile(io.BytesIO(payload))
        with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
            assert "word/document.xml" in zf.namelist()
            assert "[Content_Types].xml" in zf.namelist()
    finally:
        db.close()
