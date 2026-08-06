import os
import pytest
from shared.entity_normalizer import normalize_entity_name, is_entity_match
from services.currency.currency_service import CurrencyService
from services.audit_trail.audit_trail_service import AuditTrailService
from services.dashboard.dashboard_generator import DashboardGenerator


def test_entity_normalizer():
    norm1 = normalize_entity_name("Aktau Holdings LLP")
    norm2 = normalize_entity_name("Aktau Holdings L.L.P.")
    norm3 = normalize_entity_name("Aktau Holdings Inc")

    assert norm1 == "aktau"
    assert norm2 == "aktau"
    assert norm3 == "aktau"

    assert is_entity_match("Aktau Holdings LLP", "Aktau Holdings L.L.P.") is True
    assert is_entity_match("Kaspi Marine Engineering JSC", "Kaspi Marine Engineering LLP") is True


def test_currency_conversion():
    cs = CurrencyService()
    usd = cs.convert_to_usd(100.0, "USD")
    assert usd == 100.0

    kzt_in_usd = cs.convert_to_usd(48000.0, "KZT")
    assert round(kzt_in_usd, 0) == 100.0


def test_audit_trail_and_dashboard_generation(tmp_path):
    audit_json = tmp_path / "audit_trail.json"
    audit_html = tmp_path / "audit_report.html"
    dashboard_html = tmp_path / "dashboard.html"

    audit_svc = AuditTrailService(str(audit_json), str(audit_html))
    dash_gen = DashboardGenerator(str(dashboard_html))

    sub_dict = {
        "team": "TestTeam",
        "contact_email": "test@test.kz",
        "model": "claude-3.5-sonnet",
        "answers": {
            "P1": {
                "6.1": {"status": "BREACH", "actual": 0.46, "evidence_txn_id": None},
                "6.2": {"status": "COMPLIANT", "actual": 6842117.53, "evidence_txn_id": None},
                "6.3": {"status": "COMPLIANT", "actual": 283664.18, "evidence_txn_id": None}
            }
        }
    }

    dash_gen.generate_dashboard(sub_dict)
    assert os.path.exists(dashboard_html)
