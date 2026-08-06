import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from services.orchestrator.runner import PipelineRunner
from scripts.validate_submission import validate_submission_file
from scripts.score import score_submission

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def print_rich_banner():
    if not HAS_RICH:
        print("=" * 60)
        print(" HALYK AI CHALLENGE · AI COVENANT VERIFICATION AGENT ")
        print("=" * 60)
        return

    console = Console()
    console.print(
        Panel.fit(
            "[bold white]HALYK BANK · AI COVENANT VERIFICATION AGENT[/bold white]\n"
            "[green]Autonomous Corporate Credit Compliance & Risk Engine[/green]",
            style="bold green"
        )
    )


def print_rich_results_table(submission_dict):
    if not HAS_RICH:
        return

    console = Console()
    table = Table(title="Portfolio Covenant Verification Summary", show_header=True, header_style="bold magenta")
    table.add_column("Scenario ID", style="cyan", width=12)
    table.add_column("Clause 6.1", justify="center")
    table.add_column("Clause 6.2", justify="center")
    table.add_column("Clause 6.3", justify="center")
    table.add_column("Verdict Summary", style="bold")

    answers = submission_dict.get("answers", {})

    for scen_id in sorted(answers.keys()):
        clauses = answers[scen_id]
        c61 = clauses.get("6.1", {})
        c62 = clauses.get("6.2", {})
        c63 = clauses.get("6.3", {})

        s61 = f"[red]BREACH[/red] ({c61.get('actual')})" if c61.get("status") == "BREACH" else f"[green]OK[/green] ({c61.get('actual')})"
        s62 = f"[red]BREACH[/red] ({c62.get('actual')})" if c62.get("status") == "BREACH" else f"[green]OK[/green] ({c62.get('actual')})"
        s63 = f"[red]BREACH[/red] ({c63.get('actual')})" if c63.get("status") == "BREACH" else f"[green]OK[/green] ({c63.get('actual')})"

        breached = any(c.get("status") == "BREACH" for c in clauses.values())
        summary = "[bold red]RISK DETECTED[/bold red]" if breached else "[bold green]ALL COMPLIANT[/bold green]"

        table.add_row(scen_id, s61, s62, s63, summary)

    console.print(table)


def main():
    docs_dir = os.getenv("DOCUMENTS_DIR", "docs/agentic-bank-public/documents")
    ledger_path = os.getenv("MASTER_LEDGER_PATH", "docs/agentic-bank-public/master_ledger_2025.csv")
    template_path = os.getenv("SUBMISSION_TEMPLATE_PATH", "docs/agentic-bank-public/submission_template.json")
    output_path = os.getenv("SUBMISSION_OUTPUT_PATH", "submission.json")
    gt_path = os.getenv("GROUND_TRUTH_PATH", "docs/agentic-bank-public/ground_truth.json")

    print_rich_banner()

    runner = PipelineRunner(
        docs_dir=docs_dir,
        ledger_path=ledger_path,
        template_path=template_path,
        output_path=output_path
    )

    submission_dict = runner.run()

    print_rich_results_table(submission_dict)

    logger.info("Validating output submission.json...")
    is_valid = validate_submission_file(output_path)
    if not is_valid:
        logger.error("Submission validation failed!")
        sys.exit(1)

    if os.path.exists(gt_path):
        logger.info("Evaluating local accuracy score against ground_truth.json...")
        score_submission(output_path, gt_path)

    logger.info("Pipeline execution completed successfully!")


if __name__ == "__main__":
    main()
