import pytest
from services.evidence.evidence_selector import EvidenceSelector
from shared.schemas import CovenantClause, TransactionRecord


def test_evidence_selector_marginal_transaction():
    selector = EvidenceSelector()

    clause = CovenantClause(
        clause_number="6.1",
        title="Capex Limit",
        metric_name="CAPEX_LIMIT",
        operator="<=",
        threshold=1000.0,
        is_marginal_single_txn=True
    )

    txns = [
        TransactionRecord(txn_id="TXN-001", date="2025-01-01", account_id="ACC-01", counterparty="A", description="capex", amount=-400.0, currency="USD"),
        TransactionRecord(txn_id="TXN-002", date="2025-01-02", account_id="ACC-01", counterparty="B", description="capex", amount=-700.0, currency="USD"),
    ]

    current_actual = 1100.0  # Status is BREACH since 1100 > 1000
    current_status = "BREACH"

    # Removing TXN-002 (-700) leaves 400 <= 1000 (COMPLIANT).
    # Removing TXN-001 (-400) leaves 700 <= 1000 (COMPLIANT).
    # Since multiple transactions flip verdict, marginal evidence is None.
    evidence_id = selector.find_evidence_transaction(
        covenant=clause,
        transactions=txns,
        current_status=current_status,
        current_actual=current_actual,
        threshold=1000.0,
        operator="<="
    )
    assert evidence_id is None

    # Case where ONLY ONE single transaction flips verdict
    txns_single = [
        TransactionRecord(txn_id="TXN-001", date="2025-01-01", account_id="ACC-01", counterparty="A", description="capex", amount=-50.0, currency="USD"),
        TransactionRecord(txn_id="TXN-002", date="2025-01-02", account_id="ACC-01", counterparty="B", description="capex", amount=-200.0, currency="USD"),
    ]
    current_actual_2 = 1100.0
    # Removing TXN-001 (-50) leaves 1050 > 1000 (BREACH)
    # Removing TXN-002 (-200) leaves 900 <= 1000 (COMPLIANT) -> TXN-002 is the unique evidence!

    evidence_id_2 = selector.find_evidence_transaction(
        covenant=clause,
        transactions=txns_single,
        current_status="BREACH",
        current_actual=current_actual_2,
        threshold=1000.0,
        operator="<="
    )
    assert evidence_id_2 == "TXN-002"
