import os
import time
import logging
from typing import Dict, List, Optional, Any
from shared.schemas import CovenantAnswer, DocumentInfo, DocType
from shared.llm_client import LLMClient
from services.ingestion.ingestor import DocumentIngestor
from services.classifier.doc_classifier import DocumentClassifier, TARGET_ACCOUNTS
from services.extractors.covenant_extractor import CovenantExtractor
from services.extractors.adjustment_extractor import AdjustmentExtractor
from services.ledger.ledger_service import LedgerService
from services.decision.decision_engine import DecisionEngine
from services.response_builder.builder import ResponseBuilder
from services.audit_trail.audit_trail_service import AuditTrailService
from services.dashboard.dashboard_generator import DashboardGenerator
from services.currency.currency_service import CurrencyService

logger = logging.getLogger(__name__)


class PipelineRunner:
    def __init__(
        self,
        docs_dir: str = "docs/agentic-bank-public/documents",
        ledger_path: str = "docs/agentic-bank-public/master_ledger_2025.csv",
        template_path: str = "docs/agentic-bank-public/submission_template.json",
        output_path: str = "submission.json",
        audit_trail_path: str = "audit_trail.json",
        dashboard_path: str = "reports/dashboard.html",
        llm_client: Optional[LLMClient] = None
    ):
        self.docs_dir = docs_dir
        self.ledger_path = ledger_path
        self.template_path = template_path
        self.output_path = output_path
        self.audit_trail_path = audit_trail_path
        self.dashboard_path = dashboard_path
        self.llm_client = llm_client or LLMClient()

        self.ingestor = DocumentIngestor(self.docs_dir)
        self.classifier = DocumentClassifier(self.llm_client)
        self.cov_extractor = CovenantExtractor(self.llm_client)
        self.adj_extractor = AdjustmentExtractor(self.llm_client)
        self.ledger_service = LedgerService(self.ledger_path)
        self.currency_service = CurrencyService()
        self.decision_engine = DecisionEngine()
        self.builder = ResponseBuilder(self.template_path)
        self.audit_service = AuditTrailService(output_json_path=self.audit_trail_path)
        self.dashboard_gen = DashboardGenerator(output_path=self.dashboard_path)

    def run(self) -> Dict[str, Any]:
        logger.info("=== STEP 1: Ingesting Documents in Parallel ===")
        raw_documents = self.ingestor.load_all_documents()

        logger.info("=== STEP 2: Classifying Documents & Resolving Bank Entities ===")
        classified_docs = self.classifier.classify_documents(raw_documents)

        # Group documents by account_id and doc_type
        docs_by_account: Dict[str, Dict[DocType, List[DocumentInfo]]] = {}
        for d in classified_docs:
            if not d.account_id:
                continue
            if d.account_id not in docs_by_account:
                docs_by_account[d.account_id] = {}
            if d.doc_type not in docs_by_account[d.account_id]:
                docs_by_account[d.account_id][d.doc_type] = []
            docs_by_account[d.account_id][d.doc_type].append(d)

        logger.info("=== STEP 3: Evaluating Covenants & Building Compliance Audit Trail ===")
        all_answers: Dict[str, Dict[str, CovenantAnswer]] = {}

        for scenario_id, target_account_id in TARGET_ACCOUNTS.items():
            logger.info(f"Processing Scenario {scenario_id} (Account: {target_account_id})...")

            account_docs = docs_by_account.get(target_account_id, {})

            # Get active Loan Agreement
            loan_docs = account_docs.get(DocType.LOAN_AGREEMENT, [])
            active_loan_doc = self._select_active_document(loan_docs)

            if active_loan_doc:
                cov_result = self.cov_extractor.extract_covenants(active_loan_doc)
            else:
                dummy_doc = DocumentInfo(filename="", filepath="", doc_type=DocType.LOAN_AGREEMENT, account_id=target_account_id)
                cov_result = self.cov_extractor.extract_covenants(dummy_doc)

            # Get Audit Adjustments
            audit_docs = account_docs.get(DocType.AUDIT_NOTE, [])
            active_audit_doc = self._select_active_document(audit_docs)
            audit_adj = self.adj_extractor.extract_audit_adjustments(active_audit_doc) if active_audit_doc else None

            # Get KYC Dossier
            kyc_docs = account_docs.get(DocType.KYC_DOSSIER, [])
            active_kyc_doc = self._select_active_document(kyc_docs)
            kyc_info = self.adj_extractor.extract_kyc_dossier(active_kyc_doc) if active_kyc_doc else None

            # Get Scenario Ledger Transactions (excluding auditor period cut-off txns)
            excluded_ids = audit_adj.excluded_txn_ids if audit_adj else []
            txns = self.ledger_service.get_transactions_for_scenario(scenario_id, excluded_txn_ids=excluded_ids)

            scenario_answers: Dict[str, CovenantAnswer] = {}
            for clause_no in ["6.1", "6.2", "6.3"]:
                clause_def = cov_result.covenants.get(clause_no)

                ans = self.decision_engine.evaluate_covenant(
                    clause=clause_def,
                    transactions=txns,
                    audit=audit_adj,
                    kyc=kyc_info
                )
                scenario_answers[clause_no] = ans

                # Record decision in audit trail
                self.audit_service.record_decision(
                    scenario_id=scenario_id,
                    account_id=target_account_id,
                    company_name=cov_result.company_name,
                    clause=clause_def,
                    answer=ans,
                    transactions=txns,
                    source_doc=active_loan_doc.filename if active_loan_doc else "Loan Agreement PDF",
                    audit=audit_adj,
                    kyc=kyc_info
                )

            all_answers[scenario_id] = scenario_answers

            # Brief throttle between scenarios to reduce Groq rate-limit pressure
            time.sleep(2)

        logger.info("=== STEP 4: Saving Submission, Audit Trail & Executive Dashboard ===")
        submission_dict = self.builder.build_submission(all_answers)

        # Primary mandate: Save submission.json first
        self.builder.save_submission(submission_dict, self.output_path)

        # Secondary mandate: Generate optional audit reports in fault-tolerant try-except blocks
        try:
            self.audit_service.save_audit_trail()
        except Exception as e:
            logger.warning(f"Audit trail generation encountered non-fatal error: {e}")

        try:
            self.dashboard_gen.generate_dashboard(submission_dict)
        except Exception as e:
            logger.warning(f"Dashboard generation encountered non-fatal error: {e}")

        return submission_dict

    def _select_active_document(self, docs: List[DocumentInfo]) -> Optional[DocumentInfo]:
        if not docs:
            return None
        for d in docs:
            text = d.raw_text or ""
            if "НЕДЕЙСТВУЮЩАЯ РЕДАКЦИЯ" not in text and "НЕ ПРИМЕНЯЕТСЯ" not in text:
                return d
        return docs[0]
