import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db import models
from app.schemas.knowledge import DocumentSchema
from app.services.documents.generator import doc_generator

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("", response_model=List[DocumentSchema], summary="List Documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(models.Document).all()
    return [
        DocumentSchema(
            id=d.id,
            name=d.name,
            type=d.type,
            collection=d.collection_name,
            chunks=d.chunks_count,
            status=d.status,
            size=d.size,
            updatedAt=d.updated_at,
            previewText=d.preview_text
        ) for d in docs
    ]



@router.get("/{doc_id}", response_model=DocumentSchema, summary="Get Document Details")
def get_document(doc_id: str, db: Session = Depends(get_db)):
    d = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentSchema(
        id=d.id,
        name=d.name,
        type=d.type,
        collection=d.collection_name,
        chunks=d.chunks_count,
        status=d.status,
        size=d.size,
        updatedAt=d.updated_at,
        previewText=d.preview_text
    )


DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
PDF_MEDIA_TYPE = "application/pdf"

MEDIA_TYPE_MAP = {
    ".docx": DOCX_MEDIA_TYPE,
    ".xlsx": XLSX_MEDIA_TYPE,
    ".pptx": PPTX_MEDIA_TYPE,
    ".pdf": PDF_MEDIA_TYPE,
}


def _resolve_media_type(filename: str, file_type: str = None) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in MEDIA_TYPE_MAP:
        return MEDIA_TYPE_MAP[ext]
    if file_type:
        ft = file_type.upper()
        if ft == "DOCX":
            return DOCX_MEDIA_TYPE
        elif ft == "XLSX":
            return XLSX_MEDIA_TYPE
        elif ft == "PPTX":
            return PPTX_MEDIA_TYPE
        elif ft == "PDF":
            return PDF_MEDIA_TYPE
    return "application/octet-stream"


@router.get("/{doc_id}/download", summary="Download Generated Document")
def download_document(doc_id: str, db: Session = Depends(get_db)):
    out = db.query(models.GeneratedOutput).filter(models.GeneratedOutput.id == doc_id).first()
    if out and out.file_path and os.path.exists(out.file_path):
        media_type = _resolve_media_type(out.name or out.file_path, out.file_type)
        return FileResponse(
            path=out.file_path,
            filename=out.name,
            media_type=media_type
        )

    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if doc and doc.file_path and os.path.exists(doc.file_path):
        media_type = _resolve_media_type(doc.name or doc.file_path, doc.type)
        return FileResponse(
            path=doc.file_path,
            filename=doc.name,
            media_type=media_type
        )

    raise HTTPException(status_code=404, detail="Requested deliverable file not found on disk.")

