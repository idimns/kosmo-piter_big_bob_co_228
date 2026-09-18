import React from 'react'

// экран данных кейса. параметры статуса 'case' - только чтение (Правило 4).
// задача экрана - дать оператору быстро понять "что за каналы и спрос".

// короткие характеристики каналов, чтобы не читать таблицу как справочник.
// подбираются по данным (не хардкод конкретных id, а пороги).
function channelTags(c) {
  const tags = []
  if (c.var_cost <= 4) tags.push({ t: 'дешёвый', cls: 'ok' })
  else if (c.var_cost >= 12) tags.push({ t: 'дорогой', cls: 'err' })
  if (c.take_or_pay >= 0.5) tags.push({ t: 'take-or-pay ' + (c.take_or_pay * 100).toFixed(0) + '%', cls: 'warn' })
  if (c.lead_time_months <= 2) tags.push({ t: 'быстрый', cls: 'ok' })
  else if (c.lead_time_months >= 18) tags.push({ t: 'долгий ввод', cls: 'warn' })
  if (c.requires) tags.push({ t: 'нужна инвестиция', cls: 'warn' })
  if (c.available_from) tags.push({ t: 'с ' + c.available_from, cls: 'warn' })
  return tags
}

function Tag({ t, cls }) {
  const color = cls === 'ok' ? '#3fb950' : cls === 'err' ? '#f85149' : '#d29922'
  return (
    <span style={{
      display: 'inline-block', padding: '1px 7px', marginRight: 5, marginTop: 3,
      fontSize: 11, borderRadius: 3, border: '1px solid ' + color, color,
    }}>{t}</span>
  )
}

export default function DataScreen({ caseData }) {
  const years = Object.keys(caseData.demand.years).sort()
  const first = caseData.demand.years[years[0]]
  const last = caseData.demand.years[years[years.length - 1]]
  const growth = (last.base_total / first.base_total).toFixed(1)

  return (
    <div>
      <div className="panel">
        <h3>Исходные условия кейса <span className="hint">(статус: case — только чтение)</span></h3>
        <p style={{ color: 'var(--muted)', margin: '4px 0 0', lineHeight: 1.5 }}>
          Оператор орбитального топливного узла планирует снабжение на 2035–2040.
          Спрос растёт в <b>{growth}×</b> ({first.base_total} → {last.base_total} т/год),
          доступны 5 каналов с разной ценой, надёжностью и условиями. Задача — собрать
          исполнимый план на вкладке «Решения».
        </p>
      </div>

      <div className="panel">
        <h3>Каналы снабжения</h3>
        <table>
          <thead>
            <tr>
              <th className="txt">Канал</th>
              <th className="txt">Характер</th>
              <th>Мощность</th>
              <th>Цена</th>
              <th>Резерв</th>
              <th>ToP</th>
              <th>Lead, мес</th>
            </tr>
          </thead>
          <tbody>
            {caseData.channels.map((c) => (
              <tr key={c.id}>
                <td className="txt"><b>{c.id}</b> {c.name}</td>
                <td className="txt">{channelTags(c).map((tg, i) => <Tag key={i} {...tg} />)}</td>
                <td>{c.capacity}</td>
                <td>{c.var_cost}</td>
                <td>{c.reservation_rate}</td>
                <td>{(c.take_or_pay * 100).toFixed(0)}%</td>
                <td>{c.lead_time_months}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="hint">
          Цена — млн у.е./т (агрегированная, с доставкой в узел). Резерв — млн у.е. за (т/год).
          ToP — take-or-pay (обязательный минимум оплаты).
        </div>
      </div>

      <div className="row">
        <div className="col panel">
          <h3>Спрос по годам</h3>
          <table>
            <thead>
              <tr>
                <th className="txt">Год</th>
                <th>Общий</th>
                <th>Критич.</th>
                <th>Низкий</th>
                <th>Высокий</th>
              </tr>
            </thead>
            <tbody>
              {years.map((y) => {
                const d = caseData.demand.years[y]
                return (
                  <tr key={y}>
                    <td className="txt">{y}</td>
                    <td>{d.base_total}</td>
                    <td>{d.critical}</td>
                    <td>{d.low_total}</td>
                    <td>{d.high_total}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <div className="hint">Критический спрос входит в общий (не суммируется поверх).</div>
        </div>

        <div className="col">
          <div className="panel">
            <h3>Хранилище</h3>
            <table>
              <tbody>
                <tr><td className="txt">Базовая ёмкость</td><td>{caseData.storage.base.capacity} т</td></tr>
                <tr><td className="txt">Потери (базово)</td><td>{(caseData.storage.base.loss_rate * 100).toFixed(1)}%</td></tr>
                <tr><td className="txt">Хранение</td><td>{caseData.storage.base.storage_cost} млн у.е./т-год</td></tr>
                {caseData.storage.zbo_upgrade && (
                  <>
                    <tr><td className="txt">ZBO: ёмкость</td><td>{caseData.storage.zbo_upgrade.capacity} т</td></tr>
                    <tr><td className="txt">ZBO: потери</td><td>{(caseData.storage.zbo_upgrade.loss_rate * 100).toFixed(1)}%</td></tr>
                  </>
                )}
              </tbody>
            </table>
          </div>

          <div className="panel">
            <h3>Инвестиции</h3>
            <table>
              <thead>
                <tr><th className="txt">Название</th><th>CAPEX</th></tr>
              </thead>
              <tbody>
                {caseData.investments.map((inv) => (
                  <tr key={inv.id}>
                    <td className="txt">{inv.name}</td>
                    <td>{inv.capex}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="panel">
        <h3>Обязательные ограничения</h3>
        <div className="row">
          <div className="kpi"><div className="label">Критич. сервис</div><div className="value ok">≥{(caseData.constraints.service_critical_min * 100).toFixed(0)}%</div></div>
          <div className="kpi"><div className="label">Общий сервис</div><div className="value ok">≥{(caseData.constraints.service_total_min * 100).toFixed(0)}%</div></div>
          <div className="kpi"><div className="label">CAPEX до 2037</div><div className="value">≤{caseData.constraints.capex_cap_2037}</div></div>
          <div className="kpi"><div className="label">CAPEX всего</div><div className="value">≤{caseData.constraints.capex_cap_2040}</div></div>
          <div className="kpi"><div className="label">Резерв запаса</div><div className="value">{caseData.constraints.reserve_days} дн</div></div>
        </div>
      </div>
    </div>
  )
}
