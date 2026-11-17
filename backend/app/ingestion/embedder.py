import logging
from typing import List, Optional
import numpy as np
from app.core.config import settings

logger = logging.getLogger(__name__)

class Embedder:
    """
    Embedding manager utilizing SentenceTransformer (BGE-M3 by default).
    Runs locally and produces L2-normalized float32 embeddings for FAISS.
    Uses lazy initialization to avoid blocking imports or server startup.
    """
    _instance: Optional["Embedder"] = None
    _model = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Embedder, cls).__new__(cls)
        return cls._instance

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME

    def _ensure_model_loaded(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self.model_name}...")
            try:
                self._model = SentenceTransformer(self.model_name)
                logger.info(f"Loaded embedding model {self.model_name} successfully.")
            except Exception as e:
                logger.error(f"Failed to load primary embedding model '{self.model_name}': {e}")
                fallback = "sentence-transformers/all-MiniLM-L6-v2"
                logger.info(f"Attempting fallback to '{fallback}'...")
                self._model = SentenceTransformer(fallback)
                self.model_name = fallback

    @property
    def dimension(self) -> int:
        """Returns embedding dimension size."""
        self._ensure_model_loaded()
        if hasattr(self._model, "get_embedding_dimension"):
            return self._model.get_embedding_dimension()
        return self._model.get_sentence_embedding_dimension()

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """
        Generates normalized dense embeddings for a list of text strings.
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        self._ensure_model_loaded()
        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True
        )
        return np.array(embeddings, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """
        Generates normalized embedding for a single search query.
        """
        self._ensure_model_loaded()
        embeddings = self._model.encode(
            [query],
            show_progress_bar=False,
            normalize_embeddings=True
        )
        return np.array(embeddings, dtype=np.float32)

embedder = Embedder()
