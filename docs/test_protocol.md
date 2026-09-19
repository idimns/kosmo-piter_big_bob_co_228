# Протокол контрольных и стресс-тестов

Документ фиксирует результаты проверки расчётного ядра. Воспроизводится командами
ниже; числа детерминированы.

Дата генерации протокола: по состоянию репозитория. Среда: Python 3.12.

---

## 1. Контрольные примеры V01–V10

Официальные контрольные векторы (`validation/expected_checks.json`), прогнанные
расчётным ядром. Команда: `python -m fuelcontour validate`.

| ID | Что проверяет | Получено | Результат |
|---|---|---|---|
| V01 | материальный баланс | closing_inventory = 13 | OK |
| V02 | дефицит ≠ отрицательный запас | served 8, shortage 2, closing 0 | OK |
| V03 | take-or-pay минимум | payable 70, payment 140 | OK |
| V04 | ToP не удваивается | payment 140 | OK |
| V05 | резерв пропорционально | reservation 20 | OK |
| V06 | потери один раз | losses 1 | OK |
| V07 | 45-дневный резерв | reserve 45 | OK |
| V08 | превышение мощности | CAPACITY_EXCEEDED, excess 2 | OK |
| V09 | критический вложен в общий | total 100 | OK |
| V10 | stress-доля без ×reliability | delivery 10 | OK |

**Итог: 10/10 пройдено.**

---

## 2. Автотесты

Команда: `pytest`.

**Итог: 74 теста пройдено.** Покрытие: материальный баланс, экономика (take-or-pay,
резерв, хранение, дисконтирование), ограничения, импорт CSV/XLSX (в т.ч.
многолистовой), оптимизатор, чувствительность, Монте-Карло (детерминизм по seed),
API, контрольные примеры V01–V10.

Файлы тестов: `tests/test_balance.py`, `test_economics.py`, `test_constraints.py`,
`test_export_geo.py`, `test_api.py`, `test_importer.py`, `test_import_api.py`,
`test_optimization.py`, `test_control_cases.py`.

---

## 3. Прогон по сценариям (план `plan_recommended.json`)

Команда: `python -m fuelcontour run --scenario <id> --plan results/plan_recommended.json`.

| Сценарий | Расходы, млн | Дисконт., млн | Худший общий сервис | Худший критич. | Ошибки |
|---|---|---|---|---|---|
| low | 12 482,9 | 9 523,8 | 100,0% | 100,0% | 4 (переполнение склада) |
| standard | 12 030,0 | 9 194,4 | 100,0% | 100,0% | 0 |
| high | 11 851,3 | 9 063,4 | 84,1% | 100,0% | 0 (сервис — предупреждения) |
| stress | 11 912,1 | 9 112,7 | 93,0% | 100,0% | 0 |

Интерпретация — в `docs/scenario_comparison.md`.

---

## 4. Обязательный стресс-тест

Условия: с 2038 общий и критический спрос ×1,15; ISRU по фактическим долям
(0,78 / 0,90 / 0,93).

Результат рекомендуемого плана:
- критический сервис = 100% во все годы;
- общий сервис: 100% до 2038, 97,2% в 2039, 93,0% в 2040;
- ошибок ограничений нет (просадка общего сервиса — предупреждения, показаны
  численно).

---

## 5. Вероятностный стресс (Монте-Карло)

Команда: `python -m fuelcontour montecarlo --plan results/plan_recommended.json
--trials 3000 --seed 42`. Детерминирован по seed.

| Метрика | Значение |
|---|---|
| P(критич. соблюдён) | 90,5% |
| Средний дефицит | 76,9 т |
| 95-й перцентиль (VaR) | 168,3 т |

---

## 6. Как воспроизвести весь протокол

```bash
python -m fuelcontour validate                                   # V01-V10
pytest -q                                                        # автотесты
for s in low standard high stress; do \
  python -m fuelcontour run --scenario $s --plan results/plan_recommended.json; done
python -m fuelcontour compare --plan results/plan_recommended.json
python -m fuelcontour montecarlo --plan results/plan_recommended.json --trials 3000 --seed 42
```
