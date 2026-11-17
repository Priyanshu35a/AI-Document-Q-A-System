import re
from typing import List, Dict, Any

class TextChunker:
    """
    Page-aware text chunker with recursive splitting and overlapping windows.
    Preserves page number metadata for exact RAG citations.
    """

    def __init__(self, chunk_size: int = 600, chunk_overlap: int = 100):
        """
        Args:
            chunk_size: Target chunk size in characters/words (approx tokens).
                        Using character length: 600 tokens ~ 2400 chars.
            chunk_overlap: Overlap in characters/words (approx tokens).
                           100 tokens ~ 400 chars.
        """
        # We approximate 1 token ~ 4 characters in English text
        self.chunk_size = chunk_size * 4
        self.chunk_overlap = chunk_overlap * 4
        if self.chunk_overlap >= self.chunk_size:
            self.chunk_overlap = self.chunk_size // 4

    def _split_text(self, text: str) -> List[str]:
        """
        Splits text into chunks respecting sentence boundaries and overlap.
        """
        if len(text) <= self.chunk_size:
            return [text.strip()] if text.strip() else []

        # Split text into sentences/clauses
        sentences = re.split(r'(?<=[.?!])\s+', text)
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_length = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sentence_len = len(sentence)

            # If a single sentence exceeds chunk size, split by whitespace
            if sentence_len > self.chunk_size:
                words = sentence.split()
                temp_sentence = ""
                for word in words:
                    if len(temp_sentence) + len(word) + 1 <= self.chunk_size:
                        temp_sentence += (" " if temp_sentence else "") + word
                    else:
                        if temp_sentence:
                            chunks.append(temp_sentence)
                        temp_sentence = word
                if temp_sentence:
                    chunks.append(temp_sentence)
                continue

            if current_length + sentence_len + 1 <= self.chunk_size:
                current_chunk.append(sentence)
                current_length += sentence_len + 1
            else:
                if current_chunk:
                    chunk_text = " ".join(current_chunk)
                    chunks.append(chunk_text)

                    # Calculate overlap from previous sentences
                    overlap_chunk = []
                    overlap_len = 0
                    for prev_sentence in reversed(current_chunk):
                        if overlap_len + len(prev_sentence) + 1 <= self.chunk_overlap:
                            overlap_chunk.insert(0, prev_sentence)
                            overlap_len += len(prev_sentence) + 1
                        else:
                            break
                    current_chunk = overlap_chunk
                    current_length = overlap_len

                current_chunk.append(sentence)
                current_length += sentence_len + 1

        if current_chunk:
            chunk_text = " ".join(current_chunk)
            if not chunks or chunk_text != chunks[-1]:
                chunks.append(chunk_text)

        return chunks

    def chunk_pages(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Processes list of extracted pages and produces chunk dictionaries with page numbers.
        
        Args:
            pages: List of {"page_number": int, "text": str}
            
        Returns:
            List of {"page_number": int, "chunk_index": int, "content": str}
        """
        all_chunks: List[Dict[str, Any]] = []
        global_index = 0

        for page in pages:
            page_num = page["page_number"]
            page_text = page["text"]

            page_chunks = self._split_text(page_text)
            for chunk_content in page_chunks:
                clean_content = chunk_content.strip()
                if clean_content:
                    all_chunks.append({
                        "page_number": page_num,
                        "chunk_index": global_index,
                        "content": clean_content
                    })
                    global_index += 1

        return all_chunks
