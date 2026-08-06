import logging
from typing import List, Optional
from shared.schemas import TransactionRecord
from shared.llm_client import LLMClient

logger = logging.getLogger(__name__)

CATEGORIZATION_PROMPT = """Ты финансовый контролер.
Тебе дано описание состава метрики из кредитного договора:
"{numerator_definition}"

Проанализируй список назначений платежей транзакций и верни JSON массив с txn_id тех транзакций, которые входят в эту метрику:
[
  "TXN-XXX-0001",
  "TXN-XXX-0005"
]
"""


class TransactionCategorizer:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def categorize(
        self,
        definition: Optional[str],
        transactions: List[TransactionRecord],
        metric_type: str = "GENERIC"
    ) -> List[TransactionRecord]:
        return self.filter_numerator_transactions(definition or "", transactions, metric_type)

    def filter_numerator_transactions(
        self,
        numerator_definition: str,
        transactions: List[TransactionRecord],
        metric_type: str = "GENERIC"
    ) -> List[TransactionRecord]:
        if not transactions:
            return []

        if not numerator_definition or not numerator_definition.strip():
            return transactions

        # Attempt LLM dynamic classification if configured and online
        if self.llm_client.is_configured():
            try:
                txn_descriptions = "\n".join([f"{t.txn_id}: {t.counterparty} | {t.description}" for t in transactions[:60]])
                prompt = f"Метрика: {numerator_definition}\nТранзакции:\n{txn_descriptions}"

                res = self.llm_client.completion_json(prompt, system_prompt=CATEGORIZATION_PROMPT)
                if isinstance(res, list) and len(res) > 0:
                    matched_ids = set(res)
                    filtered = [t for t in transactions if t.txn_id in matched_ids]
                    if filtered:
                        return filtered
            except Exception as e:
                logger.error(f"LLM transaction categorization failed: {e}")

        # Deterministic offline keyword matching based on contract clause definition
        num_lower = numerator_definition.lower()
        matched = []

        if "капитальн" in num_lower or "capex" in num_lower or metric_type == "CAPEX_LIMIT":
            matched = [t for t in transactions if any(w in (t.counterparty.lower() + " " + t.description.lower()) for w in ["оборудован", "строительст", "капитальн", "модернизац", "техник", "кран", "судно", "причал", "монтаж", "реконструкц", "capex", "equipment"])]
        elif "персонал" in num_lower or "накладн" in num_lower or metric_type == "OVERHEAD_PERSONNEL_LIMIT":
            matched = [t for t in transactions if any(w in (t.counterparty.lower() + " " + t.description.lower()) for w in ["зарплат", "персонал", "накладн", "аренд", "коммунал", "офис", "администрат", "услуг", "содержани", "payroll", "retainer"])]
        elif "выручк" in num_lower or "поступлен" in num_lower or metric_type == "REVENUE_LIMIT":
            matched = [t for t in transactions if t.amount > 0 and any(w in (t.counterparty.lower() + " " + t.description.lower()) for w in ["выручк", "поступлен", "расчет", "продаж", "settlement", "sales"])]
        elif "связан" in num_lower or "аффилир" in num_lower or metric_type == "RELATED_PARTY_LIMIT":
            matched = [t for t in transactions if any(w in (t.counterparty.lower() + " " + t.description.lower()) for w in ["holding", "управл", "вознагражден", "агентск", "консультац", "роялти", "дивиденд"])]

        if matched:
            return matched

        return transactions
