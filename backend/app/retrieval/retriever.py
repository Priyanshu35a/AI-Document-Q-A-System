import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Document
from app.ingestion.embedder import embedder
from app.ingestion.vector_store import vector_store

logger = logging.getLogger(__name__)

class Retriever:
    """
    Retrieves most relevant document chunks for a query using FAISS vector search
    and hydrates results from PostgreSQL.
    """

    def __init__(self, top_k: Optional[int] = None):
        self.top_k = top_k or settings.TOP_K

    def retrieve_chunks(
        self,
        query: str,
        db: Session,
        document_id: Optional[int] = None,
        user_id: Optional[int] = None,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Embeds the query, searches FAISS, and fetches chunk metadata from DB scoped to user.
        """
        k = top_k or self.top_k

        if vector_store.total_vectors == 0:
            logger.info("Vector store is empty. No chunks to retrieve.")
            return []

        # 1. Embed query
        query_vector = embedder.embed_query(query)

        # 2. Search FAISS index
        # Search a wider candidate pool to ensure multi-tenant and document-filtered recall
        search_k = max(k * 10, 60)
        vector_ids, scores = vector_store.search(query_vector, top_k=search_k)

        if not vector_ids:
            return []

        # Create score lookup map
        score_map = {vid: score for vid, score in zip(vector_ids, scores)}

        # 3. Query DB for matching chunks
        query_builder = (
            db.query(Chunk, Document.filename)
            .join(Document, Chunk.document_id == Document.id)
            .filter(Chunk.vector_id.in_(vector_ids))
        )

        if user_id is not None:
            query_builder = query_builder.filter(Document.user_id == user_id)

        if document_id is not None:
            query_builder = query_builder.filter(Chunk.document_id == document_id)

        db_results = query_builder.all()

        # 4. Assemble and order by FAISS similarity score
        retrieved = []
        for chunk, doc_name in db_results:
            similarity = score_map.get(chunk.vector_id, 0.0)
            retrieved.append({
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "document_name": doc_name,
                "page_number": chunk.page_number,
                "content": chunk.content,
                "score": round(similarity, 4)
            })

        # Sort descending by similarity score
        retrieved.sort(key=lambda x: x["score"], reverse=True)

        return retrieved[:k]

retriever = Retriever()
