import logging
from typing import List, Optional
from shared.schemas import CovenantClause, TransactionRecord

logger = logging.getLogger(__name__)


class EvidenceSelector:
    """
    Implements bi-directional marginal transaction selection algorithm.
    Identifies the single transaction whose removal flips the compliance verdict:
    - From BREACH to COMPLIANT (if currently BREACH)
    - From COMPLIANT to BREACH (if currently COMPLIANT)
    For ratio/aggregate tests or cases where no single transaction flips the verdict, returns None.
    """

    def find_evidence_transaction(
        self,
        covenant: CovenantClause,
        transactions: List[TransactionRecord],
        current_status: str,
        current_actual: float,
        threshold: float,
        operator: str = "<="
    ) -> Optional[str]:
        if not covenant.is_marginal_single_txn:
            return None

        if not transactions:
            return None

        target_status = "COMPLIANT" if current_status == "BREACH" else "BREACH"
        marginal_candidates: List[str] = []

        for txn in transactions:
            amount = abs(txn.amount)
            # Evaluate actual if this transaction is excluded
            new_actual = current_actual - amount

            is_new_compliant = self._evaluate_condition(new_actual, threshold, operator)
            new_status = "COMPLIANT" if is_new_compliant else "BREACH"

            if new_status == target_status:
                marginal_candidates.append(txn.txn_id)

        if len(marginal_candidates) == 1:
            logger.info(
                f"Found unique bi-directional evidence transaction {marginal_candidates[0]} "
                f"flipping verdict from {current_status} to {target_status}."
            )
            return marginal_candidates[0]

        if len(marginal_candidates) > 1:
            logger.warning(
                f"Multiple ({len(marginal_candidates)}) transactions flip status for clause {covenant.clause_number}. "
                "Returning None per specification."
            )

        return None

    def _evaluate_condition(self, val: float, threshold: float, operator: str) -> bool:
        if operator in ("<=", "LE", "LESS_EQUAL"):
            return val <= threshold
        elif operator in ("<", "LT", "LESS"):
            return val < threshold
        elif operator in (">=", "GE", "GREATER_EQUAL"):
            return val >= threshold
        elif operator in (">", "GT", "GREATER"):
            return val > threshold
        elif operator in ("==", "EQ", "EQUAL"):
            return val == threshold
        return val <= threshold
