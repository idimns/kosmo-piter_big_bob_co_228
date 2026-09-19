import React from 'react'

// экран нарушений. цвет НЕ единственный индикатор - есть тег [ОШИБКА]/[ВНИМАНИЕ]
// и текст (доступность).

export default function ViolationsScreen({ result }) {
  if (!result) return <div className="panel">Нет результата.</div>

  const errors = result.violations.filter((v) => v.severity === 'error')
  const warnings = result.violations.filter((v) => v.severity === 'warning')

  return (
    <div>
      <div className="panel">
        <h3>
          Проверка ограничений{' '}
          <span className={'badge ' + (result.feasible ? 'ok' : 'err')}>
            {result.feasible ? 'план исполним' : 'план неисполним'}
          </span>
        </h3>

        {result.violations.length === 0 && (
          <div className="viol" style={{ borderLeftColor: '#3fb950' }}>
            <span className="tag" style={{ color: '#3fb950' }}>[OK]</span>
            Нарушений не найдено.
          </div>
        )}

        {errors.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div className="hint">Ошибки ({errors.length}) — план не соответствует обязательным ограничениям:</div>
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
            <div className="hint">Предупреждения ({warnings.length}) — ориентиры устойчивости (напр. в стрессе):</div>
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
                <th>Вероятность</th>
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
            Надёжность каналов учтена здесь как риск, а не как множитель поставки.
          </div>
        </div>
      )}
    </div>
  )
}
