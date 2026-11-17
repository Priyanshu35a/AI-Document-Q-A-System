import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

_backend_dir = Path(__file__).resolve().parent.parent.parent
_root_dir = _backend_dir.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_root_dir / ".env"), str(_backend_dir / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    PROJECT_NAME: str = "AI Document Q&A System"
    API_V1_STR: str = "/api"

    # LLM Settings
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"

    # Database Settings
    POSTGRES_USER: str = "raguser"
    POSTGRES_PASSWORD: str = "ragpassword"
    POSTGRES_DB: str = "ragdb"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: Optional[str] = None

    # Embedding and FAISS
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    FAISS_INDEX_PATH: str = "faiss_index/index.faiss"
    UPLOAD_DIR: str = "uploads"

    # Chunking & Retrieval
    CHUNK_SIZE: int = 600
    CHUNK_OVERLAP: int = 100
    TOP_K: int = 5

    @property
    def effective_embedding_model(self) -> str:
        # On Render Free Tier (512MB RAM limit), default to zero-RAM Gemini API embeddings
        if os.getenv("RENDER"):
            return "gemini-embedding-001"
        return self.EMBEDDING_MODEL_NAME

    def get_database_url(self) -> str:
        if self.DATABASE_URL and self.DATABASE_URL.strip():
            # If default docker-compose postgres URL is passed on Render or standalone, use SQLite
            if "postgres:5432" in self.DATABASE_URL and (os.getenv("RENDER") or not os.path.exists("/.dockerenv")):
                return "sqlite:///./rag.db"
            return self.DATABASE_URL
        if os.getenv("RENDER") or not os.path.exists("/.dockerenv"):
            return "sqlite:///./rag.db"
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

settings = Settings()
