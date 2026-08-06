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
        self._cache = {}

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
            return []

        cache_key = (numerator_definition, metric_type, len(transactions))
        if cache_key in self._cache:
            return self._cache[cache_key]

        # LLM dynamic classification ONLY (No fallback rules)
        if self.llm_client.is_configured():
            try:
                txn_descriptions = "\n".join([f"{t.txn_id}: {t.counterparty} | {t.description}" for t in transactions[:40]])
                prompt = f"Метрика: {numerator_definition}\nТранзакции:\n{txn_descriptions}"

                res = self.llm_client.completion_json(prompt, system_prompt=CATEGORIZATION_PROMPT)
                if isinstance(res, list) and len(res) > 0:
                    matched_ids = set(res)
                    filtered = [t for t in transactions if t.txn_id in matched_ids]
                    self._cache[cache_key] = filtered
                    return filtered
            except Exception as e:
                logger.error(f"LLM transaction categorization failed: {e}")

        # Pure LLM mode: NO offline keyword fallbacks
        self._cache[cache_key] = []
        return []
