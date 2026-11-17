import os
import re
import mimetypes
import logging
from typing import List, Dict, Any

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from app.core.config import settings
from app.generation.llm_provider import GeminiLLMProvider

logger = logging.getLogger(__name__)

llm_vision_provider = GeminiLLMProvider(
    api_key=settings.GEMINI_API_KEY,
    model_name=settings.GEMINI_MODEL
)

class DocumentParsingError(Exception):
    """Custom exception raised when document/image parsing fails."""
    pass

class DocumentParser:
    """
    Unified multi-modal document parser supporting:
    - Standard text PDFs (PyMuPDF fast extraction)
    - Scanned PDFs & image-based PDF pages (PyMuPDF pixmap rendering + Gemini Vision OCR)
    - Direct image uploads: notes, bill photos, receipts (.png, .jpg, .jpeg, .webp)
    """

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
    PDF_EXTENSIONS = {".pdf"}

    @classmethod
    def parse_document(cls, file_path: str, filename: str) -> List[Dict[str, Any]]:
        """
        Parses a document or image file and returns page-attributed text chunks.
        
        Args:
            file_path: Absolute or relative path to file on disk.
            filename: Original uploaded filename with extension.
            
        Returns:
            List[Dict[str, Any]]: [{"page_number": int, "text": str}]
        """
        ext = os.path.splitext(filename)[1].lower()
        if ext not in cls.PDF_EXTENSIONS and ext not in cls.IMAGE_EXTENSIONS:
            raise DocumentParsingError(
                f"Unsupported file format '{ext}'. Allowed: .pdf, .png, .jpg, .jpeg, .webp"
            )

        if not os.path.exists(file_path):
            raise DocumentParsingError(f"File not found: {file_path}")

        if ext in cls.PDF_EXTENSIONS:
            return cls._parse_pdf(file_path)
        else:
            return cls._parse_image(file_path, filename)

    @classmethod
    def _parse_pdf(cls, file_path: str) -> List[Dict[str, Any]]:
        try:
            doc = fitz.open(file_path)
        except Exception as e:
            raise DocumentParsingError(f"Could not open PDF file: {str(e)}")

        if doc.is_encrypted:
            raise DocumentParsingError("Encrypted or password-protected PDFs are not supported.")

        page_count = len(doc)
        if page_count == 0:
            raise DocumentParsingError("PDF file is empty (contains 0 pages).")

        # Step 1: Scan for readable native digital text layer across pages
        native_pages = []
        total_readable_chars = 0
        pages_with_readable_text = 0

        for page_idx in range(page_count):
            page_num = page_idx + 1
            try:
                page = doc.load_page(page_idx)
                raw_text = page.get_text("text") or ""
                cleaned = " ".join(raw_text.split())
                # Verify that the text consists of readable alphanumeric words rather than font-obfuscated dingbats
                alphanumeric_count = len(re.findall(r'[a-zA-Z0-9]', cleaned))
                is_readable = (alphanumeric_count >= 25) and ((alphanumeric_count / max(len(cleaned), 1)) >= 0.35)

                native_pages.append((page_num, cleaned, is_readable))
                if is_readable:
                    total_readable_chars += alphanumeric_count
                    pages_with_readable_text += 1
            except Exception as e:
                logger.warning(f"Error reading native text on page {page_num}: {e}")
                native_pages.append((page_num, "", False))

        # PDF is considered digital only if its text layer is genuinely readable
        is_digital_pdf = (total_readable_chars >= 200) and (page_count > 0 and (pages_with_readable_text / page_count) >= 0.20)

        extracted_pages: List[Dict[str, Any]] = []

        if is_digital_pdf:
            logger.info(
                f"PDF has readable native text layer ({pages_with_readable_text}/{page_count} readable pages, {total_readable_chars} chars). "
                "Using fast digital extraction."
            )
            for page_num, text, is_readable in native_pages:
                if is_readable:
                    extracted_pages.append({
                        "page_number": page_num,
                        "text": text
                    })
        else:
            logger.info(
                f"PDF has no readable text ({total_readable_chars} alphanumeric chars across {page_count} pages; "
                "scanned or font-obfuscated encoding detected). Performing Gemini Vision OCR..."
            )
            max_ocr_pages = min(page_count, 35)
            for page_idx in range(max_ocr_pages):
                page_num = page_idx + 1
                try:
                    page = doc.load_page(page_idx)
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("png")
                    ocr_text = llm_vision_provider.extract_text_from_image(img_bytes, mime_type="image/png")
                    if ocr_text and ocr_text.strip():
                        extracted_pages.append({
                            "page_number": page_num,
                            "text": ocr_text.strip()
                        })
                except Exception as ocr_err:
                    logger.warning(f"OCR failed for page {page_num}: {ocr_err}")

        doc.close()

        if not extracted_pages:
            raise DocumentParsingError(
                "Could not extract any readable text or visual content from the PDF."
            )

        return extracted_pages

    @classmethod
    def _parse_image(cls, file_path: str, filename: str) -> List[Dict[str, Any]]:
        """Extracts text from direct image uploads (bill photos, receipts, notes)."""
        ext = os.path.splitext(filename)[1].lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp"
        }
        mime_type = mime_map.get(ext, "image/png")

        try:
            with open(file_path, "rb") as f:
                image_bytes = f.read()

            if not image_bytes:
                raise DocumentParsingError("Uploaded image file is empty.")

            logger.info(f"Running Gemini Multimodal OCR on image '{filename}' ({len(image_bytes)} bytes)...")
            ocr_text = llm_vision_provider.extract_text_from_image(image_bytes, mime_type=mime_type)

            if not ocr_text or not ocr_text.strip():
                raise DocumentParsingError("No text or content could be identified in the uploaded image.")

            return [{
                "page_number": 1,
                "text": ocr_text.strip()
            }]
        except DocumentParsingError:
            raise
        except Exception as e:
            raise DocumentParsingError(f"Failed to process image document: {str(e)}")
