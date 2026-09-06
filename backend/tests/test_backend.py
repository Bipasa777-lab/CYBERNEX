import io
import os
import zipfile
import pytest
from app.services.documents.generator import doc_generator, sanitize_xml_text
from app.services.models.ollama_client import OllamaProvider

ollama_provider = OllamaProvider()




def test_root_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_api_v1_health(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "services" in data


def test_auth_register_and_login(client):
    reg_payload = {
        "email": "test_operator@cybernex.local",
        "password": "sovereign_secure_password_123",
        "full_name": "Test Operator"
    }
    res = client.post("/api/v1/auth/register", json=reg_payload)
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["email"] == "test_operator@cybernex.local"

    login_payload = {
        "email": "test_operator@cybernex.local",
        "password": "sovereign_secure_password_123"
    }
    res_login = client.post("/api/v1/auth/login", json=login_payload)
    assert res_login.status_code == 200
    assert "access_token" in res_login.json()


def test_models_list(client):
    res = client.get("/api/v1/models")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_file_upload_and_metadata(client):
    file_content = b"Unit test document content for sovereign testing fixture."
    file_tuple = ("fixture_doc.pdf", io.BytesIO(file_content), "application/pdf")
    res = client.post("/api/v1/files/upload", files={"file": file_tuple})
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "fixture_doc.pdf"
    assert data["type"] == "PDF"
    file_id = data["id"]

    # Retrieve metadata
    meta_res = client.get(f"/api/v1/files/{file_id}")
    assert meta_res.status_code == 200
    assert meta_res.json()["name"] == "fixture_doc.pdf"


def test_task_and_run_creation(client):
    task_payload = {
        "prompt": "Summarize fixture report and generate deliverable.",
        "model": "Auto",
        "tools": ["OCR", "Knowledge"],
        "file_ids": []
    }
    res = client.post("/api/v1/tasks", json=task_payload)
    assert res.status_code == 200
    data = res.json()
    assert "task_id" in data
    assert "run_id" in data
    run_id = data["run_id"]

    # Verify run details endpoint
    run_res = client.get(f"/api/v1/runs/{run_id}")
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert run_data["id"] == run_id
    assert run_data["status"] == "completed"
    assert len(run_data["steps"]) >= 5


def test_security_and_system_status(client):
    sec_res = client.get("/api/v1/security/status")
    assert sec_res.status_code == 200
    assert "airGapStatus" in sec_res.json()

    sys_res = client.get("/api/v1/system/status")
    assert sys_res.status_code == 200
    assert "cpuUsage" in sys_res.json()
    assert "memoryUsage" in sys_res.json()
    assert "gpuUsage" in sys_res.json()


@pytest.mark.asyncio
async def test_ollama_unavailable_state():
    bad_provider = ollama_provider.__class__(base_url="http://127.0.0.1:99999")
    is_online = await bad_provider.health_check()
    assert is_online is False
    gen_text = await bad_provider.generate("Test prompt", "llama3")
    assert "OLLAMA_UNAVAILABLE" in gen_text


def test_sandbox_docker_status(client):
    code_payload = {
        "code": "print('Test Sandbox')",
        "language": "python"
    }
    res = client.post("/api/v1/sandbox/run", json=code_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ["SUCCESS", "SANDBOX_UNAVAILABLE"]


def test_sanitize_xml_text():
    dirty_text = "Sl. No. 2526\x00\x08\x0bPage 1\x0cReport \x1fOK \ud800Text"
    clean_text = sanitize_xml_text(dirty_text)
    # Control chars removed, form feed and vertical tab converted to \n
    assert "\x00" not in clean_text
    assert "\x08" not in clean_text
    assert "\x1f" not in clean_text
    assert "\ud800" not in clean_text
    assert "Sl. No. 2526" in clean_text
    assert "Page 1" in clean_text
    assert "\n" in clean_text


def test_docx_generation_regression():
    """
    Regression test: ensures DocumentGenerator.generate_docx produces a genuine
    OpenXML ZIP package (not a renamed plain text file) and that word/document.xml exists.
    """
    sections = [
        {"title": "1. Executive Summary\x0c", "content": "Summary text with OCR noise\x00\x08 and valid content."},
        {"title": "2. OCR Extracted Evidence", "content": "Sl. No. 252601611969\n\x0c--- Page 2 ---\nGRADE CARD\x00\x1fPASS"}
    ]
    out = doc_generator.generate_docx(
        title="Test Executive Report\x0c",
        sections=sections,
        output_name="Regression_Test_Report.docx"
    )

    file_path = out["file_path"]
    assert os.path.exists(file_path)
    assert out["name"] == "Regression_Test_Report.docx"
    assert out["type"] == "DOCX"

    # Must be larger than a plain text stub (typically > 10KB)
    assert os.path.getsize(file_path) > 5000

    # Must be a valid ZIP archive
    assert zipfile.is_zipfile(file_path)

    # Must contain OpenXML structural XML files
    with zipfile.ZipFile(file_path, "r") as zf:
        namelist = zf.namelist()
        assert "word/document.xml" in namelist
        assert "[Content_Types].xml" in namelist

        doc_xml = zf.read("word/document.xml").decode("utf-8")
        assert "Sl. No. 252601611969" in doc_xml
        assert "GRADE CARD" in doc_xml


def test_docx_download_api_regression(client):
    """
    API test: downloads generated DOCX and verifies content-type header
    and binary ZIP/DOCX package structure.
    """
    task_payload = {
        "prompt": "Extract all text from scanned document for DOCX test.",
        "model": "Auto",
        "tools": ["Knowledge"],
        "file_ids": []
    }
    task_res = client.post("/api/v1/tasks", json=task_payload)
    assert task_res.status_code == 200
    run_id = task_res.json()["run_id"]

    # Fetch run details to obtain generated deliverable
    run_res = client.get(f"/api/v1/runs/{run_id}")
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert len(run_data["deliverables"]) > 0

    deliv = run_data["deliverables"][0]
    download_url = deliv.get("downloadUrl") or deliv.get("download_url") or f"/api/v1/documents/{deliv['id']}/download"
    assert download_url.startswith("/api/v1/documents/")

    # Download deliverable via API
    dl_res = client.get(download_url)
    assert dl_res.status_code == 200

    expected_media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    content_type = dl_res.headers.get("content-type", "")
    assert expected_media_type in content_type

    # Verify binary DOCX payload is a valid ZIP package with word/document.xml
    body_bytes = dl_res.content
    assert len(body_bytes) > 5000
    assert zipfile.is_zipfile(io.BytesIO(body_bytes))

    with zipfile.ZipFile(io.BytesIO(body_bytes), "r") as zf:
        namelist = zf.namelist()
        assert "word/document.xml" in namelist
        assert "[Content_Types].xml" in namelist

