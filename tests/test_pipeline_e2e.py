import os
import json
import pytest
from services.orchestrator.runner import PipelineRunner
from scripts.validate_submission import validate_submission_file


def test_pipeline_e2e_execution(tmp_path):
    output_json = tmp_path / "submission.json"

    runner = PipelineRunner(
        docs_dir="docs/agentic-bank-public/documents",
        ledger_path="docs/agentic-bank-public/master_ledger_2025.csv",
        template_path="docs/agentic-bank-public/submission_template.json",
        output_path=str(output_json)
    )

    result_dict = runner.run()

    assert os.path.exists(output_json)
    assert result_dict["team"] is not None
    assert "answers" in result_dict
    assert len(result_dict["answers"]) == 12

    # Validate output structure
    is_valid = validate_submission_file(str(output_json))
    assert is_valid is True
