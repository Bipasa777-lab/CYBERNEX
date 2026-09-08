from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class KnowledgeCollectionCreate(BaseModel):
    name: str
    description: Optional[str] = None


class KnowledgeCollectionSchema(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    document_count: int = 0
    vector_count: int = 0
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class KnowledgeSearchRequest(BaseModel):
    query: str
    collection: str = "SOPs"
    limit: int = 5


class KnowledgeSearchResult(BaseModel):
    text: str
    document_id: str
    filename: str
    page: int
    score: float


class DocumentSchema(BaseModel):
    id: str
    name: str
    type: str  # PDF, DOCX, XLSX, TXT, IMAGE
    collection: str  # SOPs, Manuals, Reports, Policies
    chunks: int
    status: str  # Indexed, Processing, Failed
    size: str
    updatedAt: str
    previewText: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
