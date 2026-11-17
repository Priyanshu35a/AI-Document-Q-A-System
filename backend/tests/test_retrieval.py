import os
import tempfile
import numpy as np
import pytest
from app.ingestion.vector_store import FAISSVectorStore

def test_faiss_vector_store_operations():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_index_path = os.path.join(tmpdir, "test_index.faiss")
        dim = 16

        store = FAISSVectorStore(index_path=test_index_path, dimension=dim)

        # Generate 5 random normalized vectors
        np.random.seed(42)
        raw_vecs = np.random.randn(5, dim).astype(np.float32)
        norms = np.linalg.norm(raw_vecs, axis=1, keepdims=True)
        norm_vecs = raw_vecs / norms

        vector_ids = [101, 102, 103, 104, 105]
        store.add_vectors(norm_vecs, vector_ids)

        assert store.total_vectors == 5

        # Query with exact first vector: similarity score should be ~1.0
        query_vec = norm_vecs[0:1]
        retrieved_ids, scores = store.search(query_vec, top_k=3)

        assert len(retrieved_ids) == 3
        assert len(scores) == 3
        assert retrieved_ids[0] == 101
        assert pytest.approx(scores[0], abs=1e-4) == 1.0

        # Remove vector 101
        store.remove_vectors([101])
        assert store.total_vectors == 4

        # Search again: 101 must not appear
        retrieved_ids_after, _ = store.search(query_vec, top_k=3)
        assert 101 not in retrieved_ids_after

        # Verify disk persistence
        assert os.path.exists(test_index_path)
        reloaded_store = FAISSVectorStore(index_path=test_index_path, dimension=dim)
        assert reloaded_store.total_vectors == 4
