import os
from typing import List, Dict, Any

try:
    import pymupdf as fitz
except ImportError:
    import fitz

class PDFParsingError(Exception):
    """Custom exception raised when PDF parsing fails."""
    pass

class PDFParser:
    """Extracts text from PDF documents page by page using PyMuPDF (fitz)."""

    @staticmethod
    def parse_pdf(file_path: str) -> List[Dict[str, Any]]:
        """
        Parses a PDF file and returns a list of dictionaries with page_number and extracted text.
        
        Args:
            file_path: Path to the local PDF file.
            
        Returns:
            List[Dict[str, Any]]: List of dicts, e.g. [{"page_number": 1, "text": "..."}]
        """
        if not os.path.exists(file_path):
            raise PDFParsingError(f"File not found at path: {file_path}")

        try:
            doc = fitz.open(file_path)
        except Exception as e:
            raise PDFParsingError(f"Failed to open PDF document: {str(e)}")

        if doc.is_encrypted:
            raise PDFParsingError("Encrypted or password-protected PDFs are not supported.")

        page_count = len(doc)
        if page_count == 0:
            raise PDFParsingError("PDF file is empty (contains 0 pages).")

        extracted_pages: List[Dict[str, Any]] = []
        total_text_length = 0

        for page_idx in range(page_count):
            page_num = page_idx + 1  # 1-indexed
            try:
                page = doc.load_page(page_idx)
                raw_text = page.get_text("text") or ""
                # Normalize line breaks and spaces
                cleaned_text = " ".join(raw_text.split())
                if cleaned_text:
                    total_text_length += len(cleaned_text)
                    extracted_pages.append({
                        "page_number": page_num,
                        "text": cleaned_text
                    })
            except Exception as e:
                # Log and continue with next page if one page fails
                continue

        doc.close()

        if total_text_length == 0:
            raise PDFParsingError(
                "No extractable text found in PDF. The document may be scanned images or empty."
            )

        return extracted_pages
