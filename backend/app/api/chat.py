import time
import json
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import settings
from app.db.database import get_db, SessionLocal
from app.db.models import ChatMessage, Document, User
from app.core.security import get_current_user
from app.retrieval.retriever import retriever
from app.generation.llm_provider import GeminiLLMProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])

# LLM provider instance
llm_provider = GeminiLLMProvider(
    api_key=settings.GEMINI_API_KEY,
    model_name=settings.GEMINI_MODEL
)

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Natural language question")
    document_id: Optional[int] = Field(None, description="Optional ID of document to restrict search")

class Citation(BaseModel):
    document_id: int
    document_name: str
    page_number: int
    snippet: str
    score: float

class LatencyMetrics(BaseModel):
    retrieval_ms: float
    generation_ms: float
    total_ms: float

class ChatResponse(BaseModel):
    question: str
    answer: str
    citations: List[Citation]
    model: str
    latency: Optional[LatencyMetrics] = None

@router.post("", response_model=ChatResponse)
def ask_question(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    RAG Chat endpoint with latency telemetry breakdown:
    1. Embeds question and retrieves top-k relevant chunks from FAISS + PostgreSQL.
    2. Constructs grounded prompt.
    3. Generates answer using Gemini API with citation and no-hallucination guardrails.
    4. Records performance metrics and logs to chat history.
    """
    t_start = time.perf_counter()
    question = request.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty."
        )

    # Check if any documents exist for this user
    total_docs = db.query(Document).filter(Document.user_id == current_user.id).count()
    if total_docs == 0:
        empty_answer = "No documents have been uploaded to your workspace yet. Please upload a PDF document before asking questions."
        return ChatResponse(
            question=question,
            answer=empty_answer,
            citations=[],
            model=settings.GEMINI_MODEL,
            latency=LatencyMetrics(retrieval_ms=0.0, generation_ms=0.0, total_ms=0.0)
        )

    # 1. Retrieve relevant chunks scoped strictly to current_user
    chunks = retriever.retrieve_chunks(
        query=question,
        db=db,
        document_id=request.document_id,
        user_id=current_user.id,
        top_k=settings.TOP_K
    )
    t_retrieved = time.perf_counter()
    retrieval_ms = round((t_retrieved - t_start) * 1000, 2)

    # If no relevant chunks retrieved
    if not chunks:
        no_context_answer = "I cannot find any relevant passages in your uploaded documents to answer your question."
        return ChatResponse(
            question=question,
            answer=no_context_answer,
            citations=[],
            model=settings.GEMINI_MODEL,
            latency=LatencyMetrics(retrieval_ms=retrieval_ms, generation_ms=0.0, total_ms=retrieval_ms)
        )

    # 2. Generate answer via LLM
    result = llm_provider.generate_answer(query=question, context_chunks=chunks)
    t_generated = time.perf_counter()
    generation_ms = round((t_generated - t_retrieved) * 1000, 2)
    total_ms = round((t_generated - t_start) * 1000, 2)

    answer_text = result["answer"]
    model_name = result.get("model", settings.GEMINI_MODEL)

    # 3. Format citations
    citations = [
        Citation(
            document_id=c["document_id"],
            document_name=c["document_name"],
            page_number=c["page_number"],
            snippet=c["content"],
            score=c["score"]
        )
        for c in chunks
    ]

    latency_data = LatencyMetrics(
        retrieval_ms=retrieval_ms,
        generation_ms=generation_ms,
        total_ms=total_ms
    )

    # 4. Save to chat history associated with current user
    user_msg = ChatMessage(user_id=current_user.id, role="user", content=question)
    db.add(user_msg)
    
    assistant_msg = ChatMessage(
        user_id=current_user.id,
        role="assistant",
        content=answer_text,
        citations=[c.dict() for c in citations]
    )
    db.add(assistant_msg)
    db.commit()

    return ChatResponse(
        question=question,
        answer=answer_text,
        citations=citations,
        model=model_name,
        latency=latency_data
    )

@router.post("/stream")
def ask_question_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Server-Sent Events (SSE) streaming endpoint:
    Streams answer tokens in real-time while providing telemetry metrics and citations.
    """
    t_start = time.perf_counter()
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    user_id = current_user.id
    doc_id = request.document_id

    total_docs = db.query(Document).filter(Document.user_id == user_id).count()
    if total_docs == 0:
        def empty_gen():
            payload = {
                "type": "error",
                "message": "No documents uploaded yet. Please upload a PDF before asking questions."
            }
            yield f"data: {json.dumps(payload)}\n\n"
        return StreamingResponse(empty_gen(), media_type="text/event-stream")

    # 1. Retrieve chunks
    chunks = retriever.retrieve_chunks(
        query=question,
        db=db,
        document_id=doc_id,
        user_id=user_id,
        top_k=settings.TOP_K
    )
    t_retrieved = time.perf_counter()
    retrieval_ms = round((t_retrieved - t_start) * 1000, 2)

    citations = [
        {
            "document_id": c["document_id"],
            "document_name": c["document_name"],
            "page_number": c["page_number"],
            "snippet": c["content"],
            "score": c["score"]
        }
        for c in chunks
    ]

    if not chunks:
        def no_chunk_gen():
            payload = {
                "type": "error",
                "message": "I cannot find any relevant passages in your uploaded documents."
            }
            yield f"data: {json.dumps(payload)}\n\n"
        return StreamingResponse(no_chunk_gen(), media_type="text/event-stream")

    def sse_event_stream():
        # Step A: Emit metadata event (citations & retrieval latency)
        meta_payload = {
            "type": "metadata",
            "citations": citations,
            "latency": {"retrieval_ms": retrieval_ms}
        }
        yield f"data: {json.dumps(meta_payload)}\n\n"

        # Step B: Stream tokens from LLM
        stream_gen = llm_provider.generate_answer_stream(query=question, context_chunks=chunks)
        full_text = ""
        model_used = settings.GEMINI_MODEL

        for event in stream_gen:
            if event["type"] == "delta":
                full_text += event["text"]
                delta_payload = {"type": "delta", "text": event["text"]}
                yield f"data: {json.dumps(delta_payload)}\n\n"
            elif event["type"] == "done":
                model_used = event.get("model", model_used)
                if event.get("full_text"):
                    full_text = event["full_text"]

        t_end = time.perf_counter()
        generation_ms = round((t_end - t_retrieved) * 1000, 2)
        total_ms = round((t_end - t_start) * 1000, 2)

        done_payload = {
            "type": "done",
            "model": model_used,
            "latency": {
                "retrieval_ms": retrieval_ms,
                "generation_ms": generation_ms,
                "total_ms": total_ms
            }
        }
        yield f"data: {json.dumps(done_payload)}\n\n"

        # Persist conversation to DB in isolated session
        try:
            with SessionLocal() as save_db:
                user_msg = ChatMessage(user_id=user_id, role="user", content=question)
                save_db.add(user_msg)
                asst_msg = ChatMessage(
                    user_id=user_id,
                    role="assistant",
                    content=full_text,
                    citations=citations
                )
                save_db.add(asst_msg)
                save_db.commit()
        except Exception as save_err:
            logger.error(f"Failed to persist streamed chat message: {save_err}")

    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.get("/history")
def get_chat_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetches full chat history in chronological order for the authenticated user."""
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [
        {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "citations": msg.citations or [],
            "created_at": msg.created_at.isoformat()
        }
        for msg in messages
    ]

@router.delete("/history")
def clear_chat_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Clears all stored chat history for the authenticated user."""
    db.query(ChatMessage).filter(ChatMessage.user_id == current_user.id).delete()
    db.commit()
    return {"status": "success", "message": "Chat history cleared successfully."}
