# -*- coding: utf-8 -*-
"""Assemble final submission.json from computed covenant results."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = pathlib.Path(__file__).resolve().parent / "cache"
RESULTS_DIR = CACHE / "results"

TEAM = "314ZDA"
CONTACT_EMAIL = "blacksibainu@gmail.com"
MODEL_NAME = "llama-3.3-70b-versatile (Groq)"


def main():
    template = json.loads((ROOT / "submission_template.json").read_text(encoding="utf-8"))
    template["team"] = TEAM
    template["contact_email"] = CONTACT_EMAIL
    template["model"] = MODEL_NAME

    import pandas as pd
    ledger = pd.read_csv(ROOT / "master_ledger_2025.csv")
    valid_txn_ids = set(ledger["txn_id"])

    missing = []
    for scenario, covenants in template["answers"].items():
        result_path = RESULTS_DIR / f"{scenario}.json"
        if not result_path.exists():
            missing.append(scenario)
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        for cov_id in covenants:
            r = result.get(cov_id)
            if not r:
                continue
            status = r.get("status")
            if status not in ("COMPLIANT", "BREACH"):
                status = None
            actual = r.get("actual")
            if isinstance(actual, (int, float)):
                actual = round(abs(actual), 2)
            else:
                actual = None
            evidence = r.get("evidence_txn_id")
            if evidence is not None and evidence not in valid_txn_ids:
                evidence = None  # hallucinated txn_id guard
            covenants[cov_id] = {"status": status, "actual": actual, "evidence_txn_id": evidence}

    (ROOT / "submission.json").write_text(
        json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Wrote submission.json")
    if missing:
        print("MISSING scenarios (left as null):", missing)


if __name__ == "__main__":
    main()
