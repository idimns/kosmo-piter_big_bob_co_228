"""Контрольные примеры организатора V01-V10 - управляемые данными.

Читаем validation/expected_checks.json (файл организатора) и прогоняем каждый
пример через наш движок (src/fuelcontour/validation). Плюс интеграционная
проверка полного MANDATORY_STRESS на реальных входах кейса (требование их README).
"""
import pytest
from pathlib import Path

from fuelcontour.validation import run_validation, summary
from fuelcontour.io.loader import load_case, load_scenarios, load_decision
from fuelcontour.engine.pipeline import evaluate_plan

ROOT = Path(__file__).resolve().parents[1]


def test_all_control_cases_pass():
    """Все V01-V10 воспроизводятся нашим движком (data-driven из их JSON)."""
    results = run_validation()
    s = summary(results)
    failed = [r.case_id for r in results if not r.passed]
    assert s["failed"] == 0, f"провалились: {failed}"
    assert s["passed"] == 10


@pytest.mark.parametrize("case_id", ["V01", "V02", "V03", "V04", "V05",
                                     "V06", "V07", "V08", "V09", "V10"])
def test_each_control_case(case_id):
    """Каждый пример отдельным тестом - чтобы падение было точечным."""
    results = {r.case_id: r for r in run_validation()}
    r = results[case_id]
    assert r.passed, f"{case_id}: получили {r.computed}, ждали {r.expected}"


def test_mandatory_stress_integration():
    """Интеграционная проверка полного MANDATORY_STRESS на реальных входах кейса.

    Требование README организатора: помимо V01-V10 нужна интеграционная проверка
    стресса на настоящих данных. Проверяем рекомендованный план.
    """
    case = load_case(ROOT / "data" / "case.yaml")
    scns = load_scenarios(ROOT / "configs")
    dec = load_decision(ROOT / "results" / "plan_recommended.json")
    res = evaluate_plan(case, dec, scns["stress"])

    # в стрессе критический спрос должен держаться 100% (главное свойство плана)
    for r in res.years:
        assert r.service_critical_ratio >= 0.999, \
            f"{r.year}: критический сервис {r.service_critical_ratio:.3f} < 100%"

    # план не должен иметь ошибок-нарушений (только warnings допустимы в стрессе)
    errors = [v for v in res.violations if v.severity == "error"]
    assert not errors, f"ошибки в стрессе: {[v.message for v in errors]}"

    # стресс с 2038 поднимает спрос x1.15 - проверяем что трансформация применена
    d2038 = next(r for r in res.years if r.year == 2038)
    assert abs(d2038.demand_total - 250 * 1.15) < 1e-6
