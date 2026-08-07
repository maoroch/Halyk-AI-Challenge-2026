import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ingestion.ingestor import DocumentIngestor
from services.retrieval.bm25_retriever import BM25Retriever
from services.classifier.doc_classifier import DocumentClassifier
from shared.schemas import DocType

docs_dir = "docs/agentic-bank-public/documents"

def test_bm25_retrieval_performance():
    print("==========================================================")
    print("  UNIT TEST: BM25 Lexical Retrieval & Token Compression")
    print("==========================================================")
    
    ingestor = DocumentIngestor(docs_dir)
    classifier = DocumentClassifier()
    retriever = BM25Retriever()
    
    docs = ingestor.load_all_documents()
    classified = classifier.classify_documents(docs)
    
    relevant_docs = [d for d in classified if d.doc_type in (DocType.LOAN_AGREEMENT, DocType.AUDIT_NOTE) and d.raw_text][:5]
    
    total_orig_chars = 0
    total_bm25_chars = 0
    total_time_ms = 0.0
    
    for i, doc in enumerate(relevant_docs, 1):
        raw_text = doc.raw_text or ""
        orig_len = len(raw_text)
        total_orig_chars += orig_len
        
        query = "ковенант 6.1 6.2 6.3 капитальные затраты capex аудиторская записка реклассификация"
        
        start_t = time.time()
        snippet = retriever.get_top_snippets(raw_text, query=query, top_k=3, max_tokens_approx=1500)
        elapsed_ms = (time.time() - start_t) * 1000.0
        total_time_ms += elapsed_ms
        
        bm25_len = len(snippet)
        total_bm25_chars += bm25_len
        reduction_pct = (1.0 - (bm25_len / orig_len)) * 100.0 if orig_len > 0 else 0.0
        
        print(f"\n[{i}/5] File: {doc.filename} ({doc.doc_type.value}) | Account: {doc.account_id}")
        print(f"  - Original Length: {orig_len:,} chars (~{orig_len//4:,} tokens)")
        print(f"  - BM25 Snippet:   {bm25_len:,} chars (~{bm25_len//4:,} tokens)")
        print(f"  - Token Reduction: {reduction_pct:.1f}% reduction!")
        print(f"  - BM25 Latency:   {elapsed_ms:.2f} ms")
        print(f"  - Snippet Preview: {snippet[:150].replace('\n', ' ')}...")
        
    avg_reduction = (1.0 - (total_bm25_chars / total_orig_chars)) * 100.0
    print("\n----------------------------------------------------------")
    print(f"SUMMARY BM25 PERFORMANCE:")
    print(f"  - Total Original Text:  {total_orig_chars:,} chars")
    print(f"  - Total BM25 Snippets:  {total_bm25_chars:,} chars")
    print(f"  - Average Token Savings: {avg_reduction:.1f}% REDUCTION!")
    print(f"  - Average BM25 Latency:  {total_time_ms / len(relevant_docs):.2f} ms per doc")
    print("----------------------------------------------------------")

if __name__ == "__main__":
    test_bm25_retrieval_performance()
