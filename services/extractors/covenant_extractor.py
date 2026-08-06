import re
import logging
from typing import Dict, Optional
from shared.schemas import DocumentInfo, CovenantClause, CovenantExtractionResult
from shared.llm_client import LLMClient

logger = logging.getLogger(__name__)

COVENANT_ANALYSIS_PROMPT = """Ты анализируешь пункт кредитного договора, задающий финансовый ковенант.
Не считай числа. Опиши только СОСТАВ метрики.
Верни JSON:
{
  "numerator_definition": "краткое описание, что входит в числитель/тестируемую сумму, своими словами по тексту пункта",
  "denominator_definition": "то же для знаменателя, либо null если тест не коэффициентный",
  "references_audit_adjustment": true/false — упоминается ли корректировка/классификация аудитором,
  "references_kyc": true/false — упоминаются ли связанные стороны/аффилированные лица
}
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

                # Try LLM or fallback deterministic extraction for definitions
                num_def, den_def = self._extract_definitions(raw_clause_text)

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
        if self.llm_client.is_configured() and clause_text.strip():
            try:
                res = self.llm_client.completion_json(clause_text, system_prompt=COVENANT_ANALYSIS_PROMPT)
                return res.get("numerator_definition"), res.get("denominator_definition")
            except Exception as e:
                logger.error(f"LLM covenant definition extraction failed: {e}")

        # Deterministic fallback definition extraction
        text_lower = clause_text.lower()

        if "капитальн" in text_lower or "capex" in text_lower:
            num_def = "Капитальные затраты и приобретение оборудования"
            den_def = None
        elif "связан" in text_lower or "аффилир" in text_lower:
            num_def = "Операции со связанными сторонами и управляющие платежи"
            den_def = None
        elif "персонал" in text_lower or "оплат" in text_lower:
            num_def = "Расходы на персонал и накладные расходы"
            den_def = None
        elif "коэффициент" in text_lower or "отношение" in text_lower:
            num_def = "Совокупный долг и операционные расходы"
            den_def = "EBITDA и выручка"
        else:
            num_def = "Совокупные расходы по договору"
            den_def = None

        return num_def, den_def
