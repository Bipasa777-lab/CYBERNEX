import os
import pytest
from app.services.documents.generator import doc_generator, PPTX_AVAILABLE

def test_generate_pptx():
    if not PPTX_AVAILABLE:
        pytest.skip("python-pptx not available")

    title = "CYBERNEX Sovereign AI Presentation"
    slides = [
        {"title": "1. Executive Summary", "content": "Zero cloud telemetry.\nAir-gapped infrastructure.\nMultimodal LLMs."},
        {"title": "2. Inspection Analysis", "content": "Vessel Pressure: 42.5 Bar\nTemperature: 280 deg C\nStatus: Compliant"}
    ]

    result = doc_generator.generate_pptx(title=title, slides=slides, output_name="Test_Presentation.pptx")

    assert result["type"] == "PPTX"
    assert result["name"] == "Test_Presentation.pptx"
    assert os.path.exists(result["file_path"])
    assert os.path.getsize(result["file_path"]) > 0

    # Cleanup
    if os.path.exists(result["file_path"]):
        os.remove(result["file_path"])


def test_generate_pptx_edge_cases():
    if not PPTX_AVAILABLE:
        pytest.skip("python-pptx not available")

    # Path traversal output_name attempt
    result = doc_generator.generate_pptx(
        title="Edge Case Presentation",
        slides=["Simple string slide", {"title": "Valid Slide", "content": "Content\nLine 2"}],
        output_name="../../malicious_presentation.pptx"
    )

    assert result["name"] == "malicious_presentation.pptx"
    assert os.path.basename(result["file_path"]) == "malicious_presentation.pptx"
    assert os.path.exists(result["file_path"])

    if os.path.exists(result["file_path"]):
        os.remove(result["file_path"])

