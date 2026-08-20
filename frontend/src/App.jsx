import { useEffect, useState } from 'react'
import axios from 'axios'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'
import './App.css'

function App() {
  const [emissions, setEmissions] = useState([])
  const [incidents, setIncidents] = useState(null)
  const [quality, setQuality] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
     axios.get(`${import.meta.env.VITE_API_URL}/api/emissions/monthly/`),
     axios.get(`${import.meta.env.VITE_API_URL}/api/incidents/summary/`),
     axios.get(`${import.meta.env.VITE_API_URL}/api/data-quality/`),
    ]).then(([emRes, incRes, dqRes]) => {
      setEmissions(emRes.data)
      setIncidents(incRes.data)
      setQuality(dqRes.data)
      setLoading(false)
    })
  }, [])

  if (loading) return <div className="loading">Loading Ironbark Ridge data...</div>

  const totalScope1 = emissions.reduce((s, m) => s + m.scope1_kg_co2e, 0)
  const totalScope2 = emissions.reduce((s, m) => s + m.scope2_kg_co2e, 0)
  const totalIncidents = incidents.monthly_trend.reduce((s, m) => s + m.count, 0)
  const psychosocialCount = incidents.psychosocial_flags.length
  const inconsistentCount = incidents.severity_inconsistencies.length

  const fmt = (kg) => `${(kg / 1000).toFixed(0)} t`
  const fmtMonth = (m) => {
    const [year, month] = m.split('-')
    return `${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][parseInt(month)-1]} '${year.slice(2)}`
  }

  const chartData = emissions.map(m => ({
    month: fmtMonth(m.month),
    'Scope 1': Math.round(m.scope1_kg_co2e / 1000),
    'Scope 2': Math.round(m.scope2_kg_co2e / 1000),
  }))

  const typeLabels = {
    VEH: 'Vehicle', EQP: 'Equipment', ENV: 'Environmental',
    DUS: 'Dust/Air', SLP: 'Slip/Trip', OTH: 'Other', ELE: 'Electrical'
  }

  const severityLabel = (s) => s === 1 ? 'Low' : s === 2 ? 'Medium' : 'High'

  return (
    <div className="app">

      <div className="header">
        <h1>Ironbark Ridge Resources — ESG Dashboard</h1>
        <p>January 2025 – June 2026 · 18 months of operational data · Queensland, Australia</p>
      </div>

      <div className="stat-row">
        <div className="stat-card scope1">
          <div className="label">Total Scope 1 Emissions</div>
          <div className="value">{fmt(totalScope1)}</div>
          <div className="sub">CO₂e from fuel combustion</div>
        </div>
        <div className="stat-card scope2">
          <div className="label">Total Scope 2 Emissions</div>
          <div className="value">{fmt(totalScope2)}</div>
          <div className="sub">CO₂e from grid electricity</div>
        </div>
        <div className="stat-card warning">
          <div className="label">Total Incidents</div>
          <div className="value">{totalIncidents}</div>
          <div className="sub">{inconsistentCount} severity mismatches flagged</div>
        </div>
        <div className="stat-card alert">
          <div className="label">Psychosocial Risks</div>
          <div className="value">{psychosocialCount}</div>
          <div className="sub">AI-detected · requires review</div>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <h2>Monthly Emissions <span>tonnes CO₂e</span></h2>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="month" tick={{ fontSize: 11 }} interval={2} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="Scope 1" stroke="#e53e3e" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="Scope 2" stroke="#3182ce" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h2>Incidents by Type <span>all 18 months</span></h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={incidents.by_type.map(t => ({
              type: typeLabels[t.type_code] || t.type_code,
              count: t.count
            }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
              <XAxis dataKey="type" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#3182ce" radius={[4, 4, 0, 0]} maxBarSize={48} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="full-card">
        <h2>⚠️ AI-Detected Psychosocial Hazards <span>{psychosocialCount} incidents</span></h2>
        <table className="incident-table">
          <thead>
            <tr>
              <th>Incident ID</th>
              <th>Date</th>
              <th>Category</th>
              <th>Description</th>
              <th>AI Finding</th>
            </tr>
          </thead>
          <tbody>
            {incidents.psychosocial_flags.map(inc => (
              <tr key={inc.incident_id}>
                <td><strong>{inc.incident_id}</strong></td>
                <td>{inc.incident_date}</td>
                <td><span className="badge psychosocial">{inc.ai_category}</span></td>
                <td>{inc.description}</td>
                <td>
                  {inc.ai_severity_inconsistency_reason
                    ? <div className="reason-text">{inc.ai_severity_inconsistency_reason}</div>
                    : <span style={{ color: '#888', fontSize: 12 }}>No severity issue</span>
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="full-card">
        <h2>🔴 Severity Mismatches <span>{inconsistentCount} flagged by AI</span></h2>
        <table className="incident-table">
          <thead>
            <tr>
              <th>Incident ID</th>
              <th>Date</th>
              <th>Recorded Severity</th>
              <th>Description</th>
              <th>AI Finding</th>
            </tr>
          </thead>
          <tbody>
            {incidents.severity_inconsistencies.map(inc => (
              <tr key={inc.incident_id}>
                <td><strong>{inc.incident_id}</strong></td>
                <td>{inc.incident_date}</td>
                <td><span className={`badge severity-${inc.severity}`}>{severityLabel(inc.severity)}</span></td>
                <td>{inc.description}</td>
                <td><div className="reason-text">{inc.ai_severity_inconsistency_reason}</div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="full-card">
        <h2>🔍 Data Quality Report <span>auto-detected during ingestion</span></h2>
        <div className="quality-row">
          <div className="quality-item">
            <div className="q-value">{quality.total_issues}</div>
            <div className="q-label">Total Issues</div>
          </div>
          {Object.entries(quality.by_file).map(([file, count]) => (
            <div className="quality-item" key={file}>
              <div className="q-value">{count}</div>
              <div className="q-label">{file.replace('.csv', '')}</div>
            </div>
          ))}
          {Object.entries(quality.by_action).map(([action, count]) => (
            <div className={`quality-item ${action}`} key={action}>
              <div className="q-value">{count}</div>
              <div className="q-label">{action}</div>
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}

export default App