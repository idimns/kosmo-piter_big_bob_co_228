# Как это работает изнутри

Подробное техническое описание внутреннего устройства «Топливного космоконтура»:
слои, поток данных, каждая стадия расчёта с формулами и ссылками на код,
инструменты анализа, импорт, API, фронтенд.

Ссылки на код даны в формате `путь:строка` относительно корня репозитория.

---

## 1. Архитектура: слои и зависимости

Система построена по принципу **чистого ядра**: вся математика в `engine/` не
зависит ни от веба, ни от базы, ни от файлов. Всё остальное — тонкие оболочки.

```
┌──────────────────────────────────────────────────────────────┐
│  frontend/ (React)      presentation/ (HTML)                   │  представление
├──────────────────────────────────────────────────────────────┤
│  api/app.py (FastAPI)        cli.py (argparse)                 │  оболочки
├──────────────────────────────────────────────────────────────┤
│  io/  loader · export · importer                              │  ввод-вывод
├──────────────────────────────────────────────────────────────┤
│  engine/  pipeline → availability · scenario · balance ·      │  ЯДРО
│           economics · constraints · risk                       │  (чистый Python)
│           optimizer · sensitivity · montecarlo                 │
├──────────────────────────────────────────────────────────────┤
│  model/entities.py (pydantic)      validation/                │  модель + проверка
└──────────────────────────────────────────────────────────────┘
```

**Правило зависимостей:** стрелки идут только вниз. `engine/` импортирует только
`model/`. `io/`, `api/`, `cli` импортируют `engine/` и `model/`. Ядро можно
запустить без единой веб-зависимости — это гарантирует, что числа не зависят от
способа вызова.

**Единый источник истины.** Любой расчёт возвращает один объект `Result`
(`engine/results.py:102`). CLI, API, выгрузка CSV/XLSX и фронтенд читают его же —
поэтому числа везде совпадают.

---

## 2. Модель данных (`model/entities.py`)

Все структуры — pydantic-модели (валидация на входе). Три статуса параметра
(`ParamStatus`, `entities.py:19`):

- **CASE** — исходное условие кейса, неизменно в контрольных расчётах;
- **DECISION** — решение пользователя (что заказать, что зарезервировать, во что
  инвестировать);
- **ASSUMPTION** — допущение команды (например, ставка дисконтирования).

Ключевые сущности:

| Класс | Назначение | Важные поля/методы |
|---|---|---|
| `DemandYear` | спрос за год | `base_total, critical, low_total, high_total`; валидатор «критический ≤ общего» (`entities.py:33`) |
| `Demand` | спрос по годам | `total(year, variant)`, `critical(year, variant)` — варианты base/low/high (`entities.py:47`) |
| `Channel` | канал снабжения | `capacity, var_cost, reservation_rate, take_or_pay, lead_time_months, reliability, available_from, requires`; `reliability_for(year, first_active_year)` |
| `Storage` | хранилище | `base` + опциональный `zbo_upgrade` (ёмкость, потери, стоимость хранения) |
| `Investment` | инвестиция | `capex, available_from, finance_before, commissioning_from, extra_opex` |
| `Constraints` | ограничения | сервис 99/97%, CAPEX 1800/2800, резерв 45 дн, лимит Emergency |
| `CaseData` | корневой контейнер | `channel(id)`, `investment(id)` — доступ по id |
| `ScenarioDef` | сценарий | `demand_variant`, `transforms[]`, `discounting` |
| `Decision` | план пользователя | `initial_stock, use_zbo, investments{id:год}, plan{год:[ChannelDecision]}` |
| `ChannelDecision` | решение по каналу/году | `reserved_capacity, ordered` (валидатор ≥ 0) |

**Тонкость с критическим спросом в low/high** (`entities.py:58`): доля
критического сохраняется от базового года — `critical_low = low_total × (critical_base / base_total)`.
Это предотвращает искажение приоритетного спроса при вариации.

**Тонкость с надёжностью канала.** Профиль `reliability` — словарь. Ключи: `first_year`
(первый год работы), `default`, либо абсолютные годы (`"2038"`). Метод
`reliability_for` разрешает нужное значение с учётом года ввода.

---

## 3. Поток данных: от файла до результата

```
data/case.yaml ──load_case()──► CaseData ─┐
configs/*.yaml ──load_scenarios()──► ScenarioDef ─┤
results/plan_*.json ──load_decision()──► Decision ─┤
                                                    ▼
                                        evaluate_plan(case, decision, scenario)
                                                    │  (pipeline.py:19)
                        ┌───────────────────────────┼───────────────────────────┐
                        ▼                            ▼                           ▼
                 compute_balance            compute_economics              check_all
                 (7 стадий физики)          (экономика)                    (ограничения)
                        │                            │                           │
                        └────────────► build_risk_register ◄────────────────────┘
                                                    ▼
                                                 Result
                                    (годы, экономика, нарушения, риски, feasible)
                                                    ▼
                        ┌───────────────┬───────────┴───────────┬──────────────┐
                        ▼               ▼                       ▼              ▼
                   CLI (print)    API (JSON)          export (CSV/XLSX)   frontend
```

Загрузчики — `io/loader.py`. Оркестратор — `engine/pipeline.py:evaluate_plan`.

---

## 4. Конвейер расчёта: 7 стадий

Оркестратор `evaluate_plan` (`pipeline.py:19`) вызывает стадии в порядке:
**balance → economics → constraints → risk**. Стадии 1 (availability) и 7
(scenario-transforms) вызываются изнутри balance. Разберём каждую.

### Стадия 1 — Доступность каналов (`availability.py`)

Определяет, сколько канал **может** дать в году (потолок мощности), с учётом трёх
ворот (`channel_available`, `availability.py:18`):

1. **Год ввода:** если `year < available_from` → 0 (например, ISRU до 2038).
2. **Инвестиционные ворота:** если канал `requires` инвестицию, она должна быть в
   `decision.investments` И год ≥ `commissioning_from`.
3. Иначе доступна полная `capacity`.

`first_active_year` (`availability.py:50`) находит первый доступный год — нужно для
надёжности «первого года» (напр. Earth-New 0.88 в первый год работы).

### Стадия 7 (частично) — Сценарные трансформации (`scenario.py`)

Класс `EffectiveDemand` (`scenario.py:16`) считает спрос **на лету**, не мутируя
`CaseData` (изоляция сценариев). Собирает множители из `transforms`:

- `demand_multiplier` (стресс): с указанного года спрос × коэффициент (×1.15 с 2038).
- `isru_actual_supply`: фактические доли поставки ISRU по годам.

`isru_actual_shares` (`scenario.py:45`) отдаёт доли ISRU для стресса. **Критично:**
эти доли применяются к мощности ОДИН раз и НЕ умножаются повторно на надёжность
(защита от двойного учёта, контрольный пример V10).

### Стадия 2 — Материальный баланс (`balance.py`)

Сердце физики. Прогон по годам (`compute_balance`, `balance.py:60`). Для каждого года:

**Тождество баланса:**
```
запас_конец = запас_начало + поступление − потери − выдача
```

Пошагово в коде:
1. `stock_start` = запас с прошлого года (первый год = `initial_stock`).
2. Для каждого канала считается `delivered` (`_delivered_for_channel`, `balance.py:43`):
   - `planned = min(заказ, доступная_мощность)`;
   - для ISRU в стрессе: `min(planned, мощность × доля_года)`.
3. `inflow` = сумма delivered по каналам.
4. **Потери:** `losses = inflow × loss_rate` — на валовое поступление, ОДИН раз
   (`balance.py:97`). Ставка: 4.5% базово, 1.2% после ZBO (`storage_loss_rate`).
5. `available_to_issue = stock_start + inflow − losses`.
6. **Выдача:** `issued = min(спрос, max(available_to_issue, 0))`.
7. **Критический сервис:** `served_critical = min(спрос_крит, issued)` — критический
   вложен в общий, приоритетно.
8. **Дефицит:** `shortage = max(спрос − issued, 0)`.
9. **Запас конец:** `max(available_to_issue − issued, 0)` — отрицательного запаса не
   бывает, это дефицит.

Результат — список `YearRow` (`results.py:22`) с потоками по каналам.

### Стадия 3 — Обслуживание спроса

Не отдельный файл — доли сервиса вычисляются как свойства `YearRow`
(`results.py:42`):
```
service_total_ratio    = served_total / demand_total
service_critical_ratio = served_critical / demand_critical
```

### Стадия 4 — Экономика (`economics.py`)

Считает пять статей расходов по годам (`compute_economics`, `economics.py:96`):

**Переменный платёж** (`variable_payment`, `economics.py:27`):
```
цена × max(отбор, take_or_pay × зарезервированная_мощность)
```
take-or-pay внутри `max`, не прибавляется вторым разом (V03/V04).

**Плата за резерв** (`reservation_payment`, `economics.py:39`):
```
тариф × зарезервированная_мощность × доля_года
```

**Хранение** (`_avg_physical_stock`, `economics.py:61`):
```
storage_cost × (запас_начало + запас_конец) / 2
```

**CAPEX** (`_capex_schedule`, `economics.py:70`): начисляется в год финансирования
инвестиции (для ISRU — до commissioning).

**OPEX** (`_opex_for_year`, `economics.py:84`): постоянный после ввода (ZBO, ISRU).

**Суммарные и дисконтированные** (`economics.py:135`):
```
год_итого = capex + переменные + резерв + хранение + opex
дисконт   = год_итого / (1 + ставка)^t,  t = год − base_year + 1 (end_of_year)
```
ToP уже внутри `var_total` — отдельно не плюсуется. Плюс `cost_per_ton_served` и
накопленный CAPEX для проверки лимитов.

### Стадия 5 — Проверка ограничений (`constraints.py`)

`check_all` (`constraints.py:131`) собирает нарушения из пяти проверок:

| Проверка | Функция | Уровень | Условие |
|---|---|---|---|
| Сервис 99%/97% | `_check_service` | error (стандарт) / warning (стресс) | ratio < лимит |
| CAPEX 1800/2800 | `_check_capex` | error | накопленный > лимит |
| Ёмкость + мощность | `_check_capacity_and_storage` | error | запас > ёмкости; заказ > мощности |
| Резерв 45 дней | `_check_reserve` | warning | `stock_start < спрос×45/365` |
| Emergency ≤ 2 лет | `_check_emergency` | error | E как основной (>50% отбора) >2 лет подряд |

Каждое нарушение — `Violation{year, kind, severity, value, limit, message}`
(`results.py:73`). **Ключевое различие уровней:** в стандартном сценарии недобор
сервиса — `error` (план неисполним); в стрессе — `warning` (ориентир). Это задаётся
флагом `is_standard` в `pipeline.py:26`.

### Стадия 6 — Риски (`risk.py`)

`build_risk_register` (`risk.py:24`) строит реестр по надёжности каналов.
**Принципиально:** надёжность живёт здесь, а НЕ в балансе (в стандартном расчёте
поставки идут по плану). Формула ожидаемого недобора:
```
E[недопоставка] = Σ поставка(год) × (1 − надёжность(год))
```
Это метрика риска, она НЕ вычитается из баланса (иначе двойной учёт со стрессом
ISRU). Каждая запись — `RiskEntry` с вероятностью, ожидаемым ущербом, мерой.

### Сборка результата

`evaluate_plan` (`pipeline.py:33`) собирает `Result`, ставит `feasible = not
has_errors` (наличие хоть одного `error`-нарушения делает план неисполнимым).

---

## 5. Система сценариев

Сценарий (`ScenarioDef`) = вариант спроса + список трансформаций + параметры
дисконтирования. Четыре конфига в `configs/`:

| Сценарий | demand_variant | transforms |
|---|---|---|
| `standard` | base | — |
| `stress` | base | demand ×1.15 с 2038 + доли ISRU |
| `low` | low | — |
| `high` | high | — |

Один и тот же `Decision` (план) прогоняется через разные сценарии на общей базе.
`compare` (`pipeline.py:62`) считает год-к-году разницу двух прогонов.

---

## 6. Оптимизатор (`engine/optimizer.py`)

MILP на PuLP + солвер CBC. Отвечает на вопрос «а план оптимален?».

**Схема «оптимизатор предлагает — ядро проверяет»** (`optimize_and_verify`):
1. MILP минимизирует дисконтированные расходы при всех ограничениях.
2. Найденный план прогоняется через **настоящий движок** (`evaluate_plan`).
3. Если движок нашёл ошибки — увеличивается страховочный запас (margin) к порогам
   сервиса, MILP решается заново (repair loop, до 6 итераций).
4. Итоговая цена — всегда из движка; MILP-значение — сертифицированная **оценка
   снизу** (lower bound), из неё считается зазор до оптимума.

**Переменные:** `order[год,канал]`, `reserved[год,канал]`, `payable` (линеаризация
take-or-pay через эпиграф: `payable ≥ order`, `payable ≥ top×reserved`), `stock`,
`issued`, бинарные `build[инвестиция]`, `use_zbo`.

**Линеаризации:** ZBO-потери (билинейность `inflow×zbo`) — через big-M; хранение —
по среднему `(stock_start+stock_end)/2`; ISRU-ворота — блокировка потока до
commissioning.

Результат на стандартном сценарии: зазор ≤ 4.5%.

---

## 7. Анализ чувствительности (`engine/sensitivity.py`)

Детерминированный (без случайности). Прогоняет план через движок, варьируя один
параметр по сетке на **копии** кейса:

- `sweep_channel_price` — цена канала × набор множителей;
- `sweep_demand` — спрос × множитель;
- `sweep_isru_reliability` — надёжность ISRU первого года;
- `tornado` — для каждого фактора считает разброс (swing) расходов при ±delta,
  сортирует по влиянию. Показывает, что цена Earth-Core — главный драйвер.

---

## 8. Монте-Карло риски (`engine/montecarlo.py`)

Вероятностный блок поверх детерминированного расчёта (не меняет базовый).
`run_montecarlo`:
1. Для каждого прогона (по умолчанию 3000) и каждого канала/года: с вероятностью
   `1 − надёжность` канал «сбоит» и даёт половину планового объёма.
2. Прогоняется упрощённый баланс, меряется дефицит.
3. Агрегируются: `P(критич. соблюдён)`, `P(общий соблюдён)`, средний дефицит,
   медиана, **95-й перцентиль (VaR)**, максимум, средний/худший годовой сервис.

**Детерминизм по seed** (`random.Random(seed)`): те же числа при повторе — критично
для воспроизводимости.

---

## 9. Импорт данных (`io/importer.py`)

Гибкий импорт CSV/XLSX без строгой структуры.

**Нормализация заголовков** (`norm`): нижний регистр, ё→е, убираются единицы в
скобках и пунктуация. `"Capacity (t/year)"` → `"capacity t year"`.

**Фаззи-матчинг** (`guess_role`): словарь синонимов `FIELD_SYNONYMS` (RU/EN)
сопоставляет колонку с ролью (`capacity`, `var_cost`, `take_or_pay`, …) по самому
длинному совпавшему синониму.

**Определение типа таблицы** (`detect_table_type`): по набору распознанных ролей —
сигнатуры `TABLE_SIGNATURES` (demand/channels/storage/investments/constraints).
Спец-правила: constraints перебивает demand при наличии metric+operator+value.

**Чтение** (`read_table`): CSV с автоопределением разделителя (`,`/`;`/таб), XLSX —
лист с наибольшим числом непустых ячеек. `read_all_sheets` читает все листы.

**Многолистовой импорт** (`build_all_pieces`): один XLSX → все таблицы разом
(demand + channels + storage + investments).

**Специальные парсеры:**
- `parse_reliability` — `"constant:0.96"`, `"first_operating_year:0.88;later:0.94"`,
  `"2038:0.78;2039:0.90"`;
- недели → месяцы для lead time;
- `_canon_investment_id` — алиасы (`EARTH_NEW` → `earth_new_option`);
- инференс `requires` для известных каналов (C→earth_new_option, D→isru_pilot).

Применение (в API) — **мердж по id**: частичный файл обновляет только пришедшие
записи, остальные сохраняются.

---

## 10. API (`api/app.py`)

FastAPI поверх ядра. Рабочий кейс хранится в изменяемом контейнере `state["case"]`,
чтобы импорт мог его заменить (`cur_case()`).

| Эндпоинт | Назначение |
|---|---|
| `GET /api/case` | данные кейса |
| `GET /api/scenarios` | список сценариев |
| `POST /api/plan/evaluate` | план + сценарий → Result |
| `POST /api/scenario/compare` | standard vs stress + diff |
| `GET/POST /api/plans[/{name}]` | список/загрузка/сохранение планов |
| `POST /api/export?fmt=` | выгрузка CSV/XLSX |
| `POST /api/geopolitical/apply` | ценовой шок на копии |
| `POST /api/optimize` | MILP-оптимум |
| `POST /api/sensitivity` | торнадо-анализ |
| `POST /api/montecarlo` | вероятностные риски |
| `POST /api/import/preview[-all]` | распознавание файла |
| `POST /api/import/apply` | применить (мердж по id) |
| `POST /api/import/reset` | вернуть исходные данные |

**Защита ввода** (`_validate_plan`): план со ссылкой на несуществующий канал/
инвестицию → понятная 422, а не 500. `_parse_decision` приводит year-ключи из JSON
(строки) к int. Собранный фронт из `frontend/dist` раздаётся тем же процессом
(`StaticFiles`) — один порт для API и интерфейса.

---

## 11. CLI (`cli.py`)

Запуск без интерфейса — для воспроизводимости и автоматизации:

```
python -m fuelcontour show-case       # данные кейса
python -m fuelcontour run --scenario <id> --plan <json>
python -m fuelcontour compare --plan <json>
python -m fuelcontour validate        # контрольные примеры V01-V10
python -m fuelcontour optimize --scenario <id> --save <json>
python -m fuelcontour sensitivity --plan <json>
python -m fuelcontour montecarlo --plan <json> --trials N --seed S
```

Точка входа `main` (`cli.py`) через argparse-субкоманды; те же функции движка, что
и в API.

---

## 12. Фронтенд (`frontend/`)

React + Vite, без роутера — навигация по экранам через `useState` в `App.jsx`.
Тонкий клиент: вся логика на бэке, фронт только рисует `Result`.

- `api.js` — обёртки над fetch (evaluate, compare, export, import, optimize…).
- `App.jsx` — состояние (кейс, план, сценарий, результат), автопересчёт при
  изменении плана/сценария через `useEffect`.
- `screens/` — 7 экранов: DataScreen, ImportScreen, DecisionsScreen, Dashboard,
  ViolationsScreen, CompareScreen, GeoScreen.
- Графики — Recharts; таблицы — вручную; стили — `styles.css` (тёмная тема, без
  UI-фреймворка).

Сборка `npm run build` → `frontend/dist` → раздаётся FastAPI. Один процесс.

---

## 13. Проверка (`validation/` + `src/fuelcontour/validation/`)

- `validation/expected_checks.json` — эталонные ожидаемые значения V01–V10.
- `validation/case_inputs.json` — входы примеров.
- `src/fuelcontour/validation/__init__.py` — `run_validation` читает оба файла и
  считает каждый пример **функциями движка** (`variable_payment`,
  `reservation_payment` и т.д.), сверяет с эталоном. Команда `validate` → 10/10.

Плюс 74 автотеста в `tests/` (баланс, экономика, ограничения, импорт, оптимизатор,
чувствительность, Монте-Карло, API, V01–V10).

---

## 14. Инварианты корректности (анти-двойной-учёт)

Четыре принципа, зашитые в код и защищённые тестами:

1. **Потери — один раз** на валовое поступление, не на остаток (`balance.py:97`;
   тест V06).
2. **Take-or-pay через `max`**, не сумма (`economics.py:34`; V03/V04).
3. **Надёжность ≠ множитель поставки** — живёт в блоке рисков, стрессовые доли ISRU
   не умножаются повторно (`risk.py`, `scenario.py:45`; V10).
4. **Резерв мощности ≠ физический запас** — разные сущности, не суммируются
   (`ChannelDecision.reserved_capacity` vs `stock`).

Плюс: отрицательного запаса не бывает (дефицит), запас ≤ ёмкости, критический
спрос вложен в общий (V01, V02, V09).

---

## 15. Карта репозитория

```
src/fuelcontour/
  model/entities.py       все pydantic-сущности + три статуса параметра
  engine/
    results.py            Result, YearRow, EconomicsResult, Violation, RiskEntry
    availability.py       стадия 1: доступность каналов
    scenario.py           стадия 7: EffectiveDemand, доли ISRU
    balance.py            стадия 2: материальный баланс
    economics.py          стадия 4: экономика (все формулы платежей)
    constraints.py        стадия 5: проверка ограничений
    risk.py               стадия 6: реестр рисков
    pipeline.py           оркестратор evaluate_plan + compare
    optimizer.py          MILP (PuLP/CBC) + repair loop
    sensitivity.py        свипы + торнадо
    montecarlo.py         вероятностные риски + VaR
    geopolitical.py       ценовые шоки на копии
  io/
    loader.py             load_case/scenarios/decision
    export.py             CSV/XLSX выгрузка
    importer.py           гибкий импорт (фаззи-матчинг, многолистовой)
  api/app.py              FastAPI, все эндпоинты
  cli.py                  командная строка
  validation/             прогон V01-V10 через движок
data/case.yaml            исходные условия
configs/                  standard, stress, low, high
results/                  планы + выгрузки
validation/               эталонные векторы V01-V10
tests/                    74 теста
frontend/                 React + Vite
presentation/             автономная HTML-презентация
docs/                     документация
```

---

## 16. Точки расширения

- **Новый канал / год:** добавить в `data/case.yaml` — логику не трогать
  (масштабируемость через данные).
- **Новый сценарий:** добавить `configs/<id>.yaml` с `demand_variant` и
  `transforms`.
- **Новая трансформация:** добавить тип в `scenario.py` (`_build_multipliers` или
  новый обработчик).
- **Новая проверка:** добавить `_check_*` в `constraints.py` и подключить в
  `check_all`.
- **Новый источник данных импорта:** расширить `FIELD_SYNONYMS` и
  `TABLE_SIGNATURES` в `importer.py`.

Все расширения не затрагивают ядро расчёта — это следствие слоистой архитектуры.
