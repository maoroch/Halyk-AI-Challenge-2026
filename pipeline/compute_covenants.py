# -*- coding: utf-8 -*-
"""Compute status/actual/evidence_txn_id for each scenario's 3 covenants via Groq LLM."""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from groq_client import chat_json as groq_chat_json  # noqa: E402
from ollama_client import chat_json as ollama_chat_json  # noqa: E402

CACHE = pathlib.Path(__file__).resolve().parent / "cache"
BUNDLES_DIR = CACHE / "bundles"
RESULTS_DIR = CACHE / "results"
RESULTS_DIR.mkdir(exist_ok=True)

SYSTEM = """Ты — старший кредитный аналитик банка. Тебе даны для ОДНОГО заёмщика: текст статьи \
кредитного договора о финансовых ковенантах (6.1, 6.2, 6.3), авторитетные вспомогательные \
документы (KYC-досье со списком связанных сторон, аудиторские примечания/отчёты о \
реклассификации операций, служебные записки с исправлениями сумм) и полный список его \
транзакций за 2025 год.

ВАЖНЫЕ ПРАВИЛА:
1. Все данные тебе уже отфильтрованы и авторитетны — других документов нет, доверяй только тому, что дано.
2. Валюта: ковенанты в USD. Транзакции указаны в разных валютах (USD/EUR). Курса конвертации НЕТ нигде в \
материалах, поэтому при расчёте долларовых показателей учитывай ТОЛЬКО транзакции с currency=USD; \
EUR-транзакции исключай из долларовых сумм (это единственный корректный вариант без известного курса).
3. Суммы расходов в реестре отрицательные, доходов — положительные. Для "actual" всегда используй \
модуль (положительное число).
4. Если аудиторский/казначейский документ указывает реклассификацию, исключение по периоду начисления \
(cut-off) или исправление суммы конкретной транзакции — применяй это ИЗМЕНЕНИЕ при расчёте, а не \
исходную запись реестра.
5. Связанные стороны для целей ковенанта — ТОЛЬКО те контрагенты, что явно указаны как связанные \
стороны в KYC-досье (обычно порог доли участия ≥20%, но следуй точной формулировке договора/досье). \
Контрагент, упомянутый в досье, но НЕ достигающий порога, related party не является.
6. Если по сценарию нет KYC-досье или иного документа, определяющего конкретный список связанных \
сторон/контрагентов — считай, что ни один контрагент не подтверждён как связанная сторона (не угадывай).
6b. КРИТИЧЕСКИ ВАЖНО: классифицируй транзакцию СТРОГО по тексту поля description, а НЕ по названию \
контрагента (counterparty). Названия контрагентов могут вводить в заблуждение (например, контрагент \
с "Payroll" в названии может на деле быть описан как "Interest payment" — это НЕ зарплата, а процентный \
расход). Пройди ВСЕ строки таблицы транзакций по одной, не пропуская ни одной, прежде чем суммировать.
7. status: "COMPLIANT" если показатель НЕ нарушает лимит ковенанта (с учётом точной формулировки — \
где лимит "не более X", COMPLIANT когда actual <= X; где "не менее X", COMPLIANT когда actual >= X), \
иначе "BREACH".
8. actual: РЕАЛЬНОЕ значение показателя, которое ограничивает ковенант (не сам лимит из договора). \
Указывай его всегда, даже если status COMPLIANT: положительное число, деньги в USD с 2 знаками после \
запятой, коэффициенты — обычным числом (1.68, не "1.68x").
9. evidence_txn_id: ID ЕДИНСТВЕННОЙ транзакции, которая определяет вердикт (её исключение/включение/ \
реклассификация меняет результат BREACH<->COMPLIANT, либо явно названа в аудиторской записке как \
причина корректировки). Для агрегатных/коэффициентных проверок, где результат не определяется одной \
транзакцией, — null. НЕ указывай транзакцию, просто вносящую вклад в сумму (например, крупнейшую строку).
10. Отвечай СТРОГО валидным JSON без пояснений вне структуры.

Формат ответа (JSON, БЕЗ лишних полей и пояснений):
{
  "6.1": {"status": "COMPLIANT"|"BREACH", "actual": <number>, "evidence_txn_id": "<TXN-...>"|null, "included_txn_ids": ["<TXN-...>", ...], "note": "<макс 12 слов>"},
  "6.2": {...},
  "6.3": {...}
}
included_txn_ids — список ID транзакций, вошедших в расчёт "actual" (все группы, включая числитель и \
знаменатель для коэффициентов). note — предельно кратко."""


def build_user_prompt(bundle: dict) -> str:
    return f"""Заёмщик: account_id={bundle['account_id']}, сценарий={bundle['scenario']}

=== ДОКУМЕНТЫ ===
{bundle['documents_text']}

=== ТРАНЗАКЦИИ ({bundle['n_transactions']} шт., за 2025 год) ===
{bundle['transactions_table']}

Рассчитай статус, фактическое значение и (если применимо) транзакцию-доказательство для \
пунктов 6.1, 6.2 и 6.3. Верни только JSON."""


def main():
    scenarios = sorted(p.stem for p in BUNDLES_DIR.glob("*.json"))
    args = sys.argv[1:]
    backend = "groq"
    model = None
    for flag in list(args):
        if flag.startswith("--model="):
            model = flag.split("=", 1)[1]
            args.remove(flag)
        if flag == "--ollama":
            backend = "ollama"
            args.remove(flag)
    if backend == "ollama":
        chat_json = ollama_chat_json
        model = model or "qwen2.5:7b-instruct"
    else:
        chat_json = groq_chat_json
        model = model or "llama-3.3-70b-versatile"
    only = args if args else None
    if only:
        scenarios = [s for s in scenarios if s in only]
    all_results = {}
    if (CACHE / "all_results.json").exists():
        all_results = json.loads((CACHE / "all_results.json").read_text(encoding="utf-8"))
    first = True
    for scen in scenarios:
        if (RESULTS_DIR / f"{scen}.json").exists():
            print(f"=== {scen}: already done, skipping ===", flush=True)
            continue
        if not first and backend == "groq":
            time.sleep(20)
        first = False
        bundle = json.loads((BUNDLES_DIR / f"{scen}.json").read_text(encoding="utf-8"))
        user = build_user_prompt(bundle)
        print(f"=== {scen} ({len(user)} chars prompt) ===", flush=True)
        try:
            result = chat_json(SYSTEM, user, model=model)
        except Exception as e:
            print(f"  FAILED: {e}", flush=True)
            all_results[scen] = None
            continue
        all_results[scen] = result
        for cov in ["6.1", "6.2", "6.3"]:
            r = result.get(cov, {})
            print(f"  {cov}: {r.get('status')} actual={r.get('actual')} evidence={r.get('evidence_txn_id')} | {r.get('note','')[:80]}", flush=True)
        (RESULTS_DIR / f"{scen}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (CACHE / "all_results.json").write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
