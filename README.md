# Halyk AI Challenge 2026: AI Agent for Corporate Credit Covenant Verification

> **Technical Architecture & Agent Handoff Guide**
> This repository contains an autonomous, single-process AI agent system (`halyk-ai-agent`) built to verify corporate credit covenants, audit reclassifications, and transaction ledgers for the Halyk AI Challenge 2026.

---

## 1. Executive Summary & Problem Context

The goal is to automatically evaluate corporate loan covenant compliance across 12 borrower scenarios (`P1`–`P10`, `B1`, `B4`) and 3 covenant clauses per borrower (`6.1`, `6.2`, `6.3` — 36 total cells).

### Inputs
1. **Unstructured Documents** (`docs/agentic-bank-public/documents/`): PDF and CSV files containing Credit Agreements, Audit Notes, KYC/AML dossiers, decoy HR/IT files, and corrupt 0-byte edge-case files.
2. **Transaction Ledger** (`docs/agentic-bank-public/master_ledger_2025.csv`): 1,473 transaction lines across 561 accounts (12 target scenario accounts + ~550 noise accounts).
3. **Submission Template** (`docs/agentic-bank-public/submission_template.json`): Template defining scenario keys and empty answer cells.

### Output
A single valid **`submission.json`** matching `submission_template.json` structure, where each of the 36 cells contains:
- `status`: `"COMPLIANT"` or `"BREACH"` (uppercase string).
- `actual`: Positive float rounded to 2 decimal places (metric value limited by covenant).
- `evidence_txn_id`: Single marginal transaction ID (`"TXN-..."`) flipping status between `BREACH` $\leftrightarrow$ `COMPLIANT` when removed, or `null` for aggregate/ratio tests.

---

## 2. System Architecture & Directory Structure

```
Halyk-AI-Challenge-2026/
├── services/
│   ├── ingestion/
│   │   └── ingestor.py              # Parallel multithreaded PDF loading + PyMuPDF/PyPDF/pdfplumber + Hybrid OCR fallback (pytesseract) + 0-byte corrupt bypass
│   ├── classifier/
│   │   └── doc_classifier.py        # Classifies doc types (Loan Agreement, Audit Note, KYC, Decoy) and maps exact account_id
│   ├── extractors/
│   │   ├── covenant_extractor.py    # Extracts clauses 6.1, 6.2, 6.3 parameters & thresholds (LLM + regex parser)
│   │   └── adjustment_extractor.py  # Extracts audit EBITDA add-backs, capex reclasses, Note 7 period cut-offs (e.g. TXN-P1-0045), KYC >=20% beneficial ownership entities
│   ├── ledger/
│   │   └── ledger_service.py        # Filters master ledger by account_id and scenario_id, applying auditor period cut-offs
│   ├── decision/
│   │   └── decision_engine.py       # Evaluates positive actual metrics, covenant thresholds, carve-out exceptions, and compliance status
│   ├── evidence/
│   │   └── evidence_selector.py     # Bi-directional marginal transaction selection algorithm (single transaction flipping status BREACH <-> COMPLIANT)
│   ├── response_builder/
│   │   └── builder.py               # Populates submission_template.json without key alterations
│   ├── audit_trail/
│   │   └── audit_trail_service.py   # Generates machine-readable audit_trail.json and HTML compliance report (reports/audit_report.html)
│   ├── dashboard/
│   │   └── dashboard_generator.py   # Builds Executive Credit Risk HTML Dashboard (reports/dashboard.html)
│   ├── currency/
│   │   └── currency_service.py      # Offline Multi-Currency FX Conversion & Document Exchange Rate Parser (KZT, EUR, RUB -> USD)
│   └── orchestrator/
│       └── runner.py                # End-to-end pipeline driver with fault-tolerant report generation
├── shared/
│   ├── entity_normalizer.py         # Normalizes bank counterparty names for KYC related-party tests (stripping LLP, JSC, Inc, Corp, L.L.P., ТОО, АО)
│   ├── llm_client.py                # OpenRouter API client with retries, free model fallbacks, and instant error bypass
│   └── schemas.py                   # Pydantic data models for inter-module contracts
├── scripts/
│   ├── run_pipeline.py              # Main CLI runner with Rich terminal interface
│   ├── run_pipeline.sh              # Executable 1-command shell script
│   ├── validate_submission.py       # 100% structural JSON & sanity validator
│   └── score.py                     # Local evaluator against ground_truth.json using official formula
├── tests/
│   ├── test_ingestion.py            # Unit test for 0-byte corrupt PDF handling
│   ├── test_evidence_selector.py    # Unit test for bi-directional evidence selection algorithm
│   ├── test_fintech_features.py     # Unit test for normalizer, FX converter, audit trail, and dashboard
│   └── test_pipeline_e2e.py         # End-to-end integration test
├── Dockerfile                       # Container definition with Tesseract OCR support
├── docker-compose.yml               # Docker compose configuration
├── Makefile                         # CLI targets (setup, run, validate, score, test)
├── requirements.txt                 # Python dependencies
└── README.md                        # Project documentation & AI agent handoff guide
```

---

## 3. Key Technical Capabilities & Edge-Case Handling

1. **0-Byte & Corrupt PDF Resilience**:
   - `ingestor.py` detects empty/0-byte files (e.g. `82954f7cc62a.pdf`) and corrupt files, marking `is_valid=False` without crashing.

2. **Scanned PDF Hybrid OCR Fallback**:
   - When extracted PDF text length is < 50 characters, `ingestor.py` triggers pixmap image rendering and `pytesseract` OCR text extraction.

3. **Entity Resolution & Account Mapping**:
   - Maps `account_id` (e.g., `ACC-7801`) to `scenario_id` (`P1`) via transaction ID prefixes (`TXN-P1-...`).
   - `doc_classifier.py` uses exact `ACC-\d{4}` account ID extraction to avoid entity resolution traps. `entity_normalizer.py` is strictly isolated for related-party matching in KYC counterparty names.

4. **Auditor Period Cut-Off Extraction**:
   - `adjustment_extractor.py` parses transaction exclusions from Audit Notes (e.g. Note 7 specifying `TXN-P1-0045` belongs to 2026) and excludes them from 2025 calculations.

5. **KYC Beneficial Ownership Threshold (≥20% Rule)**:
   - `adjustment_extractor.py` extracts beneficial ownership percentages from KYC dossiers and filters entities with voting rights ≥ 20.0% (`related_parties_20plus`) for Clause 6.3 related-party tests.

6. **Bi-Directional Marginal Evidence Selection Algorithm**:
   - `evidence_selector.py` evaluates single transactions in both directions (`BREACH` $\rightarrow$ `COMPLIANT` and `COMPLIANT` $\rightarrow$ `BREACH`). Returns transaction ID if exactly 1 transaction flips status.

7. **Fault-Tolerant Compliance Audit Trail & Executive Dashboard**:
   - `runner.py` saves `submission.json` first, and wraps `audit_trail.json` and HTML reports in `try...except` blocks so report generation never blocks submission generation.

---

## 4. How to Run the Project

### Environment Setup
```bash
# Create virtual environment and install dependencies
make setup
# or: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

### Execution Commands
```bash
# 1. Run full pipeline (generates submission.json, audit_trail.json, reports/)
make run
# or: ./scripts/run_pipeline.sh
# or: .venv/bin/python scripts/run_pipeline.py

# 2. Validate structural integrity of submission.json (36 cells check)
make validate
# or: .venv/bin/python scripts/validate_submission.py

# 3. Calculate local score against ground_truth.json
make score
# or: .venv/bin/python scripts/score.py

# 4. Run full pytest automated test suite
make test
# or: .venv/bin/python -m pytest tests/
```

### Docker Execution
```bash
docker-compose up --build
```
