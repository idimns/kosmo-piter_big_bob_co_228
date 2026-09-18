import React, { useState, useEffect, useCallback } from 'react'
import * as api from './api'
import DataScreen from './screens/DataScreen.jsx'
import DecisionsScreen from './screens/DecisionsScreen.jsx'
import Dashboard from './screens/Dashboard.jsx'
import ViolationsScreen from './screens/ViolationsScreen.jsx'
import CompareScreen from './screens/CompareScreen.jsx'
import GeoScreen from './screens/GeoScreen.jsx'

const SCREENS = [
  { id: 'data', label: 'Данные кейса' },
  { id: 'decisions', label: 'Решения / план' },
  { id: 'dashboard', label: 'Дашборд' },
  { id: 'violations', label: 'Проверки' },
  { id: 'compare', label: 'Сравнение сценариев' },
  { id: 'geo', label: 'Геополитика (+5)' },
]

// начальный план - пустой, пользователь наполняет через экран решений
const EMPTY_DECISION = {
  scenario_id: 'standard',
  initial_stock: 0,
  use_zbo: false,
  investments: {},
  plan: {},
}

export default function App() {
  const [screen, setScreen] = useState('data')
  const [caseData, setCaseData] = useState(null)
  const [scenarios, setScenarios] = useState([])
  const [scenarioId, setScenarioId] = useState('standard')
  const [decision, setDecision] = useState(EMPTY_DECISION)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  // грузим кейс и сценарии на старте
  useEffect(() => {
    Promise.all([api.getCase(), api.getScenarios()])
      .then(([c, s]) => {
        setCaseData(c)
        setScenarios(s)
      })
      .catch((e) => setError('Не удалось загрузить данные: ' + e.message))
  }, [])

  // пересчёт плана
  const recalc = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.evaluatePlan(decision, scenarioId)
      setResult(res)
    } catch (e) {
      setError(e.message)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }, [decision, scenarioId])

  // автопересчёт при смене плана или сценария
  useEffect(() => {
    if (caseData) recalc()
  }, [decision, scenarioId, caseData, recalc])

  if (!caseData) {
    return (
      <div className="app">
        <div className="main">
          {error ? <div className="err-msg">{error}</div> : 'Загрузка...'}
        </div>
      </div>
    )
  }

  const common = { caseData, decision, setDecision, result, scenarioId }

  return (
    <div className="app">
      <div className="sidebar">
        <h1>Топливный космоконтур 2035</h1>
        {SCREENS.map((s) => (
          <button
            key={s.id}
            className={'nav-item' + (screen === s.id ? ' active' : '')}
            onClick={() => setScreen(s.id)}
          >
            {s.label}
          </button>
        ))}
      </div>

      <div className="main">
        <div className="topbar">
          <label>Сценарий:</label>
          <select
            className="scenario-select"
            value={scenarioId}
            onChange={(e) => setScenarioId(e.target.value)}
          >
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          {result && (
            <span className={'badge ' + (result.feasible ? 'ok' : 'err')}>
              {result.feasible ? 'план исполним' : 'есть нарушения'}
            </span>
          )}
          {loading && <span className="hint">пересчёт...</span>}
          <div style={{ marginLeft: 'auto' }}>
            <button className="btn secondary" onClick={() => api.downloadExport(decision, scenarioId, 'csv')}>
              CSV
            </button>
            {' '}
            <button className="btn secondary" onClick={() => api.downloadExport(decision, scenarioId, 'xlsx')}>
              XLSX
            </button>
          </div>
        </div>

        {error && <div className="err-msg">Ошибка: {error}</div>}

        {screen === 'data' && <DataScreen {...common} />}
        {screen === 'decisions' && <DecisionsScreen {...common} />}
        {screen === 'dashboard' && <Dashboard {...common} />}
        {screen === 'violations' && <ViolationsScreen {...common} />}
        {screen === 'compare' && <CompareScreen decision={decision} caseData={caseData} />}
        {screen === 'geo' && <GeoScreen decision={decision} scenarioId={scenarioId} caseData={caseData} />}
      </div>
    </div>
  )
}
