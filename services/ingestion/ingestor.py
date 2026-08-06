import os
import logging
import io
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from shared.schemas import DocumentInfo, DocType

logger = logging.getLogger(__name__)


class DocumentIngestor:
    """
    Ingests all files from documents/ folder safely in parallel.
    Includes hybrid OCR fallback (tesseract + PyMuPDF pixmap OCR) for scanned image PDFs.
    """

    def __init__(self, documents_dir: str, max_workers: int = 8):
        self.documents_dir = documents_dir
        self.max_workers = max_workers

    def load_all_documents(self) -> List[DocumentInfo]:
        if not os.path.exists(self.documents_dir):
            raise FileNotFoundError(f"Documents directory does not exist: {self.documents_dir}")

        files = [
            f for f in sorted(os.listdir(self.documents_dir))
            if not f.startswith(".") and f not in ("Thumbs.db", ".DS_Store")
        ]

        documents: List[DocumentInfo] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_fname = {
                executor.submit(self._process_single_file, fname): fname
                for fname in files
            }

            for future in as_completed(future_to_fname):
                try:
                    doc_info = future.result()
                    documents.append(doc_info)
                except Exception as e:
                    fname = future_to_fname[future]
                    logger.error(f"Error processing file {fname}: {e}")

        documents.sort(key=lambda d: d.filename)
        logger.info(f"Ingested {len(documents)} document files ({sum(1 for d in documents if d.is_valid)} valid) in parallel.")
        return documents

    def _process_single_file(self, fname: str) -> DocumentInfo:
        fpath = os.path.join(self.documents_dir, fname)

        if os.path.getsize(fpath) == 0:
            return DocumentInfo(
                filename=fname,
                filepath=fpath,
                doc_type=DocType.CORRUPT,
                is_valid=False,
                raw_text=""
            )

        ext = os.path.splitext(fname)[1].lower()

        if ext == ".pdf":
            return self._parse_pdf(fname, fpath)
        elif ext in (".csv", ".txt"):
            return self._parse_text_file(fname, fpath)

        return DocumentInfo(
            filename=fname,
            filepath=fpath,
            doc_type=DocType.DECOY,
            is_valid=True,
            raw_text=""
        )

    def _parse_pdf(self, filename: str, filepath: str) -> DocumentInfo:
        text = ""

        # Strategy 1: PyMuPDF (fitz) text extraction
        try:
            import fitz
            doc = fitz.open(filepath)
            for page in doc:
                text += page.get_text("text") + "\n"

            # Check if text is empty or very short (< 50 chars), indicating a scanned image PDF
            if len(text.strip()) < 50 and len(doc) > 0:
                logger.info(f"PDF {filename} appears to be a scanned image. Triggering Hybrid OCR fallback...")
                text = self._perform_ocr_fallback(doc)

            doc.close()
        except Exception as e1:
            # Strategy 2: pypdf fallback
            try:
                from pypdf import PdfReader
                reader = PdfReader(filepath)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            except Exception:
                # Strategy 3: pdfplumber fallback
                try:
                    import pdfplumber
                    with pdfplumber.open(filepath) as pdf:
                        for page in pdf.pages:
                            extracted = page.extract_text()
                            if extracted:
                                text += extracted + "\n"
                except Exception as e3:
                    logger.error(f"All PDF parsers failed for {filename}: {e3}")
                    return DocumentInfo(
                        filename=filename,
                        filepath=filepath,
                        doc_type=DocType.CORRUPT,
                        is_valid=False,
                        raw_text=""
                    )

        text = text.strip()
        if not text:
            return DocumentInfo(
                filename=filename,
                filepath=filepath,
                doc_type=DocType.CORRUPT,
                is_valid=False,
                raw_text=""
            )

        return DocumentInfo(
            filename=filename,
            filepath=filepath,
            doc_type=DocType.LOAN_AGREEMENT,
            is_valid=True,
            raw_text=text
        )

    def _perform_ocr_fallback(self, fitz_doc) -> str:
        ocr_text = ""
        try:
            import pytesseract
            from PIL import Image

            for page in fitz_doc:
                pix = page.get_pixmap(dpi=150)
                img = Image.open(io.BytesIO(pix.tobytes()))
                page_ocr = pytesseract.image_to_string(img, lang="rus+eng")
                if page_ocr:
                    ocr_text += page_ocr + "\n"
        except Exception as ocr_err:
            logger.warning(f"pytesseract OCR fallback unavailable/failed: {ocr_err}")

        return ocr_text

    def _parse_text_file(self, filename: str, filepath: str) -> DocumentInfo:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return DocumentInfo(
                filename=filename,
                filepath=filepath,
                doc_type=DocType.DECOY,
                is_valid=True,
                raw_text=content
            )
        except Exception as e:
            return DocumentInfo(
                filename=filename,
                filepath=filepath,
                doc_type=DocType.CORRUPT,
                is_valid=False,
                raw_text=""
            )
