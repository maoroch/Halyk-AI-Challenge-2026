import os
import pytest
from services.ingestion.ingestor import DocumentIngestor
from shared.schemas import DocType


def test_ingestion_valid_and_corrupt(tmp_path):
    # Create a 0-byte corrupt PDF file
    corrupt_pdf = tmp_path / "82954f7cc62a.pdf"
    corrupt_pdf.write_bytes(b"")

    # Create a dummy decoy CSV
    decoy_csv = tmp_path / "4a5315740e89.csv"
    decoy_csv.write_text("server_id,event\n123,error")

    ingestor = DocumentIngestor(str(tmp_path))
    docs = ingestor.load_all_documents()

    assert len(docs) == 2

    corrupt_doc = next(d for d in docs if d.filename == "82954f7cc62a.pdf")
    assert corrupt_doc.is_valid is False
    assert corrupt_doc.doc_type == DocType.CORRUPT

    decoy_doc = next(d for d in docs if d.filename == "4a5315740e89.csv")
    assert decoy_doc.is_valid is True
    assert decoy_doc.doc_type == DocType.DECOY
