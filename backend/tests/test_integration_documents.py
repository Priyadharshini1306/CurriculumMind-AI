"""Docling extraction of every supported format from real sample files (integration: loads Docling/OCR models)."""
from pathlib import Path

import pytest

from app.services.document_service import DocumentError, extract_text

pytestmark = pytest.mark.integration
SAMPLE = Path(__file__).resolve().parents[2] / "sample"


@pytest.mark.parametrize("name", ["java_syllabus.txt", "java_syllabus.docx", "java_syllabus.pptx", "java_syllabus.pdf"])
def test_text_based_formats(name):
    text = extract_text(SAMPLE / name)
    assert "Java Programming" in text and "Unit 1" in text


def test_image_ocr_reads_scanned_syllabus():
    text = extract_text(SAMPLE / "java_syllabus_scan.png").lower()
    # OCR is imperfect; require the key content, not an exact transcript
    for word in ("java programming", "collections", "inheritance"):
        assert word in text


def test_corrupt_document_is_a_clean_error(tmp_path):
    bad = tmp_path / "broken.docx"
    bad.write_bytes(b"PK\x03\x04 this is not really a docx")
    with pytest.raises(DocumentError):
        extract_text(bad)
