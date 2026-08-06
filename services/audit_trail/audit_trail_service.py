import os
import json
import logging
from typing import Dict, List, Any
from shared.schemas import CovenantClause, AuditAdjustment, KYCDossierInfo, TransactionRecord, CovenantAnswer

logger = logging.getLogger(__name__)


class AuditTrailService:
    def __init__(self, output_json_path: str = "audit_trail.json", output_html_path: str = "reports/audit_report.html"):
        self.output_json_path = output_json_path
        self.output_html_path = output_html_path
        self.records: List[Dict[str, Any]] = []

    def record_decision(
        self,
        scenario_id: str,
        account_id: str,
        company_name: str,
        clause: CovenantClause,
        answer: CovenantAnswer,
        transactions: List[TransactionRecord],
        source_doc_name: str = "Loan Agreement PDF",
        source_doc: str = None,
        audit: AuditAdjustment = None,
        kyc: KYCDossierInfo = None
    ) -> None:
        doc_name = source_doc or source_doc_name
        rec = {
            "scenario_id": scenario_id,
            "account_id": account_id,
            "company_name": company_name,
            "clause_number": clause.clause_number,
            "metric_name": clause.metric_name,
            "operator": clause.operator,
            "threshold": clause.threshold,
            "status": answer.status,
            "actual": answer.actual,
            "evidence_txn_id": answer.evidence_txn_id,
            "source_doc": doc_name,
            "auditor_exclusions": audit.excluded_txn_ids if audit else [],
            "auditor_addbacks": audit.ebitda_addbacks_total if audit else 0.0,
            "kyc_related_entities": kyc.related_parties_20plus if kyc else [],
            "txns_evaluated_count": len(transactions),
            "evidence_explanation": (
                f"Single marginal transaction {answer.evidence_txn_id} flips compliance verdict to COMPLIANT when removed."
                if answer.evidence_txn_id else "Aggregate/ratio test or no single transaction flips verdict."
            )
        }
        self.records.append(rec)

    def save_audit_trail(self) -> None:
        # Save JSON log
        with open(self.output_json_path, "w", encoding="utf-8") as f:
            json.dump({"audit_trail": self.records}, f, indent=2, ensure_ascii=False)

        # Generate HTML report
        os.makedirs(os.path.dirname(self.output_html_path), exist_ok=True)
        html_content = self._generate_html_report()
        with open(self.output_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"Saved audit trail to {self.output_json_path} and HTML report to {self.output_html_path}")

    def _generate_html_report(self) -> str:
        rows_html = ""
        for r in self.records:
            status_color = "#28a745" if r["status"] == "COMPLIANT" else "#dc3545"
            rows_html += f"""
            <tr>
                <td><b>{r["scenario_id"]}</b> ({r["account_id"]})</td>
                <td><b>Clause {r["clause_number"]}</b> ({r["metric_name"]})</td>
                <td><span style="color: {status_color}; font-weight: bold;">{r["status"]}</span></td>
                <td>{r["actual"]}</td>
                <td>{r["operator"]} {r["threshold"]}</td>
                <td><code>{r["evidence_txn_id"] or 'null'}</code></td>
                <td><small>{r["source_doc"]}<br>Exclusions: {', '.join(r["auditor_exclusions"]) or 'None'}</small></td>
            </tr>
            """

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Halyk Bank - Credit Covenant Audit Report</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f8f9fa; margin: 0; padding: 20px; }}
        .header {{ background: #005f4b; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        h1 {{ margin: 0; font-size: 24px; }}
        p {{ margin: 5px 0 0 0; opacity: 0.9; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #e9ecef; }}
        th {{ background: #e9ecef; color: #495057; font-size: 13px; text-transform: uppercase; }}
        tr:hover {{ background: #f1f3f5; }}
        code {{ background: #e9ecef; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Halyk Bank · AI Covenant Verification Compliance Report</h1>
        <p>Automated Credit Risk & Covenant Audit Trail</p>
    </div>
    <table>
        <thead>
            <tr>
                <th>Scenario / Account</th>
                <th>Covenant Clause</th>
                <th>Status</th>
                <th>Actual Value</th>
                <th>Threshold</th>
                <th>Evidence Txn</th>
                <th>Audit Context</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</body>
</html>
"""
