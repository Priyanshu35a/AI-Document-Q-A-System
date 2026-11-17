import os
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.db.database import engine, Base
from app.api.health import router as health_router
from app.api.documents import router as documents_router
from app.api.chat import router as chat_router
from app.api.auth import router as auth_router
from app.api.sheets import router as sheets_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("rag-backend")

from sqlalchemy import text

def init_db_with_retry(max_retries=10, delay=2):
    """Wait for database to become ready, create tables, and apply column migrations."""
    for attempt in range(max_retries):
        try:
            logger.info(f"Connecting to database (attempt {attempt + 1}/{max_retries})...")
            Base.metadata.create_all(bind=engine)

            # Ensure user_id column exists on pre-existing database tables
            with engine.connect() as conn:
                try:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN user_id INTEGER REFERENCES users(id)"))
                    conn.commit()
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE chat_history ADD COLUMN user_id INTEGER REFERENCES users(id)"))
                    conn.commit()
                except Exception:
                    pass

            logger.info("Database tables verified/created successfully.")
            return
        except OperationalError as e:
            logger.warning(f"Database not ready yet: {e}")
            time.sleep(delay)
        except Exception as e:
            logger.error(f"Unexpected database initialization error: {e}")
            break
    logger.warning("Could not automatically initialize database tables. Will continue startup.")

import threading

def _warmup_embedder():
    """Pre-warms the embedding model in a background thread to eliminate first-query cold start."""
    try:
        from app.ingestion.embedder import embedder
        logger.info(f"Pre-warming {embedder.model_name} embedding model in background...")
        embedder.embed_query("warmup query")
        logger.info(f"{embedder.model_name} embedding model pre-warmed and ready in RAM.")
    except Exception as e:
        logger.warning(f"Embedding warmup warning: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure storage directories exist
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(settings.FAISS_INDEX_PATH) or ".", exist_ok=True)

    # Initialize Database
    init_db_with_retry()

    # Pre-warm embedding model in background so user's first query has 0 cold-start delay
    threading.Thread(target=_warmup_embedder, daemon=True).start()

    logger.info("FastAPI backend started successfully.")
    yield
    logger.info("FastAPI backend shutting down.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="RAG-based PDF Chatbot with PyMuPDF, BGE-M3, FAISS, PostgreSQL, and Google Gemini API",
    lifespan=lifespan
)

# Configure CORS - allow all origins including Netlify deployments and localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(health_router, prefix=settings.API_V1_STR)
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(documents_router, prefix=settings.API_V1_STR)
app.include_router(chat_router, prefix=settings.API_V1_STR)
app.include_router(sheets_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {
        "message": "Welcome to AI Document Q&A System API",
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health"
    }
