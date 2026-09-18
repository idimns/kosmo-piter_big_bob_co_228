import React, { useState, useEffect } from 'react'
import * as api from '../api'

// сравнение стандартного и стрессового сценариев на общей базе (с.10).

function pct(x) { return (x * 100).toFixed(1) + '%' }

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

  return (
    <div>
      <div className="panel">
        <h3>Сводка сравнения</h3>
        <table>
          <thead>
            <tr><th className="txt">Метрика</th><th>Стандартный</th><th>Стресс</th><th>Δ</th></tr>
          </thead>
          <tbody>
            <tr>
              <td className="txt">Суммарные расходы</td>
              <td>{diff.total_cost.standard.toFixed(1)}</td>
              <td>{diff.total_cost.stress.toFixed(1)}</td>
              <td>{diff.total_cost.delta >= 0 ? '+' : ''}{diff.total_cost.delta.toFixed(1)}</td>
            </tr>
            <tr>
              <td className="txt">Дисконтированные</td>
              <td>{diff.total_discounted.standard.toFixed(1)}</td>
              <td>{diff.total_discounted.stress.toFixed(1)}</td>
              <td>{diff.total_discounted.delta >= 0 ? '+' : ''}{diff.total_discounted.delta.toFixed(1)}</td>
            </tr>
            <tr>
              <td className="txt">Исполнимость</td>
              <td><span className={'badge ' + (standard.feasible ? 'ok' : 'err')}>{standard.feasible ? 'да' : 'нет'}</span></td>
              <td><span className={'badge ' + (stress.feasible ? 'ok' : 'err')}>{stress.feasible ? 'да' : 'нет'}</span></td>
              <td>—</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h3>Обслуживание и запас по годам</h3>
        <table>
          <thead>
            <tr>
              <th className="txt">Год</th>
              <th>Серв.общ (станд)</th>
              <th>Серв.общ (стресс)</th>
              <th>Дефицит (станд)</th>
              <th>Дефицит (стресс)</th>
              <th>Запас (станд)</th>
              <th>Запас (стресс)</th>
            </tr>
          </thead>
          <tbody>
            {diff.by_year.map((r) => (
              <tr key={r.year}>
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
