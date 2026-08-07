import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ingestion.ingestor import DocumentIngestor
from services.classifier.doc_classifier import DocumentClassifier
from services.extractors.covenant_extractor import CovenantExtractor
from services.extractors.adjustment_extractor import AdjustmentExtractor
from services.ledger.ledger_service import LedgerService
from services.currency.currency_service import CurrencyService
from services.decision.decision_engine import DecisionEngine
from shared.schemas import DocType

docs_dir = "docs/agentic-bank-public/documents"
ledger_path = "docs/agentic-bank-public/master_ledger_2025.csv"
gt_path = "docs/agentic-bank-public/ground_truth.json"

def test_unit_4_full_offline_eval():
    print("\n--- UNIT 4: Offline Evaluation against Ground Truth ---")
    ingestor = DocumentIngestor(docs_dir)
    classifier = DocumentClassifier()
    cov_extractor = CovenantExtractor()
    adj_extractor = AdjustmentExtractor()
    ledger_service = LedgerService(ledger_path)
    curr_service = CurrencyService()
    decision_engine = DecisionEngine(currency_service=curr_service)
    
    docs = ingestor.load_all_documents()
    classified = classifier.classify_documents(docs)
    
    docs_by_account = {}
    for d in classified:
        if d.account_id:
            docs_by_account.setdefault(d.account_id, {}).setdefault(d.doc_type, []).append(d)
            
    with open(gt_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)["scenarios"]
        
    for scen_id, gt_scen in sorted(gt_data.items()):
        acc_id = ledger_service.scenario_to_account.get(scen_id)
        account_docs = docs_by_account.get(acc_id, {})
        
        # Select active Loan Agreement
        loan_docs = account_docs.get(DocType.LOAN_AGREEMENT, [])
        active_loan_doc = None
        for d in loan_docs:
            if "2025" in (d.raw_text or "") and "НЕДЕЙСТВУЮЩАЯ" not in (d.raw_text or ""):
                active_loan_doc = d
                break
        if not active_loan_doc and loan_docs:
            active_loan_doc = loan_docs[0]
            
        cov_res = cov_extractor.extract_covenants(active_loan_doc) if active_loan_doc else None
        
        # Select active Audit Note
        audit_docs = account_docs.get(DocType.AUDIT_NOTE, [])
        active_audit = audit_docs[0] if audit_docs else None
        audit_adj = adj_extractor.extract_audit_adjustments(active_audit) if active_audit else None
        
        if active_audit and active_audit.raw_text:
            curr_service.extract_fx_rates_from_text(active_audit.raw_text)
            
        # Select active KYC
        kyc_docs = account_docs.get(DocType.KYC_DOSSIER, [])
        active_kyc = kyc_docs[0] if kyc_docs else None
        kyc_info = adj_extractor.extract_kyc_dossier(active_kyc) if active_kyc else None
        
        excluded_ids = audit_adj.excluded_txn_ids if audit_adj else []
        txns = ledger_service.get_transactions_for_scenario(scen_id, excluded_txn_ids=excluded_ids)
        
        print(f"\nScenario {scen_id} (Account: {acc_id}):")
        gt_covs = gt_scen["covenants"]
        for clause_no in ["6.1", "6.2", "6.3"]:
            clause_def = cov_res.covenants.get(clause_no) if cov_res else None
            ans = decision_engine.evaluate_covenant(clause_def, txns, audit_adj, kyc_info) if clause_def else None
            gt = gt_covs[clause_no]
            print(f"  Clause {clause_no}: GT status={gt['status']}, actual={gt['actual']}, evidence={gt['evidence_txn_id']} | SUB status={ans.status if ans else None}, actual={ans.actual if ans else None}, evidence={ans.evidence_txn_id if ans else None}")

if __name__ == "__main__":
    test_unit_4_full_offline_eval()
