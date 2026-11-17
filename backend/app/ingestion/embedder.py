import os
# Force PyTorch and linear algebra libraries to single-thread mode to fit within 512MB RAM on free cloud tiers
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["TORCH_NUM_THREADS"] = "1"

import logging
from typing import List, Optional
import numpy as np
from app.core.config import settings

logger = logging.getLogger(__name__)

class Embedder:
    """
    Embedding manager supporting local SentenceTransformers (all-MiniLM-L6-v2)
    and zero-RAM cloud embeddings (gemini-embedding-001).
    Uses lazy initialization to ensure instant server boot and zero-memory startup.
    """
    _instance: Optional["Embedder"] = None
    _model = None
    _client = None
    _provider = "local"
    _dimension: Optional[int] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Embedder, cls).__new__(cls)
        return cls._instance

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.effective_embedding_model

    def _ensure_gemini_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)

    def _ensure_model_loaded(self):
        if "gemini" in self.model_name.lower():
            self._provider = "gemini"
            self._dimension = 3072
            self._ensure_gemini_client()
            return

        if self._model is None and self._provider == "local":
            try:
                import torch
                torch.set_num_threads(1)
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading embedding model: {self.model_name} (low-RAM single-thread mode)...")
                self._model = SentenceTransformer(self.model_name)
                logger.info(f"Loaded embedding model {self.model_name} successfully.")
                self._provider = "local"
            except (MemoryError, Exception) as e:
                logger.warning(
                    f"Local embedding model unavailable ({e}). "
                    "Switching to Gemini API embedding (gemini-embedding-001, 0MB RAM usage)..."
                )
                self._provider = "gemini"
                self.model_name = "gemini-embedding-001"
                self._dimension = 3072
                self._ensure_gemini_client()

    @property
    def dimension(self) -> int:
        """Returns embedding dimension size."""
        if self._dimension:
            return self._dimension
        self._ensure_model_loaded()
        if self._provider == "gemini":
            return 3072
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

        if self._provider == "gemini":
            self._ensure_gemini_client()
            vectors = []
            for t in texts:
                res = self._client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=t
                )
                vectors.append(res.embeddings[0].values)
            arr = np.array(vectors, dtype=np.float32)
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            return arr / norms

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

        if self._provider == "gemini":
            self._ensure_gemini_client()
            res = self._client.models.embed_content(
                model="gemini-embedding-001",
                contents=query
            )
            vec = np.array(res.embeddings[0].values, dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            return vec

        embeddings = self._model.encode(
            [query],
            show_progress_bar=False,
            normalize_embeddings=True
        )
        return np.array(embeddings, dtype=np.float32)

embedder = Embedder()
