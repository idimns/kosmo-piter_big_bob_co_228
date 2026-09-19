import React from 'react'

// экран решений - тут пользователь строит план: заказы и резерв по каналам,
// инвестиции, ZBO. это DECISION-слой, всё меняется через интерфейс.

export default function DecisionsScreen({ caseData, decision, setDecision }) {
  const years = Object.keys(caseData.demand.years).map(Number).sort()
  const channels = caseData.channels

  // получить решение по каналу в году (или дефолт)
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
      if (inv[invId]) {
        delete inv[invId]
      } else {
        inv[invId] = year
      }
      return { ...prev, investments: inv }
    })
  }

  function setInitialStock(v) {
    setDecision((prev) => ({ ...prev, initial_stock: parseFloat(v) || 0 }))
  }

  function toggleZbo() {
    setDecision((prev) => ({ ...prev, use_zbo: !prev.use_zbo }))
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
              {decision.use_zbo ? 'включена' : 'выключена'}
            </button>
          </div>
        </div>
      </div>

      <div className="panel">
        <h3>Инвестиционные решения (ворота)</h3>
        <div className="hint" style={{ marginBottom: 8 }}>
          Клик переключает реализацию. Год = когда финансируем/реализуем.
        </div>
        {caseData.investments.map((inv) => {
          const active = decision.investments[inv.id]
          return (
            <div key={inv.id} style={{ marginBottom: 8 }}>
              <button
                className={'btn ' + (active ? '' : 'secondary')}
                onClick={() => toggleInvestment(inv.id, active || 2037)}
              >
                {active ? '✓' : '○'} {inv.name} (CAPEX {inv.capex})
              </button>
              {active && (
                <>
                  {' '}год:{' '}
                  <input
                    type="number"
                    value={active}
                    onChange={(e) => toggleInvestment(inv.id, parseInt(e.target.value))}
                    style={{ width: 70 }}
                    onClickCapture={(e) => e.stopPropagation()}
                  />
                </>
              )}
            </div>
          )
        })}
      </div>

      <div className="panel">
        <h3>План поставок: заказ / резерв по каналам и годам</h3>
        <div className="hint" style={{ marginBottom: 8 }}>
          Верхнее поле — заказ (отбор), нижнее — резерв мощности. Резерв ≠ физический запас.
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
                <td className="txt">{ch.id} {ch.name}</td>
                {years.map((y) => {
                  const cell = getCell(y, ch.id)
                  return (
                    <td key={y}>
                      <input
                        type="number"
                        value={cell.ordered}
                        title="заказ (отбор)"
                        onChange={(e) => setCell(y, ch.id, 'ordered', e.target.value)}
                        style={{ width: 62 }}
                      />
                      <br />
                      <input
                        type="number"
                        value={cell.reserved_capacity}
                        title="резерв мощности"
                        onChange={(e) => setCell(y, ch.id, 'reserved_capacity', e.target.value)}
                        style={{ width: 62, marginTop: 3, opacity: 0.8 }}
                      />
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
