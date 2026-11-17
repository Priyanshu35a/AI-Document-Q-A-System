import pytest
from app.ingestion.chunker import TextChunker

def test_chunker_preserves_page_numbers():
    chunker = TextChunker(chunk_size=50, chunk_overlap=10)
    pages = [
        {"page_number": 1, "text": "This is the first page of the document with important introductory details."},
        {"page_number": 2, "text": "This is the second page discussing experimental methodology and analysis."}
    ]

    chunks = chunker.chunk_pages(pages)

    assert len(chunks) >= 2
    assert chunks[0]["page_number"] == 1
    assert chunks[0]["chunk_index"] == 0
    assert "first page" in chunks[0]["content"]

    page_2_chunk = next(c for c in chunks if c["page_number"] == 2)
    assert page_2_chunk is not None
    assert "second page" in page_2_chunk["content"]

def test_chunker_handles_long_text_with_overlap():
    chunker = TextChunker(chunk_size=30, chunk_overlap=10)
    # Long repetitive text
    sentence = "Artificial intelligence enables automated reasoning across vast textual datasets. "
    long_text = sentence * 10
    pages = [{"page_number": 1, "text": long_text}]

    chunks = chunker.chunk_pages(pages)

    assert len(chunks) > 1
    # Check that all chunks from this page have page_number 1
    for c in chunks:
        assert c["page_number"] == 1
        assert len(c["content"]) > 0

def test_chunker_empty_and_whitespace():
    chunker = TextChunker(chunk_size=50, chunk_overlap=10)
    pages = [
        {"page_number": 1, "text": ""},
        {"page_number": 2, "text": "    \n\n   "},
        {"page_number": 3, "text": "Valid text on page three."}
    ]

    chunks = chunker.chunk_pages(pages)
    assert len(chunks) == 1
    assert chunks[0]["page_number"] == 3
    assert chunks[0]["content"] == "Valid text on page three."
