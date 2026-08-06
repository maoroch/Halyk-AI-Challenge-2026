# -*- coding: utf-8 -*-
"""Assemble per-scenario evidence bundles: covenant text + supporting docs + ledger transactions."""
import json
import pathlib
import re

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = pathlib.Path(__file__).resolve().parent / "cache"
TEXT_DIR = CACHE / "text"

ACCOUNT_BY_SCENARIO = {
    "P1": "ACC-7801", "P2": "ACC-7802", "P3": "ACC-7803", "P4": "ACC-7804",
    "P5": "ACC-7805", "P6": "ACC-7806", "P7": "ACC-7807", "P8": "ACC-7808",
    "P9": "ACC-7809", "P10": "ACC-7810", "B1": "ACC-7201", "B4": "ACC-7204",
}

INCLUDE_TYPES = {"credit_agreement", "kyc_dossier_authoritative", "audit_notes", "aup_report_final", "treasury_memo"}


def extract_article6(text: str) -> str:
    m = re.search(r"Статья\s*6\s*[—\-–].{0,80}?ковенант.{0,60}?\n(.*?)(?=\nСтатья\s*7\b)", text, re.S | re.I)
    return m.group(0).strip() if m else text  # fallback: full text if pattern not found


def format_transactions(df: pd.DataFrame) -> str:
    lines = ["txn_id | date | counterparty | description | amount | currency"]
    for _, row in df.iterrows():
        lines.append(
            f"{row['txn_id']} | {row['date']} | {row['counterparty']} | {row['description']} | "
            f"{row['amount']:.2f} | {row['currency']}"
        )
    return "\n".join(lines)


def main():
    classification = json.loads((CACHE / "doc_classification.json").read_text(encoding="utf-8"))
    ledger = pd.read_csv(ROOT / "master_ledger_2025.csv")

    bundles_dir = CACHE / "bundles"
    bundles_dir.mkdir(exist_ok=True)

    for scenario, docs in classification.items():
        parts = []
        for d in docs:
            if d["doc_type"] not in INCLUDE_TYPES:
                continue
            text = (TEXT_DIR / f"{d['stem']}.txt").read_text(encoding="utf-8")
            if d["doc_type"] == "credit_agreement":
                text = extract_article6(text)
            parts.append(f"--- [{d['doc_type']}] ---\n{text.strip()}")

        account_id = ACCOUNT_BY_SCENARIO[scenario]
        txns = ledger[ledger["account_id"] == account_id].sort_values("date")
        txn_table = format_transactions(txns)

        bundle = {
            "scenario": scenario,
            "account_id": account_id,
            "n_transactions": len(txns),
            "documents_text": "\n\n".join(parts),
            "transactions_table": txn_table,
        }
        (bundles_dir / f"{scenario}.json").write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        doc_types_used = [d["doc_type"] for d in docs if d["doc_type"] in INCLUDE_TYPES]
        print(f"{scenario}: {len(txns)} txns, docs={doc_types_used}, prompt_chars={len(bundle['documents_text']) + len(txn_table)}")


if __name__ == "__main__":
    main()
