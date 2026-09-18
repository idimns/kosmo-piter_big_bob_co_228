import React, { useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import * as api from '../api'

// геополитический блок (+5 бонус). пользователь задаёт событие, каналы,
// направление и величину ценового шока. работает на копии - контрольные
// сценарии не меняются.

// пресеты частых сценариев - чтобы не заполнять руками
const PRESETS = [
  { label: 'Санкции на земные запуски', channels: ['A', 'B'], dir: 'increase', mag: 0.25,
    desc: 'Торговые ограничения удорожают наземно-орбитальные каналы' },
  { label: 'Рост страховых/логистики', channels: ['A', 'B', 'C'], dir: 'increase', mag: 0.15,
    desc: 'Рост страховых и логистических затрат по земным поставкам' },
  { label: 'Удешевление лунной доставки', channels: ['D'], dir: 'decrease', mag: 0.20,
    desc: 'Технологический прорыв удешевляет доставку с Луны' },
]

const tooltipStyle = { background: '#1a2029', border: '1px solid #2f3846' }

export default function GeoScreen({ decision, scenarioId, caseData }) {
  const [desc, setDesc] = useState(PRESETS[0].desc)
  const [channels, setChannels] = useState(['A', 'B'])
  const [direction, setDirection] = useState('increase')
  const [magnitude, setMagnitude] = useState(0.25)
  const [combine, setCombine] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  function applyPreset(p) {
    setDesc(p.desc)
    setChannels(p.channels)
    setDirection(p.dir)
    setMagnitude(p.mag)
  }

  function toggleChannel(id) {
    setChannels((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  }

  async function run() {
    setError(null)
    try {
      const event = {
        event_id: 'geo_event', description: desc, affected_channels: channels,
        direction, magnitude: parseFloat(magnitude) || 0,
        basis: 'условный сценарий, задан пользователем',
      }
      const r = await api.applyGeo(decision, scenarioId, event, combine)
      setResult(r)
    } catch (e) {
      setError(e.message)
    }
  }

  const chartData = result ? [
    { name: 'Расходы', 'До': +result.before.economics.total_cost.toFixed(0), 'После': +result.after.economics.total_cost.toFixed(0) },
  ] : []

  return (
    <div>
      <div className="panel">
        <h3>Геополитический сценарий <span className="hint">(бонусный модуль, работает на копии — контрольные данные не меняются)</span></h3>

        <div className="section-title">Быстрые пресеты</div>
        <div style={{ marginBottom: 12 }}>
          {PRESETS.map((p, i) => (
            <button key={i} className="btn secondary" style={{ marginRight: 8, marginBottom: 6 }} onClick={() => applyPreset(p)}>
              {p.label}
            </button>
          ))}
        </div>

        <div style={{ marginBottom: 10 }}>
          <label>Описание события</label><br />
          <input className="wide" type="text" value={desc} onChange={(e) => setDesc(e.target.value)} />
        </div>

        <div style={{ marginBottom: 10 }}>
          <label>Затронутые каналы</label><br />
          {caseData.channels.map((c) => (
            <button key={c.id}
              className={'btn ' + (channels.includes(c.id) ? '' : 'secondary')}
              style={{ marginRight: 6, marginTop: 4 }}
              onClick={() => toggleChannel(c.id)}>
              {c.id}
            </button>
          ))}
        </div>

        <div className="row" style={{ marginBottom: 12, alignItems: 'flex-end' }}>
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
          <div>
            <button className="btn" onClick={run}>Рассчитать сценарий</button>
          </div>
        </div>
      </div>

      {error && <div className="err-msg">{error}</div>}

      {result && (
        <div className="row">
          <div className="col panel">
            <h3>Причинная цепочка</h3>
            {result.causal_chain.map((line, i) => (
              <div key={i} style={{ padding: '3px 0', fontFamily: 'monospace', fontSize: 13, lineHeight: 1.5 }}>{line}</div>
            ))}
            <div style={{ marginTop: 10 }}>
              <span className={'badge ' + (result.cost_delta >= 0 ? 'err' : 'ok')}>
                расходы {result.cost_delta >= 0 ? '+' : ''}{result.cost_delta.toFixed(1)} млн у.е.
              </span>
            </div>
          </div>

          <div className="col panel">
            <h3>Эффект: до / после</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2f3846" />
                <XAxis dataKey="name" stroke="#8a94a6" />
                <YAxis stroke="#8a94a6" />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="До" fill="#4a9eff" />
                <Bar dataKey="После" fill="#d29922" />
              </BarChart>
            </ResponsiveContainer>
            <div className="hint">Восстановление исходных цен — просто пересчёт без события (исходные данные не тронуты).</div>
          </div>
        </div>
      )}
    </div>
  )
}
