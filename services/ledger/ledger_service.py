import os
import csv
import logging
from typing import Dict, List, Optional
from shared.schemas import TransactionRecord

logger = logging.getLogger(__name__)

TARGET_SCENARIOS = {
    "P1": "ACC-7801",
    "P2": "ACC-7802",
    "P3": "ACC-7803",
    "P4": "ACC-7804",
    "P5": "ACC-7805",
    "P6": "ACC-7806",
    "P7": "ACC-7807",
    "P8": "ACC-7808",
    "P9": "ACC-7809",
    "P10": "ACC-7810",
    "B1": "ACC-7201",
    "B4": "ACC-7204",
}


class LedgerService:
    def __init__(self, ledger_csv_path: str):
        self.ledger_csv_path = ledger_csv_path
        self.transactions: List[TransactionRecord] = []
        self.account_to_scenario: Dict[str, str] = {}
        self.scenario_to_account: Dict[str, str] = {}
        self.account_transactions: Dict[str, List[TransactionRecord]] = {}
        self._load_ledger()

    def _load_ledger(self):
        if not os.path.exists(self.ledger_csv_path):
            raise FileNotFoundError(f"Master ledger file not found at: {self.ledger_csv_path}")

        with open(self.ledger_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                txn_id = row["txn_id"].strip()
                account_id = row["account_id"].strip()

                # Dynamically infer scenario_id from txn_id (e.g. TXN-P1-0039 -> P1, TXN-T1-0005 -> T1)
                parts = txn_id.split("-")
                if len(parts) >= 3 and parts[0].upper() == "TXN":
                    scen = parts[1].upper()
                    self.account_to_scenario[account_id] = scen
                    self.scenario_to_account[scen] = account_id

                raw_amount = row.get("amount", "").strip()
                try:
                    amount_val = float(raw_amount) if raw_amount else 0.0
                except ValueError:
                    amount_val = 0.0

                txn = TransactionRecord(
                    txn_id=txn_id,
                    date=row.get("date", "").strip(),
                    account_id=account_id,
                    counterparty=row.get("counterparty", "").strip(),
                    description=row.get("description", "").strip(),
                    amount=amount_val,
                    currency=row.get("currency", "USD").strip()
                )

                self.transactions.append(txn)
                if account_id not in self.account_transactions:
                    self.account_transactions[account_id] = []
                self.account_transactions[account_id].append(txn)

        logger.info(
            f"Loaded {len(self.transactions)} total ledger rows across {len(self.account_transactions)} accounts. "
            f"Mapped target scenarios: {len(self.account_to_scenario)}"
        )

    def get_transactions_for_scenario(self, scenario_id: str, excluded_txn_ids: Optional[List[str]] = None) -> List[TransactionRecord]:
        acc_id = self.scenario_to_account.get(scenario_id)
        if not acc_id:
            return []
        txns = self.account_transactions.get(acc_id, [])
        if excluded_txn_ids:
            excluded_set = set(excluded_txn_ids)
            return [t for t in txns if t.txn_id not in excluded_set]
        return txns

    def get_transactions_for_account(self, account_id: str, excluded_txn_ids: Optional[List[str]] = None) -> List[TransactionRecord]:
        txns = self.account_transactions.get(account_id, [])
        if excluded_txn_ids:
            excluded_set = set(excluded_txn_ids)
            return [t for t in txns if t.txn_id not in excluded_set]
        return txns

    def filter_by_keywords(self, txns: List[TransactionRecord], keywords: List[str]) -> List[TransactionRecord]:
        matched = []
        for t in txns:
            desc_lower = t.description.lower()
            cp_lower = t.counterparty.lower()
            if any(kw.lower() in desc_lower or kw.lower() in cp_lower for kw in keywords):
                matched.append(t)
        return matched

    def filter_by_counterparties(self, txns: List[TransactionRecord], counterparties: List[str]) -> List[TransactionRecord]:
        cps_lower = [c.lower() for c in counterparties]
        matched = []
        for t in txns:
            cp_lower = t.counterparty.lower()
            desc_lower = t.description.lower()
            if any(c in cp_lower or c in desc_lower for c in cps_lower):
                matched.append(t)
        return matched

    def sum_abs_amounts(self, txns: List[TransactionRecord]) -> float:
        return sum(abs(t.amount) for t in txns)
