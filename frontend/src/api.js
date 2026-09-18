// клиент к API. тонкая обёртка над fetch.
// база пустая - и в дев (через proxy), и в проде (один процесс) /api работает.

async function req(path, opts) {
  const r = await fetch(path, opts)
  if (!r.ok) {
    let msg = `HTTP ${r.status}`
    try {
      const body = await r.json()
      if (body.detail) msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch (e) { /* не json - оставим как есть */ }
    throw new Error(msg)
  }
  return r.json()
}

export function getCase() {
  return req('/api/case')
}

export function getScenarios() {
  return req('/api/scenarios')
}

export function evaluatePlan(decision, scenarioId) {
  return req('/api/plan/evaluate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, scenario_id: scenarioId }),
  })
}

export function compareScenarios(decision) {
  return req('/api/scenario/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision }),
  })
}

export function applyGeo(decision, scenarioId, event, combine) {
  return req('/api/geopolitical/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, scenario_id: scenarioId, event, combine_with_stress: !!combine }),
  })
}

export function listPlans() {
  return req('/api/plans')
}

export function loadPlan(name) {
  return req('/api/plans/' + encodeURIComponent(name))
}

export function savePlan(name, decision, scenarioId) {
  return req('/api/plans/' + encodeURIComponent(name), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, scenario_id: scenarioId }),
  })
}

// выгрузка - просто открываем урл, браузер качает файл
export function exportUrl() {
  return '/api/export'
}

export async function downloadExport(decision, scenarioId, fmt) {
  const r = await fetch('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, scenario_id: scenarioId, fmt }),
  })
  if (!r.ok) throw new Error('Ошибка выгрузки: HTTP ' + r.status)
  const blob = await r.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = scenarioId + (fmt === 'csv' ? '_plan.csv' : '_export.xlsx')
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
