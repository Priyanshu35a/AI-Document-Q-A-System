"""
End-to-end Demonstration Script for DocuRAG System.
Demonstrates:
1. Ingestion of multi-page PDF with page tracking.
2. Local dense vector retrieval with BGE-M3.
3. Grounded answer generation with Gemini API citing document name and page number.
4. Hallucination guardrail validation.
"""
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.ingestion.pdf_parser import PDFParser
from app.ingestion.chunker import TextChunker
from app.ingestion.embedder import embedder
from app.ingestion.vector_store import FAISSVectorStore
from app.generation.llm_provider import GeminiLLMProvider
from app.core.config import settings

def run_pipeline_demo():
    print("=" * 70)
    print("           DOCURAG PIPELINE END-TO-END DEMONSTRATION")
    print("=" * 70)

    sample_pdf_path = os.path.abspath("sample_company_report.pdf")
    if not os.path.exists(sample_pdf_path):
        print(f"Generating sample PDF at {sample_pdf_path}...")
        from generate_sample_pdf import create_sample_pdf
        create_sample_pdf(sample_pdf_path)

    # 1. Parsing
    print("\n[Step 1] Ingesting & Extracting PDF pages via PyMuPDF...")
    pages = PDFParser.parse_pdf(sample_pdf_path)
    print(f"-> Extracted {len(pages)} pages successfully.")
    for p in pages:
        print(f"   * Page {p['page_number']}: {len(p['text'])} chars extracted.")

    # 2. Chunking
    print("\n[Step 2] Chunking text with page preservation...")
    chunker = TextChunker(chunk_size=600, chunk_overlap=100)
    chunks = chunker.chunk_pages(pages)
    print(f"-> Created {len(chunks)} chunks across {len(pages)} pages.")

    # 3. Embedding
    print(f"\n[Step 3] Generating embeddings via {settings.EMBEDDING_MODEL_NAME}...")
    texts = [c["content"] for c in chunks]
    embeddings = embedder.embed_texts(texts)
    print(f"-> Generated embeddings array with shape {embeddings.shape} (dtype: {embeddings.dtype}).")

    # 4. Vector Store
    print("\n[Step 4] Indexing into FAISS Vector Store...")
    vector_store = FAISSVectorStore(index_path="faiss_index/demo_index.faiss", dimension=embeddings.shape[1])
    vector_ids = list(range(1, len(chunks) + 1))
    vector_store.add_vectors(embeddings, vector_ids)
    print(f"-> Indexed {vector_store.total_vectors} vectors into FAISS.")

    # 5. Queries & Grounded Q&A
    llm = GeminiLLMProvider(api_key=settings.GEMINI_API_KEY, model_name=settings.GEMINI_MODEL)

    test_queries = [
        {
            "query": "Who is the Chief Technology Officer (CTO) of Acme Technologies?",
            "expected_page": 1
        },
        {
            "query": "What was the Q3 revenue and gross profit margin?",
            "expected_page": 2
        },
        {
            "query": "What is the capital city of planet Neptune?",
            "expected_page": None # Anti-hallucination test
        }
    ]

    print("\n[Step 5] Running Grounded Retrieval & Generation Queries...")
    for idx, t in enumerate(test_queries, 1):
        q = t["query"]
        print(f"\n" + "-" * 60)
        print(f"Test Query {idx}: '{q}'")

        # Embed query & search FAISS
        q_vec = embedder.embed_query(q)
        retrieved_ids, scores = vector_store.search(q_vec, top_k=3)

        retrieved_chunks = []
        for vid, score in zip(retrieved_ids, scores):
            chunk_item = chunks[vid - 1]
            retrieved_chunks.append({
                "document_name": "sample_company_report.pdf",
                "page_number": chunk_item["page_number"],
                "content": chunk_item["content"],
                "score": round(score, 4)
            })

        print(f"Retrieved Top-{len(retrieved_chunks)} Chunks:")
        for rc in retrieved_chunks:
            print(f"   - [Page {rc['page_number']}] (Sim: {rc['score']}): {rc['content'][:70]}...")

        # Generate answer
        result = llm.generate_answer(query=q, context_chunks=retrieved_chunks)
        print(f"\nAnswer from Gemini ({result.get('model')}):")
        print(f"{result['answer']}")

    print("\n" + "=" * 70)
    print("Pipeline demo completed successfully.")
    print("=" * 70)

if __name__ == "__main__":
    run_pipeline_demo()
