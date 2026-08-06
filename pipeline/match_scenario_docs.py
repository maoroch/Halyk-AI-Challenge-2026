# -*- coding: utf-8 -*-
"""Match documents to scenarios using BOTH account_id and exact company name."""
import json
import pathlib
import re

CACHE = pathlib.Path(__file__).resolve().parent / "cache"
TEXT_DIR = CACHE / "text"

ACCOUNT_BY_SCENARIO = {
    "P1": "ACC-7801", "P2": "ACC-7802", "P3": "ACC-7803", "P4": "ACC-7804",
    "P5": "ACC-7805", "P6": "ACC-7806", "P7": "ACC-7807", "P8": "ACC-7808",
    "P9": "ACC-7809", "P10": "ACC-7810", "B1": "ACC-7201", "B4": "ACC-7204",
}
NAMES = json.loads((CACHE / "scenario_company_names.json").read_text(encoding="utf-8"))


def main():
    scenario_docs = {s: [] for s in ACCOUNT_BY_SCENARIO}
    for f in sorted(TEXT_DIR.glob("*.txt")):
        text = f.read_text(encoding="utf-8")
        for scen, acc in ACCOUNT_BY_SCENARIO.items():
            acc_match = re.search(re.escape(acc) + r"(-\d+)?\b", text)
            name_match = NAMES.get(scen) and (NAMES[scen] in text)
            if acc_match or name_match:
                scenario_docs[scen].append((f.stem, len(text)))
    for s, docs in scenario_docs.items():
        print(s, NAMES[s], "->", len(docs), "docs")
    (CACHE / "scenario_docs.json").write_text(
        json.dumps(scenario_docs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total_unique = len(set(x for v in scenario_docs.values() for x in v))
    print("total unique docs:", total_unique)


if __name__ == "__main__":
    main()
