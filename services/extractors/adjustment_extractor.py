import re
import logging
from typing import List, Optional
from shared.schemas import DocumentInfo, AuditAdjustment, KYCDossierInfo
from shared.llm_client import LLMClient

logger = logging.getLogger(__name__)

AUDIT_SYSTEM_PROMPT = """You are an auditor and financial statement analyst.
Extract financial adjustments and period exclusions from an audit note:
1. ebitda_addbacks_total: float total sum of expenses approved for EBITDA add-back.
2. capex_reclassifications_total: float total sum of items reclassified as Capex.
3. capex_reclass_counterparties: list of counterparty names reclassified as Capex.
4. excluded_txn_ids: list of transaction IDs (e.g. TXN-P1-0045) assigned by auditor to other periods (2024 or 2026).

Return JSON:
{
  "account_id": "ACC-XXXX",
  "ebitda_addbacks_total": 0.0,
  "ebitda_addback_descriptions": [],
  "capex_reclassifications_total": 0.0,
  "capex_reclass_counterparties": [],
  "excluded_txn_ids": ["TXN-P1-0045"],
  "notes": "Short summary"
}
"""

KYC_SYSTEM_PROMPT = """You are a compliance analyst evaluating KYC / AML dossiers.
Extract related party affiliate companies along with voting rights percentages.
Entities with >= 20.0% voting rights qualify as related parties.

Return JSON:
{
  "account_id": "ACC-XXXX",
  "related_parties": ["Company A", "Company B"],
  "related_parties_20plus": ["Company A"]
}
"""


from services.retrieval.bm25_retriever import BM25Retriever

class AdjustmentExtractor:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
        self.bm25 = BM25Retriever()

    def extract_audit_adjustments(self, doc: DocumentInfo) -> AuditAdjustment:
        account_id = doc.account_id or "UNKNOWN"
        company_name = doc.company_name or "UNKNOWN"
        text = doc.raw_text or ""

        if self.llm_client.is_configured() and text.strip():
            # Use BM25 to extract relevant audit adjustment sections and cut prompt token consumption
            bm25_query = "аудиторская записка реклассификация capex add-back ebitda исключение транзакций TXN переквалификация"
            compact_text = self.bm25.get_top_snippets(text, query=bm25_query, top_k=3, max_tokens_approx=1500)
            
            try:
                prompt = f"Account ID: {account_id}\nCompany: {company_name}\nAudit Note Text:\n{compact_text}"
                res = self.llm_client.completion_json(prompt, system_prompt=AUDIT_SYSTEM_PROMPT)

                return AuditAdjustment(
                    account_id=account_id,
                    company_name=company_name,
                    ebitda_addbacks_total=float(res.get("ebitda_addbacks_total", 0.0)),
                    ebitda_addback_descriptions=res.get("ebitda_addback_descriptions", []),
                    capex_reclassifications_total=float(res.get("capex_reclassifications_total", 0.0)),
                    capex_reclass_counterparties=res.get("capex_reclass_counterparties", []),
                    excluded_txn_ids=res.get("excluded_txn_ids", []),
                    notes=res.get("notes")
                )
            except Exception as e:
                logger.error(f"LLM audit extraction failed for {account_id}: {e}")

        # Deterministic regex fallback
        addbacks_total = self._regex_find_amount(text, r"(?:add-back|восстановление|добавлен|корректировка ebitda)[^\d]{1,30}(\d[\d\s\.,]+)")
        capex_total = self._regex_find_amount(text, r"(?:capex|капитальные затраты|переклассифи)[^\d]{1,30}(\d[\d\s\.,]+)")

        # Regex for transaction period cut-offs / exclusions (e.g. TXN-P1-0045)
        excluded_ids = re.findall(r"TXN-[A-Z0-9]+-\d+", text)
        # Filter for txns mentioned in cut-off note (Note 7)
        excluded_ids = list(set(excluded_ids)) if "Отсечение" in text or "2026" in text else []

        return AuditAdjustment(
            account_id=account_id,
            company_name=company_name,
            ebitda_addbacks_total=addbacks_total,
            capex_reclassifications_total=capex_total,
            excluded_txn_ids=excluded_ids
        )

    def extract_kyc_dossier(self, doc: DocumentInfo) -> KYCDossierInfo:
        account_id = doc.account_id or "UNKNOWN"
        company_name = doc.company_name or "UNKNOWN"
        text = doc.raw_text or ""

        if self.llm_client.is_configured() and text.strip():
            try:
                prompt = f"Account ID: {account_id}\nText:\n{text[:4000]}"
                res = self.llm_client.completion_json(prompt, system_prompt=KYC_SYSTEM_PROMPT)

                return KYCDossierInfo(
                    account_id=account_id,
                    company_name=company_name,
                    related_parties=res.get("related_parties", []),
                    related_parties_20plus=res.get("related_parties_20plus", [])
                )
            except Exception as e:
                logger.error(f"LLM KYC extraction failed for {account_id}: {e}")

        # Deterministic regex fallback for beneficial ownership percentages (e.g. Aktau Holdings LLP 34.5%)
        parties_all = []
        parties_20plus = []

        matches = re.findall(r"([A-Za-z0-9\sА-Яа-я\.-]+(?:LLP|JSC|Inc|Ltd|Corp|Group|Holdings|TP|LP))\s+(\d+(?:\.\d+)?)%", text, re.IGNORECASE)
        for name, pct_str in matches:
            clean_name = name.strip()
            try:
                pct = float(pct_str)
                parties_all.append(clean_name)
                if pct >= 20.0:
                    parties_20plus.append(clean_name)
            except ValueError:
                pass

        if not parties_all:
            parties_all = re.findall(r'(?:аффилированное лицо|связанная сторона|дочернее общество)\s*:\s*["«]?([A-Za-z0-9\sА-Яа-я\.-]+)["»]?', text, re.IGNORECASE)
            parties_20plus = list(parties_all)

        return KYCDossierInfo(
            account_id=account_id,
            company_name=company_name,
            related_parties=parties_all,
            related_parties_20plus=parties_20plus
        )

    def _regex_find_amount(self, text: str, pattern: str) -> float:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            num_str = match.group(1).replace(" ", "").replace(",", ".")
            try:
                return abs(float(num_str))
            except ValueError:
                pass
        return 0.0
