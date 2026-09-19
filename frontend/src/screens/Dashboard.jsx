import React from 'react'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'

// дашборд оператора: обзор спроса/поставок/запаса/расходов/дефицита по годам.
// общий и критический сервис показаны отдельно.

function pct(x) { return (x * 100).toFixed(1) + '%' }
function num(x) { return (x || 0).toFixed(1) }

export default function Dashboard({ result }) {
  if (!result) return <div className="panel">Нет результата. Задайте план на вкладке «Решения».</div>

  const e = result.economics
  // план пустой, если ничего не заказано (нет поступлений ни в одном году)
  const planEmpty = result.years.every((r) => (r.inflow || 0) === 0)
  const chartData = result.years.map((r) => ({
    year: r.year,
    Спрос: Math.round(r.demand_total),
    Поставка: Math.round(r.inflow),
    Запас: Math.round(r.stock_end),
    Дефицит: Math.round(r.shortage_total),
    Расходы: Math.round(e.total_by_year[r.year] || 0),
  }))

  return (
    <div>
      {planEmpty && (
        <div className="status-banner bad" style={{ marginBottom: 16 }}>
          <div className="icon">i</div>
          <div>
            <div className="title">План пуст — расходы 0</div>
            <div className="sub">
              Импорт меняет данные кейса (спрос, каналы, склад), но не заказы.
              Задайте заказы по каналам на вкладке «Решения / план» — расходы и
              графики пересчитаются.
            </div>
          </div>
        </div>
      )}
      <div className="row" style={{ marginBottom: 16 }}>
        <div className="kpi">
          <div className="label">Суммарные расходы</div>
          <div className="value">{num(e.total_cost)}</div>
        </div>
        <div className="kpi">
          <div className="label">Дисконтированные</div>
          <div className="value">{num(e.total_discounted)}</div>
        </div>
        <div className="kpi">
          <div className="label">CAPEX до 2037</div>
          <div className="value">{num(e.capex_cumulative_2037)}</div>
        </div>
        <div className="kpi">
          <div className="label">Стоимость т</div>
          <div className="value">{num(e.cost_per_ton_served)}</div>
        </div>
      </div>

      <div className="row">
        <div className="col panel">
          <h3>Спрос / поставка / запас</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2f3846" />
              <XAxis dataKey="year" stroke="#8a94a6" />
              <YAxis stroke="#8a94a6" />
              <Tooltip contentStyle={{ background: '#1a2029', border: '1px solid #2f3846' }} />
              <Legend />
              <Bar dataKey="Спрос" fill="#4a9eff" />
              <Bar dataKey="Поставка" fill="#3fb950" />
              <Bar dataKey="Запас" fill="#d29922" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="col panel">
          <h3>Годовые расходы</h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2f3846" />
              <XAxis dataKey="year" stroke="#8a94a6" />
              <YAxis stroke="#8a94a6" />
              <Tooltip contentStyle={{ background: '#1a2029', border: '1px solid #2f3846' }} />
              <Line type="monotone" dataKey="Расходы" stroke="#f85149" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="panel">
        <h3>Баланс и обслуживание по годам</h3>
        <table>
          <thead>
            <tr>
              <th className="txt">Год</th>
              <th>Спрос</th>
              <th>Критич.</th>
              <th>Запас нач.</th>
              <th>Поступление</th>
              <th>Потери</th>
              <th>Выдано</th>
              <th>Запас кон.</th>
              <th>Серв. общий</th>
              <th>Серв. критич.</th>
              <th>Дефицит</th>
            </tr>
          </thead>
          <tbody>
            {result.years.map((r) => (
              <tr key={r.year}>
                <td className="txt">{r.year}</td>
                <td>{num(r.demand_total)}</td>
                <td>{num(r.demand_critical)}</td>
                <td>{num(r.stock_start)}</td>
                <td>{num(r.inflow)}</td>
                <td>{num(r.losses)}</td>
                <td>{num(r.issued)}</td>
                <td>{num(r.stock_end)}</td>
                <td style={{ color: r.service_total_ratio >= 0.97 ? '#3fb950' : '#f85149' }}>
                  {pct(r.service_total_ratio)}
                </td>
                <td style={{ color: r.service_critical_ratio >= 0.99 ? '#3fb950' : '#f85149' }}>
                  {pct(r.service_critical_ratio)}
                </td>
                <td>{num(r.shortage_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="hint">Единицы: т/год для объёмов, млн у.е. для расходов. Сценарий: {result.scenario_id}.</div>
      </div>
    </div>
  )
}
