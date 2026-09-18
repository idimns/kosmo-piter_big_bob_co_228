import React, { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import * as api from '../api'

// сравнение стандартного и стрессового сценариев на общей базе (с.10).

function pct(x) { return (x * 100).toFixed(1) + '%' }
const tooltipStyle = { background: '#1a2029', border: '1px solid #2f3846' }

export default function CompareScreen({ decision }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    api.compareScenarios(decision)
      .then((d) => { setData(d); setError(null) })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [decision])

  if (loading) return <div className="panel">Считаем оба сценария...</div>
  if (error) return <div className="err-msg">{error}</div>
  if (!data) return <div className="panel">Нет данных.</div>

  const { standard, stress, diff } = data

  // данные для графика: общий сервис по годам в обоих сценариях
  const chartData = diff.by_year.map((r) => ({
    year: r.year,
    'Стандарт': +(r.service_total.standard * 100).toFixed(1),
    'Стресс': +(r.service_total.stress * 100).toFixed(1),
  }))

  const deltaCost = diff.total_cost.delta

  return (
    <div>
      {/* верхняя сводка карточками */}
      <div className="row" style={{ marginBottom: 16 }}>
        <div className="kpi wide">
          <div className="label">Расходы: стандарт → стресс</div>
          <div className="value">{diff.total_cost.standard.toFixed(0)} → {diff.total_cost.stress.toFixed(0)}</div>
          <div className="sub">Δ {deltaCost >= 0 ? '+' : ''}{deltaCost.toFixed(1)} млн у.е.</div>
        </div>
        <div className="kpi">
          <div className="label">Стандарт</div>
          <div className="value"><span className={'badge ' + (standard.feasible ? 'ok' : 'err')}>{standard.feasible ? 'исполним' : 'нет'}</span></div>
        </div>
        <div className="kpi">
          <div className="label">Стресс</div>
          <div className="value"><span className={'badge ' + (stress.feasible ? 'ok' : 'err')}>{stress.feasible ? 'исполним' : 'нет'}</span></div>
        </div>
      </div>

      <div className="panel">
        <h3>Общий сервис: стандарт vs стресс</h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2f3846" />
            <XAxis dataKey="year" stroke="#8a94a6" />
            <YAxis domain={[80, 100]} stroke="#8a94a6" unit="%" />
            <Tooltip contentStyle={tooltipStyle} />
            <Legend />
            <ReferenceLine y={97} stroke="#d29922" strokeDasharray="5 3" label={{ value: '97%', fill: '#d29922', fontSize: 11, position: 'right' }} />
            <Bar dataKey="Стандарт" fill="#4a9eff" />
            <Bar dataKey="Стресс" fill="#d29922" />
          </BarChart>
        </ResponsiveContainer>
        <div className="hint">
          Видно, где стресс (спрос ×1.15 с 2038 + фактические доли ISRU) проваливает сервис ниже 97%.
        </div>
      </div>

      <div className="panel">
        <h3>Детально по годам</h3>
        <table>
          <thead>
            <tr>
              <th className="txt">Год</th>
              <th>Серв. общ (станд)</th>
              <th>Серв. общ (стресс)</th>
              <th>Дефицит (станд)</th>
              <th>Дефицит (стресс)</th>
              <th>Запас (станд)</th>
              <th>Запас (стресс)</th>
            </tr>
          </thead>
          <tbody>
            {diff.by_year.map((r) => (
              <tr key={r.year} className={r.service_total.stress < 0.97 ? 'warn-year' : ''}>
                <td className="txt">{r.year}</td>
                <td>{pct(r.service_total.standard)}</td>
                <td style={{ color: r.service_total.stress < 0.97 ? '#d29922' : '#d8dee9' }}>
                  {pct(r.service_total.stress)}
                </td>
                <td>{r.shortage_total.standard.toFixed(1)}</td>
                <td>{r.shortage_total.stress.toFixed(1)}</td>
                <td>{r.stock_end.standard.toFixed(1)}</td>
                <td>{r.stock_end.stress.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="hint">
          Дефицит в стрессе показывается численно, а не скрывается изменением бюджета (Правило 8).
        </div>
      </div>
    </div>
  )
}
