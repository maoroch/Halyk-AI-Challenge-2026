import os
import json
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

EXPECTED_SCENARIOS = ["B1", "B4", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"]
EXPECTED_CLAUSES = ["6.1", "6.2", "6.3"]


def validate_submission_file(filepath: str = "submission.json") -> bool:
    if not os.path.exists(filepath):
        logger.error(f"Submission file {filepath} does not exist!")
        return False

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        return False

    # 1. Check top-level metadata
    for key in ["team", "contact_email", "model"]:
        val = data.get(key)
        if not val or not isinstance(val, str) or not val.strip():
            logger.error(f"Top-level field '{key}' is missing or empty!")
            return False

    if "answers" not in data or not isinstance(data["answers"], dict):
        logger.error("Missing or invalid 'answers' dictionary!")
        return False

    answers = data["answers"]
    errors = 0
    warnings = 0
    total_cells = 0

    # 2. Check 12 scenarios and 3 covenants each (36 cells total)
    for scenario_id in EXPECTED_SCENARIOS:
        if scenario_id not in answers:
            logger.error(f"Scenario '{scenario_id}' missing from answers!")
            errors += 1
            continue

        scen_answers = answers[scenario_id]
        for clause_no in EXPECTED_CLAUSES:
            total_cells += 1
            if clause_no not in scen_answers:
                logger.error(f"Clause '{clause_no}' missing in scenario '{scenario_id}'!")
                errors += 1
                continue

            cell = scen_answers[clause_no]
            if not isinstance(cell, dict):
                logger.error(f"Cell '{scenario_id}:{clause_no}' is not a dict!")
                errors += 1
                continue

            # Check status
            status = cell.get("status")
            if status not in ("COMPLIANT", "BREACH"):
                logger.error(f"Invalid status '{status}' in cell '{scenario_id}:{clause_no}' (must be COMPLIANT or BREACH)")
                errors += 1

            # Check actual value
            actual = cell.get("actual")
            if actual is None or not isinstance(actual, (int, float)) or actual < 0:
                logger.error(f"Invalid actual value '{actual}' in cell '{scenario_id}:{clause_no}' (must be positive float)")
                errors += 1
            else:
                # Precision check (2 decimal places)
                if round(actual, 2) != actual:
                    logger.warning(f"Cell '{scenario_id}:{clause_no}' actual '{actual}' is not rounded to 2 decimal places")
                    warnings += 1

                # Sanity check: zero actual value for revenue / overhead clauses
                if actual == 0.0 and clause_no in ("6.1", "6.2"):
                    logger.warning(f"Sanity Alert: Cell '{scenario_id}:{clause_no}' has actual value of 0.0")
                    warnings += 1

            # Check evidence_txn_id
            ev_id = cell.get("evidence_txn_id")
            if ev_id is not None:
                if not isinstance(ev_id, str) or not ev_id.startswith("TXN-"):
                    logger.error(f"Invalid evidence_txn_id format '{ev_id}' in cell '{scenario_id}:{clause_no}'")
                    errors += 1

    if errors > 0:
        logger.error(f"Validation failed with {errors} critical errors across {total_cells} cells.")
        return False

    logger.info(f"VALIDATION SUCCESS: {filepath} is 100% valid ({total_cells} cells verified, {warnings} sanity warnings).")
    return True


if __name__ == "__main__":
    sub_file = sys.argv[1] if len(sys.argv) > 1 else "submission.json"
    valid = validate_submission_file(sub_file)
    sys.exit(0 if valid else 1)
