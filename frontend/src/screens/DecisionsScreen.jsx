import React from 'react'

// экран решений - тут пользователь строит план: заказы и резерв по каналам,
// инвестиции, ZBO. это DECISION-слой, всё меняется через интерфейс (Правило 4).
// главное для UX: сразу видно, покрывает ли план спрос года.

export default function DecisionsScreen({ caseData, decision, setDecision, result }) {
  const years = Object.keys(caseData.demand.years).map(Number).sort()
  const channels = caseData.channels

  function getCell(year, chId) {
    const list = decision.plan[year] || []
    return list.find((x) => x.channel_id === chId) || { channel_id: chId, reserved_capacity: 0, ordered: 0 }
  }

  function setCell(year, chId, field, value) {
    const v = parseFloat(value) || 0
    setDecision((prev) => {
      const plan = { ...prev.plan }
      const list = (plan[year] ? [...plan[year]] : [])
      let idx = list.findIndex((x) => x.channel_id === chId)
      if (idx === -1) {
        list.push({ channel_id: chId, reserved_capacity: 0, ordered: 0 })
        idx = list.length - 1
      }
      list[idx] = { ...list[idx], [field]: v }
      plan[year] = list
      return { ...prev, plan }
    })
  }

  function toggleInvestment(invId, year) {
    setDecision((prev) => {
      const inv = { ...prev.investments }
      if (inv[invId]) delete inv[invId]
      else inv[invId] = year
      return { ...prev, investments: inv }
    })
  }

  function setInitialStock(v) {
    setDecision((prev) => ({ ...prev, initial_stock: parseFloat(v) || 0 }))
  }

  function toggleZbo() {
    setDecision((prev) => ({ ...prev, use_zbo: !prev.use_zbo }))
  }

  // доступен ли канал в этом году (для подсказки в шапке столбца/ячейке)
  function channelAvailable(ch, year) {
    if (ch.available_from && year < ch.available_from) return false
    if (ch.requires && !decision.investments[ch.requires]) return false
    return true
  }

  // покрытие спроса по годам берём из result (если посчитан)
  function coverage(year) {
    if (!result) return null
    const r = result.years.find((x) => x.year === year)
    return r ? r.service_total_ratio : null
  }
  function demandOf(year) {
    if (result) {
      const r = result.years.find((x) => x.year === year)
      if (r) return r.demand_total
    }
    return caseData.demand.years[year].base_total
  }

  return (
    <div>
      <div className="panel">
        <h3>Общие параметры плана</h3>
        <div className="row">
          <div>
            <label>Начальный запас, т</label><br />
            <input type="number" value={decision.initial_stock} onChange={(e) => setInitialStock(e.target.value)} />
            <div className="hint">закупка и резерв не бесплатны — входят в стоимость</div>
          </div>
          <div>
            <label>ZBO-модернизация</label><br />
            <button className={'btn ' + (decision.use_zbo ? '' : 'secondary')} onClick={toggleZbo}>
              {decision.use_zbo ? '✓ включена' : 'выключена'}
            </button>
            <div className="hint">ёмкость 70→120 т, потери 4.5%→1.2%</div>
          </div>
        </div>
      </div>

      <div className="panel">
        <h3>Инвестиционные ворота</h3>
        <div className="hint" style={{ marginBottom: 8 }}>
          Клик — реализовать/отменить. Разблокирует каналы и ёмкость. CAPEX учтётся в год реализации.
        </div>
        <div className="row">
          {caseData.investments.map((inv) => {
            const active = decision.investments[inv.id]
            return (
              <div key={inv.id} className="kpi" style={{ minWidth: 220 }}>
                <button
                  className={'btn ' + (active ? '' : 'secondary')}
                  style={{ width: '100%', textAlign: 'left' }}
                  onClick={() => toggleInvestment(inv.id, active || 2037)}
                >
                  {active ? '✓ ' : '○ '}{inv.name}
                </button>
                <div className="sub" style={{ marginTop: 6 }}>CAPEX {inv.capex} млн у.е.</div>
                {active && (
                  <div style={{ marginTop: 6 }}>
                    <label>год: </label>
                    <input type="number" value={active} style={{ width: 70 }}
                      onChange={(e) => toggleInvestment(inv.id, parseInt(e.target.value) || 2037)} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      <div className="panel">
        <h3>План поставок по каналам и годам</h3>
        <div className="hint" style={{ marginBottom: 10 }}>
          В каждой ячейке: верх — <b>заказ</b> (сколько отбираем), низ — <b>резерв мощности</b>.
          Резерв ≠ физический запас. Недоступные каналы затемнены.
        </div>
        <table>
          <thead>
            <tr>
              <th className="txt">Канал</th>
              {years.map((y) => <th key={y}>{y}</th>)}
            </tr>
          </thead>
          <tbody>
            {channels.map((ch) => (
              <tr key={ch.id}>
                <td className="txt"><b>{ch.id}</b> {ch.name}</td>
                {years.map((y) => {
                  const cell = getCell(y, ch.id)
                  const avail = channelAvailable(ch, y)
                  if (!avail) {
                    // канал недоступен - явно показываем, а не просто бледним
                    const why = ch.requires && !decision.investments[ch.requires]
                      ? 'нужна инвестиция ' + ch.requires
                      : 'доступен с ' + ch.available_from
                    return (
                      <td key={y} style={{ background: 'rgba(0,0,0,0.25)', color: '#5a6472', fontSize: 11 }} title={why}>
                        —
                      </td>
                    )
                  }
                  return (
                    <td key={y}>
                      <input
                        type="number" value={cell.ordered} title="заказ (отбор)"
                        onChange={(e) => setCell(y, ch.id, 'ordered', e.target.value)}
                        style={{ width: 60 }}
                      />
                      <br />
                      <input
                        type="number" value={cell.reserved_capacity} title="резерв мощности"
                        onChange={(e) => setCell(y, ch.id, 'reserved_capacity', e.target.value)}
                        style={{ width: 60, marginTop: 3, opacity: 0.75 }}
                      />
                    </td>
                  )
                })}
              </tr>
            ))}
            {/* строка спроса-цели */}
            <tr>
              <td className="txt"><b>Спрос (цель)</b></td>
              {years.map((y) => (
                <td key={y} style={{ color: 'var(--muted)' }}>{demandOf(y).toFixed(0)}</td>
              ))}
            </tr>
            {/* строка покрытия - сразу видно, добираем ли */}
            <tr>
              <td className="txt"><b>Покрытие</b></td>
              {years.map((y) => {
                const cov = coverage(y)
                if (cov === null) return <td key={y}>—</td>
                const ok = cov >= caseData.constraints.service_total_min
                return (
                  <td key={y} style={{ color: ok ? '#3fb950' : '#f85149', fontWeight: 600 }}>
                    {(cov * 100).toFixed(0)}%
                  </td>
                )
              })}
            </tr>
          </tbody>
        </table>
        <div className="hint">
          Строка «Покрытие» пересчитывается автоматически. Зелёный — спрос закрыт (≥{(caseData.constraints.service_total_min * 100).toFixed(0)}%),
          красный — недобор.
        </div>
      </div>
    </div>
  )
}
