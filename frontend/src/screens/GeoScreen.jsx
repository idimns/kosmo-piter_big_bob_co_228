import React, { useState } from 'react'
import * as api from '../api'

// геополитический блок: пользователь задаёт событие, каналы,
// направление и величину ценового шока. работает на копии - контрольные
// сценарии не меняются.

export default function GeoScreen({ decision, scenarioId, caseData }) {
  const [desc, setDesc] = useState('Торговые ограничения на запуски с Земли')
  const [channels, setChannels] = useState(['A', 'B'])
  const [direction, setDirection] = useState('increase')
  const [magnitude, setMagnitude] = useState(0.25)
  const [combine, setCombine] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  function toggleChannel(id) {
    setChannels((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  }

  async function run() {
    setError(null)
    try {
      const event = {
        event_id: 'geo_event',
        description: desc,
        affected_channels: channels,
        direction,
        magnitude: parseFloat(magnitude) || 0,
        basis: 'условный сценарий, задан пользователем',
      }
      const r = await api.applyGeo(decision, scenarioId, event, combine)
      setResult(r)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div>
      <div className="panel">
        <h3>Геополитический сценарий <span className="hint">(работает на копии данных)</span></h3>
        <div style={{ marginBottom: 10 }}>
          <label>Описание события</label><br />
          <input className="wide" type="text" value={desc} onChange={(e) => setDesc(e.target.value)} />
        </div>

        <div style={{ marginBottom: 10 }}>
          <label>Затронутые каналы</label><br />
          {caseData.channels.map((c) => (
            <button
              key={c.id}
              className={'btn ' + (channels.includes(c.id) ? '' : 'secondary')}
              style={{ marginRight: 6, marginTop: 4 }}
              onClick={() => toggleChannel(c.id)}
            >
              {c.id}
            </button>
          ))}
        </div>

        <div className="row" style={{ marginBottom: 10 }}>
          <div>
            <label>Направление</label><br />
            <select className="scenario-select" value={direction} onChange={(e) => setDirection(e.target.value)}>
              <option value="increase">рост цены</option>
              <option value="decrease">снижение цены</option>
            </select>
          </div>
          <div>
            <label>Величина (доля)</label><br />
            <input type="number" step="0.05" value={magnitude} onChange={(e) => setMagnitude(e.target.value)} />
            <div className="hint">0.25 = ±25%</div>
          </div>
          <div>
            <label>Совместить со стрессом</label><br />
            <button className={'btn ' + (combine ? '' : 'secondary')} onClick={() => setCombine(!combine)}>
              {combine ? 'да' : 'нет'}
            </button>
          </div>
        </div>

        <button className="btn" onClick={run}>Рассчитать сценарий</button>
      </div>

      {error && <div className="err-msg">{error}</div>}

      {result && (
        <>
          <div className="panel">
            <h3>Причинная цепочка</h3>
            {result.causal_chain.map((line, i) => (
              <div key={i} style={{ padding: '3px 0', fontFamily: 'monospace', fontSize: 13 }}>{line}</div>
            ))}
          </div>

          <div className="panel">
            <h3>Эффект: до / после</h3>
            <table>
              <thead>
                <tr><th className="txt">Метрика</th><th>До</th><th>После</th><th>Δ</th></tr>
              </thead>
              <tbody>
                <tr>
                  <td className="txt">Суммарные расходы</td>
                  <td>{result.before.economics.total_cost.toFixed(1)}</td>
                  <td>{result.after.economics.total_cost.toFixed(1)}</td>
                  <td>{result.cost_delta >= 0 ? '+' : ''}{result.cost_delta.toFixed(1)}</td>
                </tr>
              </tbody>
            </table>
            <div className="hint">Восстановление исходных цен — просто пересчёт без события (исходные данные не тронуты).</div>
          </div>
        </>
      )}
    </div>
  )
}
