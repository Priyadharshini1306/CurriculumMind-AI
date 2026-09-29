"""Document text extraction with Docling.

  * DOCX / PPTX / text  : direct extraction (no OCR involved).
  * PDF                 : the embedded text layer is read directly with pdfium (well under a second). Only when that
                          yields too little text (a scan) is OCR used. Docling's layout models take minutes per PDF on a
                          CPU, which made uploads look frozen, so they are not used for text PDFs.
  * Images              : OCR.
OCR engines are tried in order (RapidOCR, then EasyOCR) because each downloads its own models on first use, which can
fail on restricted networks. If every engine fails the error says so instead of returning an empty curriculum."""
import logging
from pathlib import Path

log = logging.getLogger(__name__)

ALLOWED = {
    ".pdf": "pdf", ".docx": "docx", ".pptx": "pptx",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".tiff": "image", ".bmp": "image",
    ".txt": "text", ".md": "text",
}

# Leading bytes each binary type must start with (docx/pptx are zip containers).
MAGIC = {
    ".pdf": [b"%PDF"], ".docx": [b"PK\x03\x04"], ".pptx": [b"PK\x03\x04"],
    ".png": [b"\x89PNG"], ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"],
    ".tiff": [b"II*\x00", b"MM\x00*"], ".bmp": [b"BM"],
}

OCR_ENGINES = ("rapidocr", "easyocr")
MIN_TEXT_LAYER_CHARS = 80  # below this a PDF is treated as a scan and OCR is attempted


class DocumentError(Exception):
    """Invalid, empty, or unreadable document."""


def validate_signature(ext: str, head: bytes) -> bool:
    sigs = MAGIC.get(ext)
    return True if sigs is None else any(head.startswith(s) for s in sigs)


_converters: dict = {}


def _converter(ocr: str | None):
    """A Docling converter with OCR off (ocr=None) or using the named engine. Cached: model loading is slow."""
    if ocr in _converters:
        return _converters[ocr]
    from docling.datamodel.base_models import InputFormat  # heavy imports, loaded lazily
    from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = ocr is not None
    if ocr == "rapidocr":
        opts.ocr_options = RapidOcrOptions()
    elif ocr == "easyocr":
        opts.ocr_options = EasyOcrOptions()
    conv = DocumentConverter(format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=opts),
        InputFormat.IMAGE: ImageFormatOption(pipeline_options=opts),
    })
    _converters[ocr] = conv
    return conv


def _pdf_text_layer(path: Path) -> str:
    """Text of a PDF's embedded text layer (pypdfium2). Fast; empty for scans."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        pages = [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]
    finally:
        pdf.close()
    text = "\n\n".join(p.strip() for p in pages if p.strip())
    return text.replace("\r\n", "\n")


def _convert(path: Path, ocr: str | None) -> str:
    return _converter(ocr).convert(str(path)).document.export_to_markdown().strip()


def _ocr(path: Path) -> str:
    errors = []
    for engine in OCR_ENGINES:
        try:
            text = _convert(path, engine)
            if text:
                return text
            errors.append(f"{engine}: no text found")
        except ImportError as e:
            errors.append(f"{engine}: not installed ({e})")
        except Exception as e:
            log.warning("OCR with %s failed for %s: %s", engine, path.name, e)
            errors.append(f"{engine}: {str(e)[:120]}")
    raise DocumentError("OCR could not read this document (" + "; ".join(errors) + "). "
                        "OCR needs its models downloaded on first use; check the network or upload a text-based PDF.")


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    kind = ALLOWED.get(ext)
    if kind is None:
        raise DocumentError(f"Unsupported file type: {ext or 'none'}")
    try:
        if kind == "text":
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        elif kind == "image":
            text = _ocr(path)
        elif kind == "pdf":
            try:
                text = _pdf_text_layer(path)
            except Exception as e:  # corrupt or encrypted: let Docling have a go before giving up
                log.warning("pdfium could not read %s (%s); trying Docling", path.name, e)
                text = _convert(path, None)
            if len(text) < MIN_TEXT_LAYER_CHARS:  # scanned PDF: no usable text layer
                text = _ocr(path)
        else:  # docx, pptx
            text = _convert(path, None)
    except DocumentError:
        raise
    except ImportError as e:
        raise DocumentError("Docling is not installed on the server") from e
    except Exception as e:
        log.exception("Docling failed for %s", path.name)
        raise DocumentError(f"Could not read document: {e}") from e
    if not text:
        raise DocumentError("No text could be extracted (document is empty or unreadable)")
    return text
