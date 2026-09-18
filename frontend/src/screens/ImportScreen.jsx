import React, { useState } from 'react'
import * as api from '../api'

// экран импорта данных из CSV/XLSX без строгой структуры.
// поток: загрузить файл -> импортёр угадывает тип и колонки -> пользователь
// правит маппинг при желании -> применить к рабочему кейсу.
// файл держим в state, чтобы правки маппинга пересобирали превью на бэке.

const ROLE_LABELS = {
  '': '— не использовать —',
  year: 'год', id: 'ID', name: 'название',
  base_total: 'спрос общий', critical: 'спрос критический',
  low_total: 'спрос низкий', high_total: 'спрос высокий',
  capacity: 'мощность', var_cost: 'переменная цена',
  reservation_rate: 'ставка резерва', take_or_pay: 'take-or-pay',
  lead_time_months: 'lead time (мес)', lead_time_min: 'lead min',
  lead_time_max: 'lead max', lead_time_unit: 'ед. срока',
  reliability: 'надёжность', available_from: 'доступен с года', requires: 'требует инвестицию',
  loss_rate: 'коэф. потерь', storage_cost: 'стоимость хранения',
  capex: 'CAPEX', extra_opex: 'доп. OPEX',
  option_fee: 'плата за опцион', exercise_cost: 'стоимость реализации',
  commissioning_rule: 'правило ввода',
  metric: 'метрика', operator: 'оператор', value: 'значение',
  unit: 'единица', period: 'период', scenario: 'сценарий', severity: 'уровень',
}

const TYPE_LABELS = {
  demand: 'Спрос', channels: 'Каналы снабжения', storage: 'Хранилище',
  investments: 'Инвестиции', constraints: 'Ограничения',
}

export default function ImportScreen({ onApplied }) {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [override, setOverride] = useState({})   // role -> source header
  const [typeOverride, setTypeOverride] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [applied, setApplied] = useState(null)

  async function doPreview(f, ovr, tovr) {
    setBusy(true); setError(null); setApplied(null)
    try {
      const p = await api.importPreview(f, ovr, tovr)
      setPreview(p)
    } catch (e) {
      setError(e.message); setPreview(null)
    } finally {
      setBusy(false)
    }
  }

  function onFile(e) {
    const f = e.target.files[0]
    if (!f) return
    setFile(f)
    setOverride({})
    setTypeOverride('')
    doPreview(f, null, null)
  }

  // сменить роль колонки: строим override role->source и пересчитываем
  function remapColumn(source, newRole) {
    const ovr = { ...override }
    // убираем этот source из всех ролей
    for (const k of Object.keys(ovr)) if (ovr[k] === source) delete ovr[k]
    if (newRole) ovr[newRole] = source
    setOverride(ovr)
    doPreview(file, ovr, typeOverride || preview?.table_type)
  }

  function changeType(t) {
    setTypeOverride(t)
    doPreview(file, override, t)
  }

  // текущая роль колонки с учётом override
  function currentRole(col) {
    for (const [role, src] of Object.entries(override)) if (src === col.source) return role
    return col.role || ''
  }

  async function apply() {
    if (!preview || !preview.preview) return
    setBusy(true); setError(null)
    try {
      const res = await api.importApply([preview.preview])
      setApplied(res)
      if (onApplied) onApplied()   // обновить кейс в App
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function reset() {
    setBusy(true); setError(null)
    try {
      await api.importReset()
      setApplied({ reset: true })
      setPreview(null); setFile(null)
      if (onApplied) onApplied()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="panel">
        <h3>Импорт данных из CSV / XLSX</h3>
        <p style={{ color: 'var(--muted)', margin: '4px 0 12px', lineHeight: 1.5 }}>
          Загрузите файл со спросом, каналами, хранилищем или инвестициями. Структура
          не важна — импортёр сам распознаёт колонки по названиям (в любом порядке,
          с любыми заголовками, лишние колонки игнорируются). Формат-ориентир —
          файлы репозитория организатора (demand.csv, supply_sources.csv, …).
        </p>
        <input type="file" accept=".csv,.xlsx,.xls" onChange={onFile} />
        {busy && <span className="hint" style={{ marginLeft: 10 }}>обработка…</span>}
        <button className="btn secondary" style={{ marginLeft: 12 }} onClick={reset}>
          Сбросить к исходным данным
        </button>
      </div>

      {error && <div className="err-msg">Ошибка: {error}</div>}

      {applied && applied.reset && (
        <div className="panel"><span className="badge ok">данные сброшены к исходным</span></div>
      )}
      {applied && applied.applied && (
        <div className="panel">
          <span className="badge ok">импортировано: {applied.applied.join(', ')}</span>
          {applied.channels && <div className="hint" style={{ marginTop: 6 }}>каналы: {applied.channels.join(', ')}</div>}
        </div>
      )}

      {preview && (
        <>
          <div className="panel">
            <h3>Распознавание файла «{preview.filename}»</h3>
            <div className="row" style={{ marginBottom: 10 }}>
              <div>
                <label>Тип таблицы</label><br />
                <select className="scenario-select" value={typeOverride || preview.table_type || ''} onChange={(e) => changeType(e.target.value)}>
                  <option value="">— не распознан —</option>
                  {(preview.table_types || []).map((t) => (
                    <option key={t} value={t}>{TYPE_LABELS[t] || t}</option>
                  ))}
                </select>
              </div>
              <div className="kpi">
                <div className="label">Строк в файле</div>
                <div className="value">{preview.row_count}</div>
              </div>
            </div>

            <div className="section-title">Сопоставление колонок</div>
            <div className="hint" style={{ marginBottom: 8 }}>
              Импортёр угадал роли. Поправьте вручную, если что-то не так — превью пересчитается.
            </div>
            <table>
              <thead>
                <tr>
                  <th className="txt">Колонка файла</th>
                  <th className="txt">Роль в модели</th>
                  <th className="txt">Примеры значений</th>
                </tr>
              </thead>
              <tbody>
                {preview.columns.map((col) => (
                  <tr key={col.source}>
                    <td className="txt"><b>{col.source}</b></td>
                    <td className="txt">
                      <select
                        className="scenario-select"
                        value={currentRole(col)}
                        onChange={(e) => remapColumn(col.source, e.target.value)}
                      >
                        {Object.entries(ROLE_LABELS).map(([r, lbl]) => (
                          <option key={r} value={r}>{lbl}</option>
                        ))}
                      </select>
                    </td>
                    <td className="txt" style={{ color: 'var(--muted)' }}>
                      {col.samples.join(', ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="panel">
            <h3>Превью применяемых данных</h3>
            {!preview.preview && <div className="hint">Тип не распознан — выберите тип таблицы выше.</div>}
            {preview.preview && <PreviewData built={preview.preview} />}
            <div style={{ marginTop: 12 }}>
              <button className="btn" onClick={apply} disabled={busy || !preview.preview}>
                Применить к кейсу
              </button>
              <span className="hint" style={{ marginLeft: 10 }}>
                данные применяются на рабочей копии; исходные всегда можно вернуть кнопкой сброса
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// показ распарсенных данных по типу
function PreviewData({ built }) {
  const { kind, data } = built
  if (kind === 'channels') {
    return (
      <table>
        <thead><tr><th className="txt">ID</th><th className="txt">Название</th><th>Мощность</th><th>Цена</th><th>ToP</th><th>Lead</th><th className="txt">Надёжность</th></tr></thead>
        <tbody>
          {data.map((c) => (
            <tr key={c.id}>
              <td className="txt">{c.id}</td><td className="txt">{c.name}</td>
              <td>{c.capacity}</td><td>{c.var_cost}</td><td>{c.take_or_pay}</td>
              <td>{c.lead_time_months}</td>
              <td className="txt">{JSON.stringify(c.reliability)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )
  }
  if (kind === 'demand') {
    const years = Object.keys(data.years || {}).sort()
    return (
      <table>
        <thead><tr><th className="txt">Год</th><th>Общий</th><th>Критич.</th><th>Низкий</th><th>Высокий</th></tr></thead>
        <tbody>
          {years.map((y) => (
            <tr key={y}><td className="txt">{y}</td><td>{data.years[y].base_total}</td><td>{data.years[y].critical}</td><td>{data.years[y].low_total}</td><td>{data.years[y].high_total}</td></tr>
          ))}
        </tbody>
      </table>
    )
  }
  if (kind === 'investments') {
    return (
      <table>
        <thead><tr><th className="txt">ID</th><th className="txt">Название</th><th>CAPEX</th><th>OPEX</th></tr></thead>
        <tbody>
          {data.map((i) => (
            <tr key={i.id}><td className="txt">{i.id}</td><td className="txt">{i.name}</td><td>{i.capex}</td><td>{i.extra_opex}</td></tr>
          ))}
        </tbody>
      </table>
    )
  }
  if (kind === 'storage') {
    return (
      <table>
        <thead><tr><th className="txt">Режим</th><th>Ёмкость</th><th>Потери</th><th>Хранение</th><th>CAPEX</th></tr></thead>
        <tbody>
          <tr><td className="txt">base</td><td>{data.base?.capacity}</td><td>{data.base?.loss_rate}</td><td>{data.base?.storage_cost}</td><td>{data.base?.capex}</td></tr>
          {data.zbo_upgrade && <tr><td className="txt">zbo</td><td>{data.zbo_upgrade.capacity}</td><td>{data.zbo_upgrade.loss_rate}</td><td>{data.zbo_upgrade.storage_cost}</td><td>{data.zbo_upgrade.capex}</td></tr>}
        </tbody>
      </table>
    )
  }
  // constraints и прочее - как есть
  return <pre style={{ fontSize: 12, color: 'var(--muted)', overflow: 'auto' }}>{JSON.stringify(data, null, 2).slice(0, 800)}</pre>
}
