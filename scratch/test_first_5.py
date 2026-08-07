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

def run_test_first_5():
    print("==========================================================")
    print("  UNIT TEST: Evaluating First 5 Scenarios (B1, B4, P1, P2, P3)")
    print("==========================================================")
    
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
        
    test_scenarios = ["B1", "B4", "P1", "P2", "P3"]
    exact_matches = 0
    total_checks = 0
    
    for scen_id in test_scenarios:
        gt_scen = gt_data[scen_id]
        acc_id = ledger_service.scenario_to_account.get(scen_id)
        account_docs = docs_by_account.get(acc_id, {})
        
        loan_docs = account_docs.get(DocType.LOAN_AGREEMENT, [])
        active_loan_doc = None
        for d in loan_docs:
            if "2025" in (d.raw_text or "") and "НЕДЕЙСТВУЮЩАЯ" not in (d.raw_text or ""):
                active_loan_doc = d
                break
        if not active_loan_doc and loan_docs:
            active_loan_doc = loan_docs[0]
            
        cov_res = cov_extractor.extract_covenants(active_loan_doc) if active_loan_doc else None
        
        audit_docs = account_docs.get(DocType.AUDIT_NOTE, [])
        active_audit = audit_docs[0] if audit_docs else None
        audit_adj = adj_extractor.extract_audit_adjustments(active_audit) if active_audit else None
        
        txns = ledger_service.get_transactions_for_account(acc_id)
        
        covenant_evals = decision_engine.evaluate_covenants(
            scenario_id=scen_id,
            covenants=cov_res,
            audit_adjustments=audit_adj,
            ledger_transactions=txns
        )
        
        print(f"\nScenario {scen_id} (Account: {acc_id}):")
        for cl_key in ["clause_6_1", "clause_6_2", "clause_6_3"]:
            cl_eval = covenant_evals[cl_key]
            gt_clause = gt_scen[cl_key]
            
            calc_val = cl_eval.actual_value
            gt_val = gt_clause.get("actual_value", 0.0)
            
            calc_st = cl_eval.status.value if hasattr(cl_eval.status, "value") else str(cl_eval.status)
            gt_st = gt_clause.get("status")
            
            diff = abs(calc_val - gt_val)
            match_str = "EXACT MATCH ✓" if diff < 0.01 and calc_st == gt_st else f"DIFF: calc={calc_val}, gt={gt_val}"
            
            if diff < 0.01 and calc_st == gt_st:
                exact_matches += 1
            total_checks += 1
            
            print(f"  [{cl_key}]: Status={calc_st} (GT={gt_st}) | Calc={calc_val:,.2f} | GT={gt_val:,.2f} -> {match_str}")

    print("\n----------------------------------------------------------")
    print(f"SUMMARY FIRST 5 SCENARIOS: {exact_matches}/{total_checks} exact matches ({exact_matches/total_checks*100:.1f}%)")
    print("----------------------------------------------------------")

if __name__ == "__main__":
    run_test_first_5()
