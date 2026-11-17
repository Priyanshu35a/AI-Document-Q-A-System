import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

import fitz
from app.ingestion.document_parser import DocumentParser, DocumentParsingError

def create_sample_pdf(text: str) -> str:
    temp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    temp_path = temp.name
    temp.close()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    doc.save(temp_path)
    doc.close()
    return temp_path

def create_sample_image() -> str:
    import io
    from PIL import Image
    temp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img = Image.new("RGB", (200, 100), color=(255, 255, 255))
    img.save(temp.name, format="PNG")
    temp.close()
    return temp.name

def test_parse_text_pdf():
    pdf_path = create_sample_pdf("This is a standard textual PDF document for testing RAG extraction.")
    try:
        pages = DocumentParser.parse_document(pdf_path, "sample.pdf")
        assert len(pages) == 1
        assert pages[0]["page_number"] == 1
        assert "standard textual PDF" in pages[0]["text"]
    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

def test_parse_invalid_extension():
    with pytest.raises(DocumentParsingError) as exc_info:
        DocumentParser.parse_document("some_file.docx", "some_file.docx")
    assert "Unsupported file format" in str(exc_info.value)

def test_parse_missing_file():
    with pytest.raises(DocumentParsingError) as exc_info:
        DocumentParser.parse_document("non_existent_file.pdf", "non_existent_file.pdf")
    assert "File not found" in str(exc_info.value)

@patch("app.ingestion.document_parser.llm_vision_provider.extract_text_from_image")
def test_parse_image_document(mock_extract):
    mock_extract.return_value = "INVOICE #1024\nTotal: $149.50\nVendor: Acme Supplies"
    img_path = create_sample_image()
    try:
        pages = DocumentParser.parse_document(img_path, "receipt.png")
        assert len(pages) == 1
        assert pages[0]["page_number"] == 1
        assert "INVOICE #1024" in pages[0]["text"]
        assert "$149.50" in pages[0]["text"]
        mock_extract.assert_called_once()
    finally:
        if os.path.exists(img_path):
            os.remove(img_path)
