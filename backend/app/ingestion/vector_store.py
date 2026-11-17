import os
import threading
import logging
from typing import List, Tuple, Optional
import numpy as np
import faiss
from app.core.config import settings

logger = logging.getLogger(__name__)

class FAISSVectorStore:
    """
    Thread-safe FAISS vector index manager using IndexIDMap2 and IndexFlatIP.
    Supports cosine similarity search via normalized embeddings, explicit ID assignment,
    ID removal, and disk persistence.
    """

    def __init__(self, index_path: Optional[str] = None, dimension: Optional[int] = None):
        self._lock = threading.Lock()
        self.index_path = index_path or settings.FAISS_INDEX_PATH
        if dimension is None:
            try:
                from app.ingestion.embedder import embedder
                self.dimension = embedder.dimension
            except Exception:
                self.dimension = 384
        else:
            self.dimension = dimension
        self.index: Optional[faiss.Index] = None
        self._load_or_create_index()

    def _load_or_create_index(self):
        """Loads index from disk or creates a new one if not found or dimension mismatch."""
        os.makedirs(os.path.dirname(self.index_path) or ".", exist_ok=True)
        if os.path.exists(self.index_path):
            try:
                logger.info(f"Loading FAISS index from {self.index_path}...")
                loaded_index = faiss.read_index(self.index_path)
                if loaded_index.d == self.dimension:
                    self.index = loaded_index
                    logger.info(f"FAISS index loaded. Total vectors: {self.index.ntotal}")
                    return
                else:
                    logger.warning(
                        f"Existing FAISS index dimension {loaded_index.d} does not match expected {self.dimension}. "
                        "Recreating index for updated embedding model."
                    )
            except Exception as e:
                logger.error(f"Failed to read existing FAISS index: {e}. Creating new index.")

        logger.info(f"Creating new FAISS IndexIDMap2 with dimension {self.dimension}...")
        sub_index = faiss.IndexFlatIP(self.dimension)
        self.index = faiss.IndexIDMap2(sub_index)
        self._save_index()

    def _save_index(self):
        """Persists FAISS index to disk."""
        try:
            faiss.write_index(self.index, self.index_path)
            logger.info(f"FAISS index saved to {self.index_path} ({self.index.ntotal} vectors).")
        except Exception as e:
            logger.error(f"Failed to write FAISS index to disk: {e}")

    def add_vectors(self, vectors: np.ndarray, ids: List[int]):
        """
        Adds normalized vectors with corresponding integer IDs into the index.
        """
        if len(ids) == 0:
            return

        with self._lock:
            id_array = np.array(ids, dtype=np.int64)
            if self.index.d != vectors.shape[1]:
                logger.warning(
                    f"Dimension mismatch: Index has {self.index.d} but vectors have {vectors.shape[1]}. Resetting index."
                )
                self.dimension = vectors.shape[1]
                sub_index = faiss.IndexFlatIP(self.dimension)
                self.index = faiss.IndexIDMap2(sub_index)

            self.index.add_with_ids(vectors, id_array)
            self._save_index()

    def remove_vectors(self, ids: List[int]):
        """
        Removes vectors from the index by their IDs.
        """
        if not ids:
            return

        with self._lock:
            try:
                id_array = np.array(ids, dtype=np.int64)
                self.index.remove_ids(id_array)
                self._save_index()
                logger.info(f"Removed {len(ids)} vectors from FAISS index.")
            except Exception as e:
                logger.error(f"Error removing IDs from FAISS: {e}")

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> Tuple[List[int], List[float]]:
        """
        Searches the index for the top-k most similar vectors.
        """
        with self._lock:
            if not self.index or self.index.ntotal == 0:
                return [], []

            if self.index.d != query_vector.shape[1]:
                logger.warning(f"Search dimension mismatch: Index has {self.index.d}, query has {query_vector.shape[1]}")
                return [], []

            effective_k = min(top_k, self.index.ntotal)
            distances, indices = self.index.search(query_vector, effective_k)

            retrieved_ids = [int(idx) for idx in indices[0] if idx != -1]
            scores = [float(dist) for dist in distances[0] if dist != -1.0]

            return retrieved_ids, scores

    def reset(self, dimension: Optional[int] = None):
        """Resets and recreates an empty index with specified or current dimension."""
        with self._lock:
            if dimension:
                self.dimension = dimension
            sub_index = faiss.IndexFlatIP(self.dimension)
            self.index = faiss.IndexIDMap2(sub_index)
            self._save_index()
            logger.info(f"FAISS index reset with dimension {self.dimension}.")

    @property
    def total_vectors(self) -> int:
        with self._lock:
            return self.index.ntotal if self.index else 0

# Default global instance
vector_store = FAISSVectorStore()
