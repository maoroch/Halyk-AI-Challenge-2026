import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class DashboardGenerator:
    def __init__(self, output_path: str = "reports/dashboard.html"):
        self.output_path = output_path

    def generate_dashboard(self, submission_dict: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)

        answers = submission_dict.get("answers", {})
        total_cells = 0
        compliant_count = 0
        breach_count = 0

        red_flags = []

        for scen_id, clauses in answers.items():
            for clause_no, cell in clauses.items():
                total_cells += 1
                status = cell.get("status")
                if status == "COMPLIANT":
                    compliant_count += 1
                else:
                    breach_count += 1
                    red_flags.append({
                        "scenario_id": scen_id,
                        "clause": clause_no,
                        "actual": cell.get("actual"),
                        "evidence": cell.get("evidence_txn_id")
                    })

        comp_pct = round((compliant_count / total_cells) * 100, 1) if total_cells > 0 else 0.0

        red_flags_html = ""
        for rf in red_flags:
            red_flags_html += f"""
            <div style="background: #fff5f5; border-left: 4px solid #e53e3e; padding: 10px 15px; margin-bottom: 10px; border-radius: 4px;">
                <strong>Scenario {rf['scenario_id']} — Clause {rf['clause']}</strong>: BREACH detected! 
                Actual: <code>{rf['actual']}</code> | Evidence: <code>{rf['evidence'] or 'Aggregate'}</code>
            </div>
            """

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Executive Credit Risk Dashboard — Halyk AI</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f4f6f8; margin: 0; padding: 25px; }}
        .header {{ background: linear-gradient(135deg, #005f4b 0%, #00876c 100%); color: white; padding: 25px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); margin-bottom: 25px; }}
        .metrics {{ display: flex; gap: 20px; margin-bottom: 25px; }}
        .card {{ flex: 1; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.06); text-align: center; }}
        .card h2 {{ margin: 0; font-size: 32px; color: #005f4b; }}
        .card p {{ margin: 5px 0 0 0; color: #718096; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; }}
        .section {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.06); margin-bottom: 25px; }}
        h3 {{ margin-top: 0; color: #2d3748; border-bottom: 2px solid #edf2f7; padding-bottom: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="margin:0;">Halyk Bank · Executive Credit Risk Dashboard</h1>
        <p style="margin:5px 0 0 0;">Corporate Loan Portfolio Covenant Verification</p>
    </div>

    <div class="metrics">
        <div class="card">
            <h2>{len(answers)}</h2>
            <p>Borrower Scenarios</p>
        </div>
        <div class="card">
            <h2>{total_cells}</h2>
            <p>Total Covenants Evaluated</p>
        </div>
        <div class="card">
            <h2 style="color: #38a169;">{comp_pct}%</h2>
            <p>Compliance Rate</p>
        </div>
        <div class="card">
            <h2 style="color: #e53e3e;">{breach_count}</h2>
            <p>Covenant Breaches</p>
        </div>
    </div>

    <div class="section">
        <h3>🚨 Red Flag Risk Alerts</h3>
        {red_flags_html}
    </div>
</body>
</html>
"""

        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"Generated Executive Dashboard at {self.output_path}")
