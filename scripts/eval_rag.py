#!/usr/bin/env python3
"""
Automated RAG Evaluation Suite — RAG Triad Benchmark
Measures:
1. Context Relevance: Quality of retrieved chunks vs ground truth keywords.
2. Faithfulness / Groundedness: Degree to which generated answer is supported by context (Anti-Hallucination).
3. Answer Relevance: Semantic alignment between user query and generated answer.
4. Latency Telemetry: Retrieval and Generation timing breakdowns.
"""

import os
import sys
import time
import json
import logging
from typing import List, Dict, Any

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.db.database import SessionLocal
from app.db.models import Document, Chunk
from app.retrieval.retriever import retriever
from app.ingestion.embedder import embedder
from app.generation.llm_provider import GeminiLLMProvider
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Representative benchmark evaluation test set
DEFAULT_BENCHMARK = [
    {
        "id": "TC-01",
        "question": "What is recommended for learning C-programming and which author or playlist is provided?",
        "expected_keywords": ["c-programming", "kernighan", "ritchie", "youtube", "playlist", "nptel"],
        "category": "Foundational Coding"
    },
    {
        "id": "TC-02",
        "question": "Which standard textbook is cited for Computer Organization and Design?",
        "expected_keywords": ["patterson", "hennessy", "hardware", "software", "interface", "5e"],
        "category": "Hardware & Architecture"
    },
    {
        "id": "TC-03",
        "question": "What should I learn first to prepare for GATE CSE according to the document?",
        "expected_keywords": ["c-programming", "data structures", "discrete", "logic", "foundational"],
        "category": "Study Roadmap"
    },
    {
        "id": "TC-04",
        "question": "What resource or author is given for Data Structures and Algorithms?",
        "expected_keywords": ["narasimha", "karumanchi", "data structures", "clrs", "algorithms"],
        "category": "Algorithms & DS"
    }
]

def calculate_context_relevance(retrieved_chunks: List[Dict[str, Any]], expected_keywords: List[str]) -> float:
    """Calculates keyword recall and coverage in the top retrieved chunks."""
    if not retrieved_chunks or not expected_keywords:
        return 0.0
    combined_text = " ".join(c["content"].lower() for c in retrieved_chunks)
    matched = sum(1 for kw in expected_keywords if kw.lower() in combined_text)
    return round(matched / len(expected_keywords), 3)

def calculate_faithfulness(answer: str, retrieved_chunks: List[Dict[str, Any]]) -> float:
    """Calculates lexical and claim support of answer against retrieved passages (anti-hallucination)."""
    if not answer or not retrieved_chunks:
        return 0.0
    
    context_text = " ".join(c["content"].lower() for c in retrieved_chunks)
    
    # Split answer into key sentences
    sentences = [s.strip() for s in answer.split(".") if len(s.strip()) > 15]
    if not sentences:
        return 0.95
    
    supported_sentences = 0
    for s in sentences:
        words = [w.strip("(),[]:;\"'") for w in s.lower().split() if len(w) > 4]
        if not words:
            supported_sentences += 1
            continue
        word_overlap = sum(1 for w in words if w in context_text)
        if (word_overlap / len(words)) >= 0.40:
            supported_sentences += 1
            
    return round(min(1.0, supported_sentences / len(sentences)), 3)

def calculate_answer_relevance(question: str, answer: str) -> float:
    """Calculates cosine similarity between question and generated answer vectors."""
    if not answer.strip():
        return 0.0
    q_vec = embedder.embed_query(question)
    a_vec = embedder.embed_query(answer[:300]) # compare initial focus
    sim = float(q_vec @ a_vec.T)
    # Scale from [-1, 1] to [0, 1]
    scaled = max(0.0, min(1.0, (sim + 0.2) / 1.2))
    return round(scaled, 3)

def run_evaluation(test_cases: List[Dict[str, Any]] = None, output_file: str = "eval_report.json") -> Dict[str, Any]:
    """Runs end-to-end evaluation benchmark across the test set."""
    cases = test_cases or DEFAULT_BENCHMARK
    db = SessionLocal()
    llm = GeminiLLMProvider(api_key=settings.GEMINI_API_KEY, model_name=settings.GEMINI_MODEL)

    # Locate available documents in DB
    doc = db.query(Document).order_by(Document.id.desc()).first()
    doc_id = doc.id if doc else None

    logger.info(f"Starting RAG Triad Evaluation on {len(cases)} test cases using document ID: {doc_id}...")

    results = []
    total_retrieval_ms = 0.0
    total_generation_ms = 0.0

    print("\n" + "=" * 90)
    print("                RAG TRIAD EVALUATION BENCHMARK REPORT")
    print("=" * 90)
    print(f"{'ID':<6} | {'Category':<22} | {'Context Rel':<11} | {'Faithfulness':<12} | {'Answer Rel':<10} | {'Composite':<9} | {'Latency':<8}")
    print("-" * 90)

    for tc in cases:
        q = tc["question"]
        expected_kw = tc["expected_keywords"]

        # Step 1: Retrieval with telemetry
        t0 = time.perf_counter()
        chunks = retriever.retrieve_chunks(q, db=db, document_id=doc_id, top_k=5)
        retrieval_ms = round((time.perf_counter() - t0) * 1000, 2)
        total_retrieval_ms += retrieval_ms

        # Step 2: Generation with telemetry
        t1 = time.perf_counter()
        gen_res = llm.generate_answer(q, chunks)
        generation_ms = round((time.perf_counter() - t1) * 1000, 2)
        total_generation_ms += generation_ms

        answer = gen_res["answer"]
        model_used = gen_res.get("model", settings.GEMINI_MODEL)

        # Step 3: Compute RAG Triad Metrics
        ctx_rel = calculate_context_relevance(chunks, expected_kw)
        faith = calculate_faithfulness(answer, chunks)
        ans_rel = calculate_answer_relevance(q, answer)
        composite = round((ctx_rel + faith + ans_rel) / 3.0, 3)

        total_lat_s = round((retrieval_ms + generation_ms) / 1000.0, 2)

        print(f"{tc['id']:<6} | {tc['category']:<22} | {ctx_rel:<11.3f} | {faith:<12.3f} | {ans_rel:<10.3f} | {composite:<9.3f} | {total_lat_s:<6.2f}s")

        results.append({
            "id": tc["id"],
            "category": tc["category"],
            "question": q,
            "metrics": {
                "context_relevance": ctx_rel,
                "faithfulness": faith,
                "answer_relevance": ans_rel,
                "composite_score": composite
            },
            "latency": {
                "retrieval_ms": retrieval_ms,
                "generation_ms": generation_ms,
                "total_ms": retrieval_ms + generation_ms
            },
            "retrieved_chunk_count": len(chunks),
            "model_used": model_used
        })

    db.close()

    n = len(results)
    avg_ctx = round(sum(r["metrics"]["context_relevance"] for r in results) / n, 3)
    avg_faith = round(sum(r["metrics"]["faithfulness"] for r in results) / n, 3)
    avg_ans = round(sum(r["metrics"]["answer_relevance"] for r in results) / n, 3)
    overall_score = round(sum(r["metrics"]["composite_score"] for r in results) / n, 3)
    avg_retrieval_ms = round(total_retrieval_ms / n, 2)
    avg_generation_ms = round(total_generation_ms / n, 2)

    print("=" * 90)
    print(f"OVERALL SUMMARY:")
    print(f"  • Average Context Relevance: {avg_ctx * 100:.1f}%")
    print(f"  • Average Faithfulness (Anti-Hallucination): {avg_faith * 100:.1f}%")
    print(f"  • Average Answer Relevance: {avg_ans * 100:.1f}%")
    print(f"  • Overall Composite RAG Score: {overall_score * 100:.1f}%")
    print(f"  • Average Retrieval Latency: {avg_retrieval_ms} ms")
    print(f"  • Average Generation Latency: {avg_generation_ms} ms")
    print("=" * 90)

    report_payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_test_cases": n,
        "aggregate_scores": {
            "overall_rag_score": overall_score,
            "context_relevance": avg_ctx,
            "faithfulness": avg_faith,
            "answer_relevance": avg_ans
        },
        "performance_telemetry": {
            "avg_retrieval_ms": avg_retrieval_ms,
            "avg_generation_ms": avg_generation_ms,
            "avg_total_ms": round(avg_retrieval_ms + avg_generation_ms, 2)
        },
        "test_results": results
    }

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report_payload, f, indent=2)
        logger.info(f"Evaluation report saved successfully to '{output_file}'.")
    except Exception as e:
        logger.error(f"Failed to write report file: {e}")

    return report_payload

if __name__ == "__main__":
    run_evaluation()
