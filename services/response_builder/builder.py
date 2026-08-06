import os
import json
import logging
from typing import Dict, Any
from shared.schemas import CovenantAnswer

logger = logging.getLogger(__name__)

DEFAULT_TEAM = "AI-Covenant-Team"
DEFAULT_EMAIL = "ai-team@halyk-challenge.kz"
DEFAULT_MODEL = "claude-3.5-sonnet"


class ResponseBuilder:
    def __init__(self, template_path: str):
        self.template_path = template_path
        if not os.path.exists(self.template_path):
            raise FileNotFoundError(f"Submission template file not found at: {self.template_path}")

        with open(self.template_path, "r", encoding="utf-8") as f:
            self.template_data = json.load(f)

    def build_submission(
        self,
        answers: Dict[str, Dict[str, CovenantAnswer]],
        team: str = DEFAULT_TEAM,
        contact_email: str = DEFAULT_EMAIL,
        model: str = DEFAULT_MODEL
    ) -> Dict[str, Any]:
        submission = json.loads(json.dumps(self.template_data))

        submission["team"] = team
        submission["contact_email"] = contact_email
        submission["model"] = model

        missing_scenarios = []
        missing_clauses = []

        for scenario_id, clauses in submission["answers"].items():
            if scenario_id not in answers:
                missing_scenarios.append(scenario_id)
                # Fallback default values for missing scenario
                for clause_no in clauses.keys():
                    clauses[clause_no] = {
                        "status": "COMPLIANT",
                        "actual": 0.0,
                        "evidence_txn_id": None
                    }
                continue

            scenario_answers = answers[scenario_id]
            for clause_no in clauses.keys():
                if clause_no not in scenario_answers:
                    missing_clauses.append(f"{scenario_id}:{clause_no}")
                    clauses[clause_no] = {
                        "status": "COMPLIANT",
                        "actual": 0.0,
                        "evidence_txn_id": None
                    }
                else:
                    ans: CovenantAnswer = scenario_answers[clause_no]
                    clauses[clause_no] = {
                        "status": ans.status,
                        "actual": float(ans.actual),
                        "evidence_txn_id": ans.evidence_txn_id
                    }

        if missing_scenarios:
            logger.warning(f"Missing answers for scenarios: {missing_scenarios}, populated fallback defaults.")
        if missing_clauses:
            logger.warning(f"Missing answers for clauses: {missing_clauses}, populated fallback defaults.")

        return submission

    def save_submission(
        self,
        submission_dict: Dict[str, Any],
        output_path: str = "submission.json"
    ) -> None:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(submission_dict, f, indent=2, ensure_ascii=False)
        logger.info(f"Successfully saved submission to {output_path}")
