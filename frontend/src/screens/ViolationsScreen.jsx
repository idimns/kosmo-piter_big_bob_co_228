import React from 'react'

// экран нарушений. цвет НЕ единственный индикатор - есть тег [ОШИБКА]/[ВНИМАНИЕ]
// и текст (доступность, с.8).

export default function ViolationsScreen({ result }) {
  if (!result) return <div className="panel">Нет результата.</div>

  const errors = result.violations.filter((v) => v.severity === 'error')
  const warnings = result.violations.filter((v) => v.severity === 'warning')

  return (
    <div>
      {/* сводка сверху - сразу счётчики */}
      <div className={'status-banner ' + (result.feasible ? 'ok' : 'bad')}>
        <div className="icon">{result.feasible ? '✓' : '✕'}</div>
        <div>
          <div className="title">
            {result.feasible ? 'Все обязательные ограничения соблюдены' : 'План нарушает ограничения'}
          </div>
          <div className="sub">
            Ошибок: {errors.length} · Предупреждений: {warnings.length} · Рисков в реестре: {result.risks.length}
            {' '}· сценарий: {result.scenario_id}
          </div>
        </div>
      </div>

      <div className="panel">
        <h3>Проверка ограничений</h3>

        {result.violations.length === 0 && (
          <div className="viol" style={{ borderLeftColor: '#3fb950' }}>
            <span className="tag" style={{ color: '#3fb950' }}>[OK]</span>
            Нарушений не найдено. План проходит все проверки: сервис, ёмкость, мощность,
            CAPEX, сроки, резерв, условия каналов.
          </div>
        )}

        {errors.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div className="section-title" style={{ color: '#f85149' }}>Ошибки — обязательные ограничения нарушены</div>
            {errors.map((v, i) => (
              <div key={i} className="viol error">
                <span className="tag">[ОШИБКА]</span>
                {v.message}
              </div>
            ))}
          </div>
        )}

        {warnings.length > 0 && (
          <div>
            <div className="section-title" style={{ color: '#d29922' }}>Предупреждения — ориентиры устойчивости (напр. в стрессе)</div>
            {warnings.map((v, i) => (
              <div key={i} className="viol warning">
                <span className="tag">[ВНИМАНИЕ]</span>
                {v.message}
              </div>
            ))}
          </div>
        )}
      </div>

      {result.risks.length > 0 && (
        <div className="panel">
          <h3>Реестр рисков снабжения</h3>
          <table>
            <thead>
              <tr>
                <th className="txt">Событие</th>
                <th className="txt">Причина</th>
                <th className="txt">Период</th>
                <th>Вероятн.</th>
                <th>Ущерб, т</th>
                <th className="txt">Мера</th>
              </tr>
            </thead>
            <tbody>
              {result.risks.map((rk) => (
                <tr key={rk.risk_id}>
                  <td className="txt">{rk.event}</td>
                  <td className="txt">{rk.cause}</td>
                  <td className="txt">{rk.period}</td>
                  <td>{rk.probability}</td>
                  <td>{(rk.impact_tons || 0).toFixed(1)}</td>
                  <td className="txt">{rk.mitigation}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="hint">
            Надёжность каналов учтена здесь как риск (ожидаемая недопоставка), а не как
            множитель поставки в балансе (Правило 6 — без двойного учёта).
          </div>
        </div>
      )}
    </div>
  )
}
