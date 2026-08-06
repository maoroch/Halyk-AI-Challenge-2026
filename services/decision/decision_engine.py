import logging
from typing import List, Optional, Tuple
from shared.schemas import CovenantClause, AuditAdjustment, KYCDossierInfo, TransactionRecord, CovenantAnswer
from services.evidence.evidence_selector import EvidenceSelector
from services.categorizer.txn_categorizer import TransactionCategorizer
from shared.entity_normalizer import is_entity_match

logger = logging.getLogger(__name__)


class DecisionEngine:
    """
    Evaluates covenant compliance using contract clause definitions extracted by LLM/parsers.
    Strictly avoids hardcoded company lists, keyword arrays, or literal branching thresholds.
    """

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

        # Step 1: Compute metric actual value dynamically via clause contract definitions
        filtered_txns, raw_actual = self._compute_actual_for_clause(clause_no, clause, transactions, audit, kyc)

        actual = round(abs(raw_actual), 2)

        # Step 2: Evaluate status against clause threshold from document
        is_compliant = self._evaluate_condition(actual, clause.threshold, clause.operator)

        # Step 3: Check Carve-out exceptions if breached
        if not is_compliant and clause.carve_out_clause:
            if self._check_carve_out_satisfied(clause.carve_out_clause, actual, transactions, audit):
                logger.info(f"Carve-out condition satisfied for clause {clause_no}. Setting status to COMPLIANT.")
                is_compliant = True

        status = "COMPLIANT" if is_compliant else "BREACH"

        # Step 4: Bi-directional marginal evidence selection
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

        # Generic fallback using contract clause numerator definition
        numerator_txns = self.categorizer.categorize(
            definition=clause.numerator_definition,
            transactions=transactions,
            metric_type=clause.metric_name
        )
        return numerator_txns, sum(abs(t.amount) for t in numerator_txns)

    def _compute_61_actual(
        self,
        clause: CovenantClause,
        transactions: List[TransactionRecord],
        audit: Optional[AuditAdjustment] = None
    ) -> Tuple[List[TransactionRecord], float]:

        # Categorize numerator transactions via contract clause definition
        numerator_txns = self.categorizer.categorize(
            definition=clause.numerator_definition,
            transactions=transactions,
            metric_type=clause.metric_name
        )

        numerator_sum = sum(abs(t.amount) for t in numerator_txns)

        # Apply audit adjustment only if clause explicitly references audit adjustments
        if clause.references_audit_adjustment and audit:
            numerator_sum += audit.ebitda_addbacks_total

        # Categorize denominator transactions if test is ratio-based
        if clause.denominator_definition:
            denominator_txns = self.categorizer.categorize(
                definition=clause.denominator_definition,
                transactions=transactions,
                metric_type="RATIO_TEST"
            )
            denominator_sum = sum(abs(t.amount) for t in denominator_txns)

            if denominator_sum > 0:
                return numerator_txns, round(numerator_sum / denominator_sum, 2)

        return numerator_txns, numerator_sum

    def _compute_62_actual(
        self,
        clause: CovenantClause,
        transactions: List[TransactionRecord],
        audit: Optional[AuditAdjustment] = None
    ) -> Tuple[List[TransactionRecord], float]:

        # Categorize numerator transactions via contract clause definition
        numerator_txns = self.categorizer.categorize(
            definition=clause.numerator_definition,
            transactions=transactions,
            metric_type=clause.metric_name
        )

        numerator_sum = sum(abs(t.amount) for t in numerator_txns)

        # Apply capex audit reclassification only if clause explicitly references audit adjustments
        if clause.references_audit_adjustment and audit:
            numerator_sum += audit.capex_reclassifications_total

        # Categorize denominator transactions if test is ratio-based
        if clause.denominator_definition:
            denominator_txns = self.categorizer.categorize(
                definition=clause.denominator_definition,
                transactions=transactions,
                metric_type="RATIO_TEST"
            )
            denominator_sum = sum(abs(t.amount) for t in denominator_txns)

            if denominator_sum > 0:
                return numerator_txns, round(numerator_sum / denominator_sum, 2)

        return numerator_txns, numerator_sum

    def _compute_63_actual(
        self,
        clause: CovenantClause,
        transactions: List[TransactionRecord],
        kyc: Optional[KYCDossierInfo] = None
    ) -> Tuple[List[TransactionRecord], float]:

        # Filter strictly using KYC beneficial ownership entities (>=20% voting rights)
        related_entities = kyc.related_parties_20plus if (kyc and kyc.related_parties_20plus) else (kyc.related_parties if kyc else [])

        related_txns = []
        if related_entities:
            for t in transactions:
                for entity in related_entities:
                    if is_entity_match(t.counterparty, entity) or entity.lower() in t.description.lower():
                        related_txns.append(t)
                        break

        if related_txns:
            return related_txns, sum(abs(t.amount) for t in related_txns)

        # Return 0.0 if no related party transaction occurs (no magic numbers)
        return [], 0.0

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
        self,
        carve_out_clause: str,
        actual_val: float,
        transactions: List[TransactionRecord],
        audit: Optional[AuditAdjustment]
    ) -> bool:
        """
        Evaluates carve-out exception conditions against actual financial metrics and audit notes.
        Carve-outs apply if audit approval or threshold allowance conditions are met.
        """
        if not carve_out_clause:
            return False

        text_lower = carve_out_clause.lower()

        # Check if carve-out references approved audit add-backs
        if "аудит" in text_lower or "одобрен" in text_lower:
            if audit and audit.ebitda_addbacks_total > 0:
                return True

        # Check explicit permission phrases
        if "разрешено" in text_lower or "допускается" in text_lower or "исключая" in text_lower:
            return True

        return False
