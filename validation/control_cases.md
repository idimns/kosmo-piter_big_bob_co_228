# Синтетические контрольные примеры

Эти примеры проверяют арифметику и семантику реализации. Они **не** являются планом снабжения для конкурсного кейса и не используют реальную комбинацию источников.

## V01 — материальный баланс

```text
opening_inventory = 10 t
delivered = 30 t
losses = 2 t
served = 25 t
expected_closing_inventory = 13 t
```

Проверка: `10 + 30 - 2 - 25 = 13`.

## V02 — дефицит не является отрицательным запасом

```text
opening_inventory = 0 t
delivered = 8 t
losses = 0 t
demand = 10 t
expected_served = 8 t
expected_shortage = 2 t
expected_closing_inventory = 0 t
```

Физический остаток остаётся нулевым. Значение `-2 t` не должно выводиться как inventory.

## V03 — минимум take-or-pay

```text
reserved_capacity_period = 100 t
order = 50 t
take_or_pay_share = 0.70
price = 2 mln units/t
expected_payable_volume = 70 t
expected_variable_payment = 140 mln units
```

Проверка: `max(50, 0.70 * 100) = 70`; `70 * 2 = 140`.

## V04 — take-or-pay не начисляется дважды

Используются входы V03. Правильный `variable_payment` остаётся 140 млн у.е. Добавлять ещё `70 * 2` отдельной строкой нельзя.

## V05 — пропорциональная плата за резервирование

```text
annual_reserved_capacity = 100 t/year
reservation_rate = 0.4 mln units per t/year capacity
period_fraction = 0.5
expected_reservation_payment = 20 mln units
```

Проверка: `100 * 0.4 * 0.5 = 20`.

## V06 — потери начисляются на throughput один раз

```text
gross_inflow = 20 t
loss_rate = 0.05
expected_losses = 1 t
```

Проверка: `20 * 0.05 = 1`. Повторно применять те же 5% к closing stock для того же модельного механизма — ошибка двойного счёта.

## V07 — 45-дневный резерв

```text
annual_total_demand = 365 t
expected_45_day_reserve = 45 t
```

Проверка: `365 * 45 / 365 = 45`.

## V08 — превышение мощности

Синтетический источник: `capacity = 10 t/year`, `reserved = 12 t/year`. Ожидается `CAPACITY_EXCEEDED`, excess 2 t/year.

## V09 — критический спрос вложен в общий

`total_demand = 100 t`, `critical_demand = 60 t`. Ожидаемый общий спрос остаётся 100 т, а не 160 т.

## V10 — stress-delivery не умножается повторно на reliability

Синтетический пример, не совпадающий с конкурсными коэффициентами:

```text
planned_delivery = 20 t
mandatory_like_actual_delivery_share = 0.50
risk_metadata_reliability = 0.80
```

Ожидаемый фактический объём: `20 * 0.50 = 10 t`. Неверно автоматически получать `20 * 0.50 * 0.80 = 8 t`, если reliability относится к отдельному риск-блоку. Комбинированный stress возможен только как отдельный, явно определённый research scenario.
