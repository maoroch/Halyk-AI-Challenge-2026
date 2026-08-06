# -*- coding: utf-8 -*-
"""Classify each relevant document by type using deterministic text markers."""
import json
import pathlib
import re

CACHE = pathlib.Path(__file__).resolve().parent / "cache" / "text"
SCEN_DOCS = json.loads((CACHE.parent / "scenario_docs.json").read_text(encoding="utf-8"))


def classify(text: str) -> str:
    head = text[:400]
    if "НЕДЕЙСТВУЮЩАЯ РЕДАКЦИЯ" in head or "НЕ ПРИМЕНЯЕТСЯ" in head:
        return "superseded_credit_agreement"
    if "ДОГОВОР БАНКОВСКОГО ЗАЙМА" in text and "Статья 6" in text:
        return "credit_agreement"
    if "Знай своего клиента" in text and "Проверка связанных сторон" in text:
        return "kyc_dossier_authoritative"
    if "Процедура комплаенса" in text and "Периодическое" in text and "обновление KYC" in text:
        return "compliance_procedure_noise"
    if "ПРОМЕЖУТОЧНАЯ ВЕДОМОСТЬ" in head and ("НЕ ЯВЛЯЕТСЯ ОКОНЧАТЕЛЬНОЙ" in text or "заменена окончательным" in text):
        return "draft_interim_EXCLUDE"
    if "Отчёт о выполнении согласованных процедур" in text and "окончательной позицией" in text:
        return "aup_report_final"
    if "АУДИТОРСКОЕ ДЕЛО" in text or "Примечания к финансовой отчётности" in text:
        return "audit_notes"
    if "Проект «Атлас»" in text or "Проект «Атлас»" in text:
        return "atlas_noise"
    if "Служебная записка казначейства" in text:
        return "treasury_memo"
    return "other_unclassified"


def main():
    result = {}
    counts = {}
    for scen, docs in SCEN_DOCS.items():
        result[scen] = []
        for stem, _size in docs:
            text = (CACHE / f"{stem}.txt").read_text(encoding="utf-8")
            doc_type = classify(text)
            counts[doc_type] = counts.get(doc_type, 0) + 1
            result[scen].append({"stem": stem, "doc_type": doc_type})
    out_path = CACHE.parent / "doc_classification.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Type counts:", counts)
    print()
    for scen, docs in result.items():
        print(scen, [(d["stem"], d["doc_type"]) for d in docs])


if __name__ == "__main__":
    main()
