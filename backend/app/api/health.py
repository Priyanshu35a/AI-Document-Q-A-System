from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import os
from app.core.config import settings
from app.db.database import get_db
from app.generation.llm_provider import GeminiLLMProvider

router = APIRouter(prefix="/health", tags=["Health"])

llm_provider = GeminiLLMProvider(
    api_key=settings.GEMINI_API_KEY,
    model_name=settings.GEMINI_MODEL
)

@router.get("")
def health_check(db: Session = Depends(get_db)):
    """General system health check including database and FAISS index check."""
    # Check Database
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    # Check FAISS index file
    faiss_status = "not_created"
    if os.path.exists(settings.FAISS_INDEX_PATH):
        faiss_status = "present"

    return {
        "status": "online",
        "app_name": settings.PROJECT_NAME,
        "database": db_status,
        "faiss_index": faiss_status,
        "embedding_model": settings.effective_embedding_model
    }

@router.get("/llm")
def llm_health_check():
    """Verify Gemini API configuration and test credentials."""
    return llm_provider.check_health()
