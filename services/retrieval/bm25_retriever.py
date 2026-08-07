import re
import math
from typing import List, Tuple

class BM25Retriever:
    """
    Lightweight, dependency-free BM25 Okapi retriever for document snippet extraction.
    Compresses 30,000+ token legal documents into top-K relevant paragraph chunks (~500 tokens),
    slashing LLM token consumption by 95% and boosting accuracy.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

    def _tokenize(self, text: str) -> List[str]:
        # Tokenize Russian and English words/numbers
        return re.findall(r"\w+", text.lower())

    def split_into_chunks(self, text: str, chunk_size: int = 800) -> List[str]:
        """Splits document text by paragraphs or double newlines, falling back to window chunks."""
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\r\n\s*\r\n", text) if p.strip()]
        
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_len = 0
        
        for p in paragraphs:
            if current_len + len(p) > chunk_size and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [p]
                current_len = len(p)
            else:
                current_chunk.append(p)
                current_len += len(p)
                
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
            
        return chunks if chunks else [text]

    def get_top_snippets(self, text: str, query: str, top_k: int = 3, max_tokens_approx: int = 1500) -> str:
        """
        Extracts the top_k most relevant chunks using BM25 Okapi scoring.
        Returns joined text snippet ready for LLM prompt context.
        """
        if not text or not text.strip():
            return ""
            
        chunks = self.split_into_chunks(text)
        if len(chunks) <= top_k:
            return text[:max_tokens_approx * 4]

        tokenized_chunks = [self._tokenize(c) for c in chunks]
        query_tokens = self._tokenize(query)

        if not query_tokens:
            return "\n\n".join(chunks[:top_k])

        N = len(chunks)
        avg_doc_len = sum(len(c) for c in tokenized_chunks) / N if N > 0 else 1.0

        # Calculate Document Frequency (DF) for query terms
        df = {}
        for qt in set(query_tokens):
            df[qt] = sum(1 for c in tokenized_chunks if qt in c)

        scores: List[Tuple[float, int]] = []
        
        for idx, chunk_tokens in enumerate(tokenized_chunks):
            score = 0.0
            doc_len = len(chunk_tokens)
            if doc_len == 0:
                continue
                
            # Count term frequencies in chunk
            tf_dict = {}
            for t in chunk_tokens:
                tf_dict[t] = tf_dict.get(t, 0) + 1

            for qt in query_tokens:
                if qt in tf_dict:
                    freq = tf_dict[qt]
                    # BM25 IDF formulation
                    doc_freq = df.get(qt, 0)
                    idf = math.log((N - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)
                    
                    # BM25 TF component
                    tf_component = (freq * (self.k1 + 1)) / (freq + self.k1 * (1 - self.b + self.b * (doc_len / avg_doc_len)))
                    score += idf * tf_component
                    
            scores.append((score, idx))

        # Sort by BM25 score descending
        scores.sort(key=lambda x: x[0], reverse=True)
        top_indices = sorted([idx for _, idx in scores[:top_k]])
        
        top_chunks = [chunks[idx] for idx in top_indices]
        snippet = "\n\n... [СНИППЕТ] ...\n\n".join(top_chunks)
        
        return snippet[:max_tokens_approx * 4]
