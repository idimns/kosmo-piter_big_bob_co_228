import React from 'react'
import {
  BarChart, Bar, ComposedChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'

// дашборд оператора: обзор спроса/поставок/запаса/расходов/дефицита по годам.
// общий и критический сервис показаны отдельно (с.8).
// цель - чтобы с ходу было видно: план ок или нет, и где узкие места.

function pct(x) { return (x * 100).toFixed(1) + '%' }
function num(x) { return (x || 0).toFixed(1) }

// цвета каналов для stacked-графика (стабильные по id)
const CH_COLORS = {
  A: '#4a9eff', B: '#3fb950', C: '#a371f7', D: '#d29922', E: '#f85149',
}

const tooltipStyle = { background: '#1a2029', border: '1px solid #2f3846' }

export default function Dashboard({ result, caseData }) {
  if (!result) return <div className="panel">Нет результата. Задайте план на вкладке «Решения».</div>

  const e = result.economics
  const c = caseData.constraints

  // данные для графиков
  const chartData = result.years.map((r) => {
    const row = {
      year: r.year,
      Спрос: Math.round(r.demand_total),
      Запас: Math.round(r.stock_end),
      Дефицит: Math.round(r.shortage_total),
      Расходы: Math.round(e.total_by_year[r.year] || 0),
      servTotal: +(r.service_total_ratio * 100).toFixed(1),
      servCrit: +(r.service_critical_ratio * 100).toFixed(1),
    }
    // поставка в разбивке по каналам (stacked)
    for (const f of r.channels) {
      if (f.delivered > 0) row['кан_' + f.channel_id] = Math.round(f.delivered)
    }
    return row
  })

  // какие каналы реально использованы (чтобы не рисовать пустые)
  const usedChannels = []
  for (const ch of caseData.channels) {
    const any = result.years.some((r) => r.channels.some((f) => f.channel_id === ch.id && f.delivered > 0))
    if (any) usedChannels.push(ch.id)
  }

  // худший сервис по годам - для KPI. старт выше 1, чтобы первый год всегда
  // записался (иначе при сервисе ровно 100% worstYear оставался null)
  let worstTotal = 99, worstCrit = 99, worstYear = null
  for (const r of result.years) {
    if (r.service_total_ratio < worstTotal) { worstTotal = r.service_total_ratio; worstYear = r.year }
    if (r.service_critical_ratio < worstCrit) worstCrit = r.service_critical_ratio
  }

  // ёмкость хранилища из кейса (base или zbo)
  const capLimit = caseData.storage.zbo_upgrade
    ? Math.max(caseData.storage.base.capacity, caseData.storage.zbo_upgrade.capacity)
    : caseData.storage.base.capacity

  const errors = result.violations.filter((v) => v.severity === 'error')

  // хелпер прогресс-бара: value от 0..1, cls - цвет
  function bar(frac, cls) {
    const w = Math.max(0, Math.min(1, frac)) * 100
    return <div className="progress"><span className={cls} style={{ width: w + '%' }} /></div>
  }

  const capexFrac = e.capex_cumulative_total / c.capex_cap_2040
  const critCls = worstCrit >= c.service_critical_min ? 'ok' : 'err'
  const totalCls = worstTotal >= c.service_total_min ? 'ok' : (result.scenario_id === 'standard' ? 'err' : 'warn')

  return (
    <div>
      {/* статус плана - сразу видно ок/не ок */}
      <div className={'status-banner ' + (result.feasible ? 'ok' : 'bad')}>
        <div className="icon">{result.feasible ? '✓' : '✕'}</div>
        <div>
          <div className="title">
            {result.feasible ? 'План исполним' : 'План неисполним'}
            <span className="hint" style={{ marginLeft: 10, textTransform: 'none' }}>
              сценарий: {result.scenario_id}
            </span>
          </div>
          <div className="sub">
            {result.feasible
              ? `Все обязательные ограничения соблюдены. Худший общий сервис ${pct(worstTotal)} (${worstYear}).`
              : `${errors.length} нарушений. Первое: ${errors[0] ? errors[0].message : ''}`}
          </div>
        </div>
      </div>

      {/* KPI с контекстом лимитов */}
      <div className="section-title">Ключевые показатели</div>
      <div className="row" style={{ marginBottom: 18 }}>
        <div className="kpi wide">
          <div className="label">Критический сервис (мин. за годы)</div>
          <div className={'value ' + critCls}>{pct(worstCrit)}</div>
          <div className="sub">требуется ≥ {pct(c.service_critical_min)}</div>
          {bar(worstCrit, critCls)}
        </div>
        <div className="kpi wide">
          <div className="label">Общий сервис (мин. за годы)</div>
          <div className={'value ' + totalCls}>{pct(worstTotal)}</div>
          <div className="sub">требуется ≥ {pct(c.service_total_min)}</div>
          {bar(worstTotal, totalCls)}
        </div>
        <div className="kpi wide">
          <div className="label">CAPEX суммарный</div>
          <div className={'value ' + (capexFrac <= 1 ? 'ok' : 'err')}>{num(e.capex_cumulative_total)}</div>
          <div className="sub">лимит {c.capex_cap_2040} (до 2037: {num(e.capex_cumulative_2037)}/{c.capex_cap_2037})</div>
          {bar(capexFrac, capexFrac <= 1 ? 'ok' : 'err')}
        </div>
      </div>
      <div className="row" style={{ marginBottom: 18 }}>
        <div className="kpi">
          <div className="label">Суммарные расходы</div>
          <div className="value">{num(e.total_cost)}</div>
          <div className="sub">млн у.е.</div>
        </div>
        <div className="kpi">
          <div className="label">Дисконтированные</div>
          <div className="value">{num(e.total_discounted)}</div>
          <div className="sub">млн у.е.</div>
        </div>
        <div className="kpi">
          <div className="label">Стоимость тонны</div>
          <div className="value">{num(e.cost_per_ton_served)}</div>
          <div className="sub">млн у.е./т обсл.</div>
        </div>
      </div>

      {/* сервис с порогами - главный график "прошли/не прошли" */}
      <div className="panel">
        <h3>Обслуживание спроса и пороги</h3>
        <ResponsiveContainer width="100%" height={230}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2f3846" />
            <XAxis dataKey="year" stroke="#8a94a6" />
            <YAxis domain={[80, 100]} stroke="#8a94a6" unit="%" />
            <Tooltip contentStyle={tooltipStyle} />
            <Legend />
            <ReferenceLine y={99} stroke="#3fb950" strokeDasharray="5 3" label={{ value: '99% крит', fill: '#3fb950', fontSize: 11, position: 'right' }} />
            <ReferenceLine y={97} stroke="#d29922" strokeDasharray="5 3" label={{ value: '97% общ', fill: '#d29922', fontSize: 11, position: 'right' }} />
            <Line type="monotone" dataKey="servCrit" name="Критический %" stroke="#3fb950" strokeWidth={2} />
            <Line type="monotone" dataKey="servTotal" name="Общий %" stroke="#4a9eff" strokeWidth={2} />
          </ComposedChart>
        </ResponsiveContainer>
        <div className="hint">Линии ниже пунктира — недобор сервиса. В стандартном сценарии это нарушение, в стрессе — ориентир.</div>
      </div>

      <div className="row">
        {/* поставка по каналам vs спрос */}
        <div className="col panel">
          <h3>Поставка по каналам и спрос</h3>
          <ResponsiveContainer width="100%" height={250}>
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2f3846" />
              <XAxis dataKey="year" stroke="#8a94a6" />
              <YAxis stroke="#8a94a6" />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend />
              {usedChannels.map((id) => (
                <Bar key={id} dataKey={'кан_' + id} name={'Канал ' + id} stackId="supply" fill={CH_COLORS[id] || '#8a94a6'} />
              ))}
              <Line type="monotone" dataKey="Спрос" stroke="#f0f6fc" strokeWidth={2} dot={{ r: 3 }} />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="hint">Столбцы — поставка по каналам (стек), белая линия — спрос. Видно микс снабжения.</div>
        </div>

        {/* запас с ёмкостью */}
        <div className="col panel">
          <h3>Запас на конец года и ёмкость</h3>
          <ResponsiveContainer width="100%" height={250}>
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2f3846" />
              <XAxis dataKey="year" stroke="#8a94a6" />
              <YAxis stroke="#8a94a6" />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend />
              <ReferenceLine y={capLimit} stroke="#f85149" strokeDasharray="5 3" label={{ value: 'ёмкость ' + capLimit, fill: '#f85149', fontSize: 11, position: 'insideTopRight' }} />
              <Bar dataKey="Запас" fill="#d29922" />
              <Bar dataKey="Дефицит" fill="#f85149" />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="hint">Красный пунктир — ёмкость хранилища. Дефицит выделен отдельно.</div>
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
            {result.years.map((r) => {
              const critBad = r.service_critical_ratio < c.service_critical_min
              const totalBad = r.service_total_ratio < c.service_total_min
              const cls = critBad ? 'bad-year' : (totalBad ? 'warn-year' : '')
              return (
                <tr key={r.year} className={cls}>
                  <td className="txt">{r.year}</td>
                  <td>{num(r.demand_total)}</td>
                  <td>{num(r.demand_critical)}</td>
                  <td>{num(r.stock_start)}</td>
                  <td>{num(r.inflow)}</td>
                  <td>{num(r.losses)}</td>
                  <td>{num(r.issued)}</td>
                  <td>{num(r.stock_end)}</td>
                  <td style={{ color: totalBad ? '#f85149' : '#3fb950' }}>{pct(r.service_total_ratio)}</td>
                  <td style={{ color: critBad ? '#f85149' : '#3fb950' }}>{pct(r.service_critical_ratio)}</td>
                  <td>{num(r.shortage_total)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <div className="legend-row">
          <span><span className="dot" style={{ background: 'rgba(248,81,73,0.5)' }} />строка — недобор критического сервиса</span>
          <span><span className="dot" style={{ background: 'rgba(210,153,34,0.5)' }} />строка — недобор общего сервиса</span>
          <span>единицы: т/год, расходы в млн у.е.</span>
        </div>
      </div>
    </div>
  )
}
