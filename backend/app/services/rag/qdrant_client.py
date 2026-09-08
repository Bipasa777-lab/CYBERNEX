import uuid
from typing import List, Dict, Any, Optional
from app.core.config import get_settings
from app.core.logging import logger
from app.services.rag.embeddings import embed_texts, embed_query, get_vector_dimension

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, VectorParams, PointStruct
    QDRANT_SDK_AVAILABLE = True
except ImportError:
    QDRANT_SDK_AVAILABLE = False

settings = get_settings()


class QdrantService:
    def __init__(self):
        self.url = settings.QDRANT_URL
        self._client = None
        if QDRANT_SDK_AVAILABLE:
            try:
                self._client = QdrantClient(url=self.url, timeout=3.0, check_compatibility=False)
            except Exception as e:
                logger.debug(f"Qdrant connection error: {e}")

    def health_check(self) -> bool:
        if not self._client:
            return False
        try:
            res = self._client.get_collections()
            return res is not None
        except Exception:
            return False

    def list_collections(self) -> List[Dict[str, Any]]:
        if not self.health_check():
            return []
        try:
            colls = self._client.get_collections().collections
            result = []
            for c in colls:
                try:
                    info = self._client.get_collection(collection_name=c.name)
                    vectors_count = getattr(info, "vectors_count", getattr(info, "points_count", 0)) or 0
                    points_count = getattr(info, "points_count", 0) or 0
                except Exception:
                    vectors_count = 0
                    points_count = 0

                result.append({
                    "name": c.name,
                    "document_count": points_count,
                    "vector_count": vectors_count
                })
            return result
        except Exception as e:
            logger.error(f"Error listing Qdrant collections: {e}")
            return []

    def create_collection(self, collection_name: str, vector_size: Optional[int] = None) -> bool:
        if not self.health_check():
            logger.warning(f"Qdrant unavailable. Cannot create collection {collection_name}")
            return False
        if vector_size is None:
            vector_size = get_vector_dimension()
        try:
            collections = [c.name for c in self._client.get_collections().collections]
            if collection_name not in collections:
                self._client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
                )
            return True
        except Exception as e:
            logger.error(f"Error creating collection {collection_name}: {e}")
            return False

    def upsert_chunks(
        self,
        collection_name: str,
        chunks: List[str],
        document_id: str,
        filename: str,
        start_page: int = 1
    ) -> bool:
        if not self.health_check() or not chunks:
            return False

        self.create_collection(collection_name)
        embeddings = embed_texts(chunks)
        if not embeddings:
            logger.warning("Could not generate embeddings for chunks.")
            return False

        points = []
        for idx, (chunk, vector) in enumerate(zip(chunks, embeddings)):
            point_id = str(uuid.uuid4())
            payload = {
                "text": chunk,
                "document_id": document_id,
                "filename": filename,
                "page": start_page + idx,
                "chunk_index": idx
            }
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        try:
            self._client.upsert(collection_name=collection_name, points=points)
            logger.info(f"Upserted {len(points)} vector chunks into Qdrant collection '{collection_name}'")
            return True
        except Exception as e:
            logger.error(f"Error upserting vectors to Qdrant: {e}")
            return False

    def search(
        self,
        collection_name: str,
        query_text: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Executes real semantic vector search against Qdrant.
        """
        if not self.health_check():
            logger.warning("Qdrant service unavailable for search.")
            return []

        query_vector = embed_query(query_text)
        if not query_vector:
            logger.warning("Could not generate query embedding.")
            return []

        try:
            results = self._client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit
            )
            hits = []
            for hit in results:
                payload = hit.payload or {}
                hits.append({
                    "text": payload.get("text", ""),
                    "document_id": payload.get("document_id", ""),
                    "filename": payload.get("filename", ""),
                    "page": payload.get("page", 1),
                    "score": round(hit.score, 4)
                })
            return hits
        except Exception as e:
            logger.error(f"Qdrant vector search failed: {e}")
            return []


qdrant_service = QdrantService()

