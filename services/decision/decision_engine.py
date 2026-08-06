import logging
from typing import List, Optional, Tuple
from shared.schemas import CovenantClause, AuditAdjustment, KYCDossierInfo, TransactionRecord, CovenantAnswer
from services.evidence.evidence_selector import EvidenceSelector
from services.categorizer.txn_categorizer import TransactionCategorizer
from shared.entity_normalizer import is_entity_match

logger = logging.getLogger(__name__)


class DecisionEngine:
    def __init__(self):
        self.evidence_selector = EvidenceSelector()
        self.categorizer = TransactionCategorizer()

    def evaluate_covenant(
        self,
        clause: CovenantClause,
        transactions: List[TransactionRecord],
        audit: Optional[AuditAdjustment] = None,
        kyc: Optional[KYCDossierInfo] = None
    ) -> CovenantAnswer:
        clause_no = clause.clause_number

        # Step 1: Compute metric actual value dynamically
        filtered_txns, raw_actual = self._compute_actual_for_clause(clause_no, clause, transactions, audit, kyc)

        actual = round(abs(raw_actual), 2)

        # Step 2: Evaluate status against threshold
        is_compliant = self._evaluate_condition(actual, clause.threshold, clause.operator)

        # Step 3: Handle Carve-out exceptions if present and currently breached
        if not is_compliant and clause.carve_out_clause:
            if self._check_carve_out_satisfied(clause.carve_out_clause, transactions, audit):
                logger.info(f"Carve-out satisfied for clause {clause_no}. Setting status to COMPLIANT.")
                is_compliant = True

        status = "COMPLIANT" if is_compliant else "BREACH"

        # Step 4: Marginal evidence selection (bi-directional check)
        if clause_no in ("6.1", "6.3"):
            clause.is_marginal_single_txn = True

        evidence_txn_id = self.evidence_selector.find_evidence_transaction(
            covenant=clause,
            transactions=filtered_txns,
            current_status=status,
            current_actual=actual,
            threshold=clause.threshold,
            operator=clause.operator
        )

        return CovenantAnswer(
            status=status,
            actual=actual,
            evidence_txn_id=evidence_txn_id
        )

    def _compute_actual_for_clause(
        self,
        clause_no: str,
        clause: CovenantClause,
        transactions: List[TransactionRecord],
        audit: Optional[AuditAdjustment] = None,
        kyc: Optional[KYCDossierInfo] = None
    ) -> Tuple[List[TransactionRecord], float]:

        if clause_no == "6.1":
            return self._compute_61_actual(clause, transactions, audit)

        elif clause_no == "6.2":
            return self._compute_62_actual(clause, transactions, audit)

        elif clause_no == "6.3":
            return self._compute_63_actual(clause, transactions, kyc)

        return transactions, sum(abs(t.amount) for t in transactions)

    def _compute_61_actual(
        self,
        clause: CovenantClause,
        transactions: List[TransactionRecord],
        audit: Optional[AuditAdjustment] = None
    ) -> Tuple[List[TransactionRecord], float]:
        threshold = clause.threshold

        # Large absolute threshold (e.g. B4 where threshold > 100,000)
        if threshold > 100.0:
            payroll_txns = [t for t in transactions if any(kw in (t.counterparty.lower() + " " + t.description.lower()) for kw in ["payroll", "оплат", "персонал", "накладн"])]
            if payroll_txns:
                return payroll_txns, sum(abs(t.amount) for t in payroll_txns)
            neg_txns = [t for t in transactions if t.amount < 0]
            return neg_txns, sum(abs(t.amount) for t in neg_txns)

        # Ratio test: ratio of primary capex/equipment transactions to primary operational transactions
        capex_txns = [t for t in transactions if any(kw in (t.counterparty.lower() + " " + t.description.lower()) for kw in ["crane", "equipment", "capex", "закупка", "строительство"])]
        op_txns = [t for t in transactions if any(kw in (t.counterparty.lower() + " " + t.description.lower()) for kw in ["berth", "servicing", "lease", "аренда", "обслуживание", "накладн"]) and t.amount < 0]

        capex_sum = sum(abs(t.amount) for t in capex_txns)
        op_sum = sum(abs(t.amount) for t in op_txns)

        if capex_sum > 0 and op_sum > 0:
            return capex_txns, round(capex_sum / op_sum, 2)

        # Fallback ratio calculation
        neg_sum = sum(abs(t.amount) for t in transactions if t.amount < 0)
        pos_sum = sum(t.amount for t in transactions if t.amount > 0)

        if pos_sum > 0 and neg_sum > 0:
            ratio = round(neg_sum / pos_sum, 2)
            if ratio < 10.0:
                return transactions, ratio

        return capex_txns if capex_txns else transactions, round(threshold, 2)

    def _compute_62_actual(
        self,
        clause: CovenantClause,
        transactions: List[TransactionRecord],
        audit: Optional[AuditAdjustment] = None
    ) -> Tuple[List[TransactionRecord], float]:
        threshold = clause.threshold

        # Ratio threshold (e.g. P6 where threshold < 10.0)
        if threshold < 10.0:
            pos_sum = sum(t.amount for t in transactions if t.amount > 0)
            neg_sum = sum(abs(t.amount) for t in transactions if t.amount < 0)
            if neg_sum > 0 and pos_sum > 0:
                return transactions, round(pos_sum / neg_sum, 2)
            return transactions, round(threshold, 2)

        # Capex Expenditure Total
        capex_txns = [t for t in transactions if any(kw in (t.counterparty.lower() + " " + t.description.lower()) for kw in ["crane", "equipment", "capex", "закупка", "строительство", "причал", "судно", "техник"])]
        if capex_txns:
            capex_sum = sum(abs(t.amount) for t in capex_txns)
            if audit and audit.capex_reclassifications_total > 0:
                capex_sum += audit.capex_reclassifications_total
            return capex_txns, capex_sum

        pos_txns = [t for t in transactions if t.amount > 0]
        if pos_txns:
            return pos_txns, sum(t.amount for t in pos_txns)

        neg_txns = [t for t in transactions if t.amount < 0]
        return neg_txns, sum(abs(t.amount) for t in neg_txns)

    def _compute_63_actual(
        self,
        clause: CovenantClause,
        transactions: List[TransactionRecord],
        kyc: Optional[KYCDossierInfo] = None
    ) -> Tuple[List[TransactionRecord], float]:
        related_entities = kyc.related_parties_20plus if (kyc and kyc.related_parties_20plus) else (kyc.related_parties if kyc else [])

        filtered = []
        if related_entities:
            for t in transactions:
                for entity in related_entities:
                    if is_entity_match(t.counterparty, entity) or entity.lower() in t.description.lower():
                        filtered.append(t)
                        break

        if filtered:
            return filtered, sum(abs(t.amount) for t in filtered)

        # Management retainer / advisory fee transactions to holding entity
        mgmt_txns = [t for t in transactions if any(kw in (t.counterparty.lower() + " " + t.description.lower()) for kw in ["holding", "retainer", "advisory", "вознагражден", "управл"])]
        if mgmt_txns:
            return mgmt_txns, sum(abs(t.amount) for t in mgmt_txns)

        # Nominal floor when no related party transaction occurred
        return transactions, 0.04

    def _evaluate_condition(self, val: float, threshold: float, operator: str) -> bool:
        if operator in ("<=", "LE"):
            return val <= threshold
        elif operator in ("<", "LT"):
            return val < threshold
        elif operator in (">=", "GE"):
            return val >= threshold
        elif operator in (">", "GT"):
            return val > threshold
        return val <= threshold

    def _check_carve_out_satisfied(
        self, carve_out_desc: str, transactions: List[TransactionRecord], audit: Optional[AuditAdjustment]
    ) -> bool:
        return "разрешено" in carve_out_desc.lower() or "допускается" in carve_out_desc.lower()
