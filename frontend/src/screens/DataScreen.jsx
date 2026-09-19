import React from 'react'

// экран данных кейса. параметры статуса 'case' - только чтение.
export default function DataScreen({ caseData }) {
  const years = Object.keys(caseData.demand.years).sort()

  return (
    <div>
      <div className="panel">
        <h3>Спрос по годам <span className="hint">(исходные условия, только просмотр)</span></h3>
        <table>
          <thead>
            <tr>
              <th className="txt">Год</th>
              <th>Базовый общий</th>
              <th>Критический</th>
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
      </div>

      <div className="panel">
        <h3>Каналы снабжения</h3>
        <table>
          <thead>
            <tr>
              <th className="txt">ID</th>
              <th className="txt">Название</th>
              <th>Мощность</th>
              <th>Цена</th>
              <th>Резерв-ставка</th>
              <th>Take-or-pay</th>
              <th>Lead time, мес</th>
              <th>Доступен с</th>
            </tr>
          </thead>
          <tbody>
            {caseData.channels.map((c) => (
              <tr key={c.id}>
                <td className="txt">{c.id}</td>
                <td className="txt">{c.name}</td>
                <td>{c.capacity}</td>
                <td>{c.var_cost}</td>
                <td>{c.reservation_rate}</td>
                <td>{(c.take_or_pay * 100).toFixed(0)}%</td>
                <td>{c.lead_time_months}</td>
                <td>{c.available_from || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="hint">
          Цена — млн у.е./т (агрегированная, включает доставку в узел). Резерв-ставка — млн у.е. за (т/год).
        </div>
      </div>

      <div className="row">
        <div className="col panel">
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

        <div className="col panel">
          <h3>Инвестиции</h3>
          <table>
            <thead>
              <tr><th className="txt">ID</th><th className="txt">Название</th><th>CAPEX</th></tr>
            </thead>
            <tbody>
              {caseData.investments.map((inv) => (
                <tr key={inv.id}>
                  <td className="txt">{inv.id}</td>
                  <td className="txt">{inv.name}</td>
                  <td>{inv.capex}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h3>Ограничения</h3>
        <div className="row">
          <div className="kpi"><div className="label">Критич. сервис</div><div className="value">≥{(caseData.constraints.service_critical_min * 100).toFixed(0)}%</div></div>
          <div className="kpi"><div className="label">Общий сервис</div><div className="value">≥{(caseData.constraints.service_total_min * 100).toFixed(0)}%</div></div>
          <div className="kpi"><div className="label">CAPEX до 2037</div><div className="value">≤{caseData.constraints.capex_cap_2037}</div></div>
          <div className="kpi"><div className="label">CAPEX всего</div><div className="value">≤{caseData.constraints.capex_cap_2040}</div></div>
          <div className="kpi"><div className="label">Резерв</div><div className="value">{caseData.constraints.reserve_days} дн</div></div>
        </div>
      </div>
    </div>
  )
}
