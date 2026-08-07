import re
import logging
from typing import Dict, Optional
from shared.schemas import DocumentInfo, CovenantClause, CovenantExtractionResult
from shared.llm_client import LLMClient

logger = logging.getLogger(__name__)

COVENANT_ANALYSIS_PROMPT = """You are a financial covenant analyst. Analyze the loan agreement clause and extract the metric composition.
Do NOT calculate numbers. Only describe what transactions/items are INCLUDED in the metric.

Return ONLY a JSON object (no markdown, no extra text):
{
  "numerator_definition": "Short plain-text description of what expenses/amounts form the numerator or tested sum. Example: 'All capital expenditure payments reclassified by auditor as Capex' or 'Total debt service payments including interest and principal'. Use the actual clause wording.",
  "denominator_definition": "Description of denominator if ratio-based test, or null if it is an absolute limit test",
  "references_audit_adjustment": true or false — does the clause mention auditor reclassification or adjustment,
  "references_kyc": true or false — does the clause mention related parties, affiliates or beneficial owners
}

Rules:
- numerator_definition MUST always be a non-empty string describing the category of transactions to aggregate
- If the clause tests a ratio, fill denominator_definition with the denominator description
- If the clause tests an absolute amount limit, set denominator_definition to null
"""


class CovenantExtractor:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def extract_covenants(self, doc: DocumentInfo) -> CovenantExtractionResult:
        text = doc.raw_text or ""
        account_id = doc.account_id or "UNKNOWN"
        company_name = doc.company_name or "UNKNOWN"

        snippet = self._extract_covenant_body(text)
        covenants_map = self._extract_covenants_from_text(snippet, account_id, company_name)

        return CovenantExtractionResult(
            account_id=account_id,
            company_name=company_name,
            covenants=covenants_map
        )

    def _extract_covenant_body(self, text: str) -> str:
        match_body = re.search(r"(?:Статья 6 —|Пункт 6\.1)[\s\S]{1,5000}(?=(?:Статья 7|\Z))", text)
        if match_body:
            return match_body.group(0)

        match_clauses = re.search(r"6\.1[\s\S]{1,4000}", text)
        if match_clauses:
            return match_clauses.group(0)

        return text[:4000]

    def _extract_covenants_from_text(self, snippet: str, account_id: str, company_name: str) -> Dict[str, CovenantClause]:
        covenants_map = {}

        for clause_key in ["6.1", "6.2", "6.3"]:
            pattern = rf"Пункт {clause_key}[\s\S]{{1,1200}}(?=(?:Пункт 6\.[123]|Статья 7|\Z))"
            match = re.search(pattern, snippet, re.IGNORECASE)

            if match:
                raw_clause_text = match.group(0).strip()

                # Extract threshold number
                threshold = 0.0
                if clause_key == "6.1":
                    ratio_match = re.search(r"(\d+\.\d+)x", raw_clause_text, re.IGNORECASE)
                    if ratio_match:
                        threshold = float(ratio_match.group(1))
                    else:
                        amount_match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", raw_clause_text)
                        if amount_match:
                            threshold = float(amount_match.group(1).replace(",", ""))
                else:
                    # Clause 6.2 and 6.3 thresholds are dollar limits
                    amount_match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", raw_clause_text)
                    if amount_match:
                        threshold = float(amount_match.group(1).replace(",", ""))
                    else:
                        ratio_match = re.search(r"(\d+\.\d+)x", raw_clause_text, re.IGNORECASE)
                        if ratio_match:
                            threshold = float(ratio_match.group(1))

                # Extract operator
                operator = "<="
                text_lower = raw_clause_text.lower()
                if "не менее" in text_lower or "поддерживать" in text_lower or "обеспечить" in text_lower:
                    operator = ">="
                elif "не превышал" in text_lower or "не допускать" in text_lower or "не превышала" in text_lower:
                    operator = "<="

                # Determine metric category
                if "коэффициент" in text_lower or "отношение" in text_lower or "доля" in text_lower or "ratio" in text_lower or "покрытия" in text_lower:
                    metric_name = "RATIO_TEST"
                elif "выручк" in text_lower or "поступлен" in text_lower or "revenue" in text_lower:
                    metric_name = "REVENUE_LIMIT"
                elif "связан" in text_lower or "аффилир" in text_lower or "related-party" in text_lower:
                    metric_name = "RELATED_PARTY_LIMIT"
                elif "персонал" in text_lower or "оплат" in text_lower or "накладных" in text_lower:
                    metric_name = "OVERHEAD_PERSONNEL_LIMIT"
                elif "капитальн" in text_lower or "capex" in text_lower:
                    metric_name = "CAPEX_LIMIT"
                else:
                    metric_name = "GENERIC_LIMIT"

                # Check marginal single transaction condition
                is_marginal = ("отдельная" in text_lower or "отдельный" in text_lower or "одной транзакцией" in text_lower or "одиночн" in text_lower or "определяющей результат" in text_lower)

                # Check audit adjustments & KYC references
                ref_audit = any(w in text_lower for w in ["корректировк", "аудит", "переклассифи", "восстановл", "отсечен"])
                ref_kyc = any(w in text_lower for w in ["связан", "аффилир", "дочерн", "kyc", "бенфициа"])

                # LLM extraction with raw_clause_text fallback
                num_def, den_def = self._extract_definitions(raw_clause_text)

                # Ensure numerator_definition is NEVER None — fallback to raw clause text
                # so the TransactionCategorizer always has something to work with
                if not num_def or not str(num_def).strip():
                    num_def = raw_clause_text
                    logger.warning(f"LLM returned empty numerator_definition for {clause_key}. Using raw clause text as fallback.")

                covenants_map[clause_key] = CovenantClause(
                    clause_number=clause_key,
                    title=f"Clause {clause_key}",
                    metric_name=metric_name,
                    operator=operator,
                    threshold=threshold,
                    period="ANNUAL",
                    is_marginal_single_txn=is_marginal,
                    raw_clause_text=raw_clause_text,
                    numerator_definition=num_def,
                    denominator_definition=den_def,
                    references_audit_adjustment=ref_audit,
                    references_kyc=ref_kyc
                )
            else:
                covenants_map[clause_key] = CovenantClause(
                    clause_number=clause_key,
                    title=f"Clause {clause_key}",
                    metric_name="GENERIC",
                    operator="<=",
                    threshold=0.0,
                    period="ANNUAL",
                    raw_clause_text=f"Пункт {clause_key} по умолчанию"
                )

        return covenants_map

    def _extract_definitions(self, clause_text: str) -> tuple:
        """Extract numerator/denominator definitions via LLM.
        Returns (numerator_def, denominator_def). May return (None, None) on failure —
        caller is responsible for applying raw_clause_text fallback.
        """
        if self.llm_client.is_configured() and clause_text.strip():
            try:
                res = self.llm_client.completion_json(clause_text, system_prompt=COVENANT_ANALYSIS_PROMPT)
                # Handle case where model returns a list wrapping the object
                if isinstance(res, list) and len(res) > 0 and isinstance(res[0], dict):
                    res = res[0]
                if isinstance(res, dict):
                    num_def = res.get("numerator_definition") or res.get("numerator") or res.get("metric_definition")
                    den_def = res.get("denominator_definition") or res.get("denominator")
                    return num_def, den_def
            except Exception as e:
                logger.error(f"LLM covenant definition extraction failed: {e}")

        # Caller will substitute raw_clause_text as fallback
        return None, None
