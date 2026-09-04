# CYBERNEX — Sovereign Local FastAPI Backend

Clean, modular FastAPI backend for **CYBERNEX**: Sovereign On-Premise Agentic AI Workbench using Open-Weight Multimodal LLMs for Confidential Industrial Work.

## 🚀 Quick Start

### 1. Requirements
- Python 3.11+

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
│   ├── tools/ (pdf_tool — Phase 7 local PDF processing)
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

## 📄 PDF Processing (Phase 7)

**POST** `/api/v1/pdf/extract` — multipart upload (`file` field). Extracts text page-by-page from text-based PDFs using PyMuPDF, fully local (no network calls).

- Page numbers are 1-based. Scanned/image-only pages return `text: ""` with `has_text: false` — no OCR is performed here (OCR is Phase 8).
- Reusable logic lives in `app/tools/pdf_tool.py` (`extract_pdf_text(file_path)`) so future OCR/RAG/LangGraph phases can consume the same structure.
- Validation: non-PDF → `400`, corrupted/password-protected PDF → `422`, oversized → `413` (`MAX_UPLOAD_SIZE_MB`). Uploaded files are temporary and always cleaned up — nothing is stored or sent anywhere.

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
