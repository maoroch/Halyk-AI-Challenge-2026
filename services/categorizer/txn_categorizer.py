import logging
from typing import List, Optional, Set
from shared.schemas import TransactionRecord
from shared.llm_client import LLMClient

logger = logging.getLogger(__name__)

CATEGORIZATION_PROMPT = """You are a financial controller reviewing bank transactions.
You are given a metric definition from a loan agreement:
"{numerator_definition}"

Review each transaction's counterparty and description below and identify which ones
should be INCLUDED in this metric's calculation.

Return ONLY a JSON object in this exact format (no markdown, no extra text):
{"txn_ids": ["TXN-XXX-0001", "TXN-XXX-0005"]}

If no transactions match, return: {"txn_ids": []}
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

        cache_key = (numerator_definition[:120], metric_type, len(transactions))
        if cache_key in self._cache:
            return self._cache[cache_key]

        # LLM dynamic classification ONLY (No fallback rules)
        if self.llm_client.is_configured():
            try:
                # Send ALL transactions — no [:40] limit (typical ~55 per scenario fits context window)
                txn_descriptions = "\n".join(
                    [f"{t.txn_id}: {t.counterparty} | {t.description}" for t in transactions]
                )
                prompt = (
                    CATEGORIZATION_PROMPT.replace("{numerator_definition}", numerator_definition)
                    + f"\nTransactions:\n{txn_descriptions}"
                )

                # Use plain completion() to avoid json_object format forcing an object wrapper
                # when the prompt asks for an array. We parse manually.
                raw_text = self.llm_client.completion(prompt, temperature=0.0)
                matched_ids = self._parse_txn_id_response(raw_text, transactions)

                if matched_ids is not None:
                    filtered = [t for t in transactions if t.txn_id in matched_ids]
                    logger.info(
                        f"LLM categorization [{metric_type}]: matched {len(filtered)}/{len(transactions)} txns"
                    )
                    self._cache[cache_key] = filtered
                    return filtered

            except Exception as e:
                logger.error(f"LLM transaction categorization failed: {e}")

        # Pure LLM mode: return empty on failure
        logger.warning(f"LLM categorization failed for metric [{metric_type}], returning empty list.")
        self._cache[cache_key] = []
        return []

    def _parse_txn_id_response(self, raw_text: str, transactions: List[TransactionRecord]) -> Optional[set]:
        """Parse LLM response that may be a JSON object {txn_ids:[...]} or a bare JSON array [...]"""
        import json, re

        # Strip <think> blocks from reasoning models
        cleaned = raw_text.strip()
        if "<think>" in cleaned and "</think>" in cleaned:
            cleaned = cleaned.split("</think>", 1)[-1].strip()

        # Strip markdown fences
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        valid_ids = {t.txn_id for t in transactions}

        # Try parse as JSON
        for extractor in [
            lambda s: json.loads(s),
            lambda s: json.loads(s[s.find('{'):s.rfind('}')+1]) if '{' in s else None,
            lambda s: json.loads(s[s.find('['):s.rfind(']')+1]) if '[' in s else None,
        ]:
            try:
                parsed = extractor(cleaned)
                if parsed is None:
                    continue
                if isinstance(parsed, dict):
                    # Accept {"txn_ids": [...]} or {"transactions": [...]} etc.
                    for key in ("txn_ids", "transactions", "ids", "matched", "results"):
                        if key in parsed and isinstance(parsed[key], list):
                            return set(parsed[key]) & valid_ids
                    # If dict has no known key, collect all string values that look like TXN IDs
                    ids = {v for v in parsed.values() if isinstance(v, str) and v.startswith("TXN-")}
                    if ids:
                        return ids & valid_ids
                elif isinstance(parsed, list):
                    return set(str(x) for x in parsed if isinstance(x, str)) & valid_ids
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

        # Last resort: regex extraction is DISABLED — TXN IDs appear in the prompt itself,
        # so regex would extract ALL transaction IDs regardless of relevance.
        # If we can't parse JSON, return None and let the caller handle the failure.
        logger.error(f"Could not parse LLM categorization response as JSON. Raw: {raw_text[:300]}")
        return None
