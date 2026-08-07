import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ingestion.ingestor import DocumentIngestor
from services.classifier.doc_classifier import DocumentClassifier
from services.extractors.covenant_extractor import CovenantExtractor
from shared.llm_client import LLMClient
from shared.schemas import DocType

docs_dir = "docs/agentic-bank-public/documents"

def test_modal_gpu_live():
    print("==========================================================")
    print("  LIVE MODAL GPU TEST: Testing Qwen2.5-7B on NVIDIA A10G")
    print("==========================================================")
    
    # Force Modal GPU endpoint
    modal_url = "https://salimovilas46--halyk-covenant-llm-serve.modal.run/v1/chat/completions"
    os.environ["MODAL_LLM_URL"] = modal_url
    
    llm_client = LLMClient()
    ingestor = DocumentIngestor(docs_dir)
    classifier = DocumentClassifier(llm_client=llm_client)
    cov_extractor = CovenantExtractor(llm_client=llm_client)
    
    print("\n1. Ingesting & Classifying Documents...")
    docs = ingestor.load_all_documents()
    classified = classifier.classify_documents(docs)
    
    loan_docs = [d for d in classified if d.doc_type == DocType.LOAN_AGREEMENT and d.account_id][:5]
    print(f"-> Found {len(loan_docs)} Loan Agreement documents for live LLM extraction.")
    
    for i, doc in enumerate(loan_docs, 1):
        print(f"\n----------------------------------------------------------")
        print(f"[{i}/5] Account: {doc.account_id} | File: {doc.file_name}")
        print("----------------------------------------------------------")
        
        start_t = time.time()
        print(f"Calling Modal GPU LLM ({modal_url})...")
        
        cov_res = cov_extractor.extract_covenants(doc)
        elapsed = time.time() - start_t
        
        print(f"✓ Modal GPU Response Time: {elapsed:.2f}s")
        print("Extracted Covenant Clauses:")
        for cl_name, clause in [("6.1", cov_res.clause_6_1), ("6.2", cov_res.clause_6_2), ("6.3", cov_res.clause_6_3)]:
            print(f"  - Clause {cl_name}: Threshold={clause.threshold}, Operator={clause.operator}")
            print(f"    Numerator Def: {clause.numerator_definition}")
            print(f"    Denominator Def: {clause.denominator_definition}")

    print("\n==========================================================")
    print("  LIVE MODAL GPU TEST COMPLETE!")
    print("==========================================================")

if __name__ == "__main__":
    test_modal_gpu_live()
