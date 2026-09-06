# CYBERNEX — Sovereign Local FastAPI Backend

Clean, modular FastAPI backend for **CYBERNEX**: Sovereign On-Premise Agentic AI Workbench using Open-Weight Multimodal LLMs for Confidential Industrial Work.

## 🚀 Quick Start

### 1. Requirements
- Python 3.12 (recommended) or 3.13 — PaddlePaddle 3.3.x has no wheels for Python 3.14

### 2. Setup Virtual Environment
```bash
cd backend
python -m venv venv
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On Linux/macOS:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
```bash
cp .env.example .env
```

### 5. Launch FastAPI Server
```bash
uvicorn app.main:app --reload --port 8000
```

- **OpenAPI Interactive Documentation**: `http://127.0.0.1:8000/docs`
- **ReDoc Documentation**: `http://127.0.0.1:8000/redoc`
- **Health Check Endpoint**: `http://127.0.0.1:8000/api/v1/health`

---

## 🏛️ Directory Architecture

```
backend/
├── app/
│   ├── api/
│   │   ├── deps.py
│   │   └── v1/ (health, auth, workbench, tasks, files, models, knowledge, documents, runs, ocr, pdf, sandbox, security, system, settings)
│   ├── core/ (config, security, logging)
│   ├── db/ (database, models)
│   ├── schemas/ (Pydantic v2 schemas)
│   ├── services/ (agent, models/ollama, router, ocr, rag/qdrant, sandbox, documents, vision, security, system)
│   ├── tools/ (pdf_tool — Phase 7 PyMuPDF + Phase 8 PaddleOCR processing)
│   └── main.py
├── storage/ (uploads, documents, outputs, logs)
├── tests/
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🔒 Security & Local-First Guarantees

- **Zero External LLM Calls**: External connections disabled by default.
- **Isolated Sandbox**: Docker / subprocess resource-bounded python sandbox.
- **Air-Gap Telemetry**: Real-time monitoring of local network state.

---

## 📄 PDF Processing (Phase 7 + Phase 8 OCR)

**POST** `/api/v1/pdf/extract` — multipart upload (`file` field). Extracts text page-by-page. Fully local (no network calls, no cloud OCR).

Processing is decided **per page** (mixed digital/scanned documents are fully supported):

- **Digital pages** with a meaningful text layer → extracted with **PyMuPDF** (`source: "pymupdf"` internally).
- **Scanned/image-only pages** (no meaningful extractable text) → the page is rendered in-memory at 200 DPI and transcribed with **PaddleOCR** (`source: "ocr"` internally). Rendered images are never written to disk.
- Pages where neither method finds text keep `text: ""` and `has_text: false`.

- Page numbers are 1-based.
- Reusable logic lives in `app/tools/pdf_tool.py` (`extract_pdf_text(file_path, use_ocr=True)`); per-page dicts carry an informational `source` key (`"pymupdf"` / `"ocr"`) that is stripped from the public API response so the Phase 7 schema stays backward compatible.
- Validation: non-PDF → `400`, corrupted/password-protected PDF → `422`, oversized → `413` (`MAX_UPLOAD_SIZE_MB`). Uploaded files are temporary and always cleaned up — nothing is stored or sent anywhere.

### Local OCR service (`app/services/ocr/service.py`)

- Backed by **PaddleOCR** running **on-premise** — no external OCR API is ever called.
- Engine is initialized lazily once per process and reused for every page/request.
- Exposes `ocr_image(image)` / `ocr_image_bytes(bytes)` / `extract_text_from_image(image)` plus the higher-level `extract_text(file_path)` used by RAG ingestion and `POST /api/v1/ocr/extract`.
- PaddleOCR 3.x (with MKLDNN disabled — required to avoid a oneDNN/PIR crash on Windows CPU with PaddlePaddle 3.3.x) and the legacy 2.x API are both supported.
- Error handling: OCR-unavailable, OCR-failure and page-rendering failures surface as `422` with generic, non-stack-trace messages; failures are logged locally.

### Installing PaddleOCR

PaddlePaddle 3.3.x does **not** publish wheels for Python 3.14. Use **Python 3.12** (recommended) or 3.13 for the backend virtual environment:

```bash
cd backend
uv venv .venv --python 3.12        # or: python -m venv .venv  (Python 3.12)
pip install -r requirements.txt
```

On first OCR use, PaddleOCR downloads its pre-trained PP-OCR models into the user cache directory (once); afterwards all inference is fully offline.

Example response:

```json
{
  "filename": "inspection_report.pdf",
  "page_count": 3,
  "pages": [
    {"page_number": 1, "text": "...", "character_count": 512, "has_text": true},
    {"page_number": 2, "text": "...", "character_count": 87, "has_text": true},
    {"page_number": 3, "text": "", "character_count": 0, "has_text": false}
  ]
}
```
