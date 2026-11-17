import csv
import io
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.database import get_db
from app.db.models import Document, Chunk, User
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sheets", tags=["Database Sheets"])

def format_file_size(bytes_size: int) -> str:
    if not bytes_size:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

@router.get("/summary")
def get_sheets_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aggregate summary statistics for user's database sheet."""
    docs = db.query(Document).filter(Document.user_id == current_user.id).all()
    doc_ids = [d.id for d in docs]

    total_chunks = 0
    total_bytes = sum(d.file_size for d in docs)
    total_pages = sum(d.page_count for d in docs)

    if doc_ids:
        total_chunks = db.query(Chunk).filter(Chunk.document_id.in_(doc_ids)).count()

    return {
        "total_documents": len(docs),
        "total_chunks": total_chunks,
        "total_pages": total_pages,
        "total_storage_formatted": format_file_size(total_bytes)
    }

@router.get("/documents")
def get_documents_sheet(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns spreadsheet-formatted rows for user's documents."""
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(desc(Document.created_at))
        .all()
    )

    rows = []
    for idx, doc in enumerate(docs, 1):
        rows.append({
            "row_index": idx,
            "id": doc.id,
            "filename": doc.filename,
            "file_size": doc.file_size,
            "file_size_formatted": format_file_size(doc.file_size),
            "page_count": doc.page_count,
            "chunk_count": doc.chunk_count,
            "status": "Ready / Indexed",
            "created_at": doc.created_at.strftime("%Y-%m-%d %H:%M:%S")
        })
    return rows

@router.get("/chunks")
def get_chunks_sheet(
    document_id: Optional[int] = Query(None, description="Filter by Document ID"),
    search: Optional[str] = Query(None, description="Search keyword in chunk text"),
    limit: int = Query(250, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns spreadsheet-formatted rows for user's text chunks with search and document filtering."""
    query = (
        db.query(Chunk, Document.filename)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Document.user_id == current_user.id)
    )

    if document_id is not None:
        query = query.filter(Chunk.document_id == document_id)

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        query = query.filter(Chunk.content.ilike(search_term))

    total_count = query.count()
    results = query.order_by(Chunk.document_id.asc(), Chunk.chunk_index.asc()).offset(offset).limit(limit).all()

    rows = []
    for idx, (chunk, doc_name) in enumerate(results, start=offset + 1):
        clean_content = chunk.content.strip()
        rows.append({
            "row_index": idx,
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "document_name": doc_name,
            "page_number": chunk.page_number,
            "chunk_index": chunk.chunk_index,
            "vector_id": chunk.vector_id,
            "content_snippet": (clean_content[:120] + "...") if len(clean_content) > 120 else clean_content,
            "full_content": clean_content,
            "char_count": len(clean_content),
            "created_at": chunk.created_at.strftime("%Y-%m-%d %H:%M:%S")
        })

    return {
        "total": total_count,
        "offset": offset,
        "limit": limit,
        "rows": rows
    }

@router.get("/export-csv")
def export_csv(
    sheet_type: str = Query("chunks", description="'chunks' or 'documents'"),
    document_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exports user's document or chunk database as a downloadable CSV spreadsheet."""
    output = io.StringIO()
    writer = csv.writer(output)

    if sheet_type == "documents":
        docs = (
            db.query(Document)
            .filter(Document.user_id == current_user.id)
            .order_by(desc(Document.created_at))
            .all()
        )
        writer.writerow(["Row #", "Doc ID", "Filename", "Pages", "Chunks", "Size (Bytes)", "Formatted Size", "Created At"])
        for idx, d in enumerate(docs, 1):
            writer.writerow([
                idx,
                d.id,
                d.filename,
                d.page_count,
                d.chunk_count,
                d.file_size,
                format_file_size(d.file_size),
                d.created_at.strftime("%Y-%m-%d %H:%M:%S")
            ])
        filename = f"documents_database_{current_user.username}.csv"
    else:
        query = (
            db.query(Chunk, Document.filename)
            .join(Document, Chunk.document_id == Document.id)
            .filter(Document.user_id == current_user.id)
        )
        if document_id is not None:
            query = query.filter(Chunk.document_id == document_id)

        chunks_data = query.order_by(Chunk.document_id.asc(), Chunk.chunk_index.asc()).all()
        writer.writerow(["Row #", "Chunk ID", "Doc ID", "Document Name", "Page Number", "Chunk Index", "Vector ID", "Length (chars)", "Text Content", "Created At"])
        for idx, (c, doc_name) in enumerate(chunks_data, 1):
            writer.writerow([
                idx,
                c.id,
                c.document_id,
                doc_name,
                c.page_number,
                c.chunk_index,
                c.vector_id,
                len(c.content),
                c.content,
                c.created_at.strftime("%Y-%m-%d %H:%M:%S")
            ])
        filename = f"chunks_database_{current_user.username}.csv"

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
