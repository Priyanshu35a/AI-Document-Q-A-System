import pytest
from scripts.eval_rag import (
    calculate_context_relevance,
    calculate_faithfulness,
    calculate_answer_relevance
)

def test_context_relevance_metric():
    chunks = [
        {"content": "Brian Kernighan and Dennis Ritchie wrote The C Programming Language."},
        {"content": "YouTube playlist for C-programming practice and NPTEL lectures."}
    ]
    keywords = ["kernighan", "ritchie", "c-programming", "youtube"]
    score = calculate_context_relevance(chunks, keywords)
    assert score == 1.0

    partial_keywords = ["kernighan", "python", "docker", "kubernetes"]
    partial_score = calculate_context_relevance(chunks, partial_keywords)
    assert 0.2 <= partial_score <= 0.3

def test_faithfulness_metric():
    chunks = [
        {"content": "Computer Organization and Design by David Patterson and John Hennessy fifth edition."}
    ]
    grounded_answer = "The recommended book is Computer Organization and Design by Patterson and Hennessy."
    score = calculate_faithfulness(grounded_answer, chunks)
    assert score >= 0.8

    hallucinated_answer = "You should study quantum cryptography with Professor Albert Einstein on Neptune."
    low_score = calculate_faithfulness(hallucinated_answer, chunks)
    assert low_score <= 0.3

import numpy as np
from unittest.mock import patch

def test_answer_relevance_metric():
    question = "What should I learn first in C programming?"
    answer = "In C programming, start with basic syntax, data types, and pointers."
    
    # Mock embeddings to avoid loading heavy models during fast test execution
    v1 = np.array([0.8, 0.6])
    v2 = np.array([0.85, 0.52])
    
    with patch("scripts.eval_rag.embedder.embed_query", side_effect=[v1, v2]):
        score = calculate_answer_relevance(question, answer)
        assert score >= 0.5

