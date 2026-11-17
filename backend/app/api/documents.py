import os
import shutil
import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Document, Chunk, User
from app.core.security import get_current_user
from app.ingestion.document_parser import DocumentParser, DocumentParsingError
from app.ingestion.chunker import TextChunker
from app.ingestion.embedder import embedder
from app.ingestion.vector_store import vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Uploads a PDF or Image (bills, receipts, handwritten/printed notes), extracts page-aware text,
    chunks it, generates BGE-M3 embeddings, and stores chunks in DB and vectors in FAISS.
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file format '{ext}'. Supported formats: PDF (.pdf) and Images (.png, .jpg, .jpeg, .webp)."
        )

    # Sanitize and assign unique file path to prevent collisions
    unique_prefix = uuid.uuid4().hex[:8]
    sanitized_filename = os.path.basename(file.filename).replace(" ", "_")
    saved_filename = f"{unique_prefix}_{sanitized_filename}"
    saved_path = os.path.join(settings.UPLOAD_DIR, saved_filename)

    try:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        # Save file to disk
        with open(saved_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = os.path.getsize(saved_path)
        if file_size == 0:
            os.remove(saved_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes)."
            )

        # 1. Parse Document or Image
        try:
            pages = DocumentParser.parse_document(saved_path, file.filename)
        except DocumentParsingError as pe:
            if os.path.exists(saved_path):
                os.remove(saved_path)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(pe)
            )

        # 2. Chunk text while preserving page number
        chunker = TextChunker(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP
        )
        chunk_data = chunker.chunk_pages(pages)

        if not chunk_data:
            if os.path.exists(saved_path):
                os.remove(saved_path)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not extract any textual chunks from the PDF."
            )

        # 3. Create Document Record in DB
        doc_record = Document(
            user_id=current_user.id,
            filename=file.filename,
            file_path=saved_path,
            file_size=file_size,
            page_count=len(pages),
            chunk_count=len(chunk_data)
        )
        db.add(doc_record)
        db.flush()  # Populates doc_record.id

        # 4. Generate BGE-M3 Embeddings
        texts_to_embed = [c["content"] for c in chunk_data]
        embeddings = embedder.embed_texts(texts_to_embed)

        # 5. Insert Chunks into DB and populate FAISS
        # Find next vector ID offset (use DB sequence or auto-incrementing id)
        max_chunk = db.query(Chunk.id).order_by(desc(Chunk.id)).first()
        start_id = (max_chunk[0] + 1) if max_chunk else 1

        db_chunks = []
        vector_ids = []
        for i, c in enumerate(chunk_data):
            vec_id = start_id + i
            db_chunk = Chunk(
                document_id=doc_record.id,
                page_number=c["page_number"],
                chunk_index=c["chunk_index"],
                content=c["content"],
                vector_id=vec_id
            )
            db_chunks.append(db_chunk)
            vector_ids.append(vec_id)

        db.bulk_save_objects(db_chunks)
        db.commit()

        # Add vectors to FAISS index
        vector_store.add_vectors(embeddings, vector_ids)

        logger.info(
            f"Successfully processed document '{file.filename}' (ID: {doc_record.id}): "
            f"{len(pages)} pages, {len(chunk_data)} chunks, {embeddings.shape[0]} vectors."
        )

        return {
            "status": "success",
            "document": {
                "id": doc_record.id,
                "filename": doc_record.filename,
                "page_count": doc_record.page_count,
                "chunk_count": doc_record.chunk_count,
                "file_size": doc_record.file_size,
                "created_at": doc_record.created_at.isoformat()
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process uploaded file: {e}", exc_info=True)
        if os.path.exists(saved_path):
            try:
                os.remove(saved_path)
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing the PDF: {str(e)}"
        )


@router.get("")
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lists all uploaded documents for the authenticated user."""
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(desc(Document.created_at))
        .all()
    )
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "file_size": doc.file_size,
            "page_count": doc.page_count,
            "chunk_count": doc.chunk_count,
            "created_at": doc.created_at.isoformat()
        }
        for doc in docs
    ]


@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deletes a document and its associated chunks from PostgreSQL and FAISS for authenticated user.
    """
    doc = db.query(Document).filter(
        Document.id == doc_id,
        Document.user_id == current_user.id
    ).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {doc_id} not found."
        )

    # 1. Fetch vector IDs associated with document chunks
    chunks = db.query(Chunk.vector_id).filter(Chunk.document_id == doc_id).all()
    vector_ids = [c[0] for c in chunks if c[0] is not None]

    # 2. Remove vectors from FAISS
    if vector_ids:
        vector_store.remove_vectors(vector_ids)

    # 3. Remove physical file from disk
    if doc.file_path and os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception as e:
            logger.warning(f"Could not delete physical file {doc.file_path}: {e}")

    # 4. Delete document record (cascade deletes chunks in DB)
    db.delete(doc)
    db.commit()

    logger.info(f"Deleted document ID {doc_id} and {len(vector_ids)} vectors.")
    return {"status": "success", "message": f"Document {doc_id} deleted successfully."}
