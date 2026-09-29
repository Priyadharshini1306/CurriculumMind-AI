import pytest

from app.services import document_service as d


def test_text_extraction(tmp_path):
    p = tmp_path / "s.txt"
    p.write_text("Unit 1: Java Basics", encoding="utf-8")
    assert d.extract_text(p) == "Unit 1: Java Basics"


def test_empty_document_rejected(tmp_path):
    p = tmp_path / "e.txt"
    p.write_text("   \n", encoding="utf-8")
    with pytest.raises(d.DocumentError):
        d.extract_text(p)


def test_signature_check():
    assert d.validate_signature(".pdf", b"%PDF-1.7")
    assert not d.validate_signature(".pdf", b"MZ\x90\x00")
    assert d.validate_signature(".txt", b"anything")
