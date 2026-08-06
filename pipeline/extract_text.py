# -*- coding: utf-8 -*-
"""Extract text from every PDF in documents/ into pipeline/cache/text/<hash>.txt"""
import pathlib
import sys

import pdfplumber

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "documents"
CACHE_DIR = pathlib.Path(__file__).resolve().parent / "cache" / "text"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def extract_one(pdf_path: pathlib.Path) -> str:
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            parts.append(t)
    return "\n".join(parts)


def main():
    pdfs = sorted(DOCS_DIR.glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs")
    failed = []
    for i, pdf_path in enumerate(pdfs, 1):
        out_path = CACHE_DIR / f"{pdf_path.stem}.txt"
        if out_path.exists():
            continue
        try:
            text = extract_one(pdf_path)
            out_path.write_text(text, encoding="utf-8")
        except Exception as e:
            failed.append((pdf_path.name, str(e)))
        if i % 25 == 0 or i == len(pdfs):
            print(f"  {i}/{len(pdfs)}")
    print(f"Done. Failed: {len(failed)}")
    for name, err in failed:
        print(f"  FAIL {name}: {err}")


if __name__ == "__main__":
    sys.exit(main())
