import { useEffect, useState } from 'react'
import Leases from './Leases.jsx'
import Records from './Records.jsx'
import Payments from './Payments.jsx'
import './App.css'

const API_URL = 'http://127.0.0.1:5000/api'
const nav = [
  ['dashboard', 'Overview', '◫'], ['properties', 'Properties', '⌂'],
  ['tenants', 'Tenants', '♙'], ['leases', 'Leases', '▤'],
  ['payments', 'Rent payments', '↗'], ['reports', 'Reports', '▥'],
]
const titles = {
  dashboard: ['Dashboard', 'Your portfolio at a glance'],
  properties: ['Properties', 'Manage your rental portfolio'],
  tenants: ['Tenants', 'Keep tenant information up to date'],
  leases: ['Leases', 'Manage occupancy and lease agreements'],
  payments: ['Rent payments', 'Stay on top of collections and balances'],
  reports: ['Reports', 'Understand your rental income'],
}
const money = n => new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD', maximumFractionDigits: 2 }).format(Number(n) || 0)
const localMonth = () => {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}
function Label({ status }) {
  const type = String(status || '').toLowerCase()
  const tone = type.includes('overdue') ? 'danger' : type.includes('paid') ? 'success' : type.includes('upcoming') ? 'info' : 'warning'
  return <span className={`status-pill ${tone}`}>{status}</span>
}
function Dashboard({ apiUrl, reports = false, revision, goTo }) {
  const [month, setMonth] = useState(localMonth())
  const [overview, setOverview] = useState(null)
  const [properties, setProperties] = useState([])
  const [tenants, setTenants] = useState([])
  const [leases, setLeases] = useState([])
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    async function load() {
      try {
        const paths = [`/rent-overview?month=${month}`, '/properties', '/tenants', '/leases']
        const result = await Promise.all(paths.map(async p => {
          const res = await fetch(`${apiUrl}${p}`)
          if (!res.ok) throw new Error('Could not load your portfolio data')
          return res.json()
        }))
        if (active) {
          setOverview(result[0]); setProperties(result[1]); setTenants(result[2]); setLeases(result[3]); setError('')
        }
      } catch (e) { if (active) setError(e.message) }
    }
    load()
    return () => { active = false }
  }, [apiUrl, month, revision])
  const rows = overview?.leases || []
  const upcoming = leases.filter(l => l.status === 'upcoming').length
  const expiring = leases.filter(l => l.expiring_soon).length
  const stats = [
    ['Expected rent', money(overview?.expected_total), 'For the selected month', 'violet'],
    ['Collected', money(overview?.collected_total), 'Received toward monthly rent', 'green'],
    ['Outstanding', money(overview?.outstanding_total), 'Still to be collected', 'amber'],
    ['Overdue', money(overview?.overdue_total), 'Past the due date', 'red'],
  ]
  return <div className="dashboard-content">
    <div className="toolbar"><div><h2>{reports ? 'Financial performance' : 'Portfolio performance'}</h2><p>Rent collection for {month}</p></div><label className="month-filter">Reporting month <input type="month" value={month} onChange={e => setMonth(e.target.value)} /></label></div>
    {error && <p role="alert" className="alert error">{error}</p>}
    <div className="metric-grid">{stats.map(([name, value, sub, tone]) => <article key={name} className="metric-card"><span className={`metric-dot ${tone}`}></span><span className="metric-title">{name}</span><strong>{overview ? value : '—'}</strong><small>{sub}</small></article>)}</div>
    {!reports && <div className="portfolio-grid">
      <div className="panel"><div className="panel-title"><h3>Portfolio snapshot</h3><span className="subtle">Live records</span></div><div className="snapshot-grid">
        <div><strong>{properties.length}</strong><span>Properties</span></div><div><strong>{properties.reduce((sum, p) => sum + (Number(p.units) || 0), 0)}</strong><span>Total units</span></div><div><strong>{tenants.length}</strong><span>Tenants</span></div><div><strong>{leases.filter(l => l.status === 'active').length}</strong><span>Active leases</span></div>
      </div></div>
      <div className="panel"><div className="panel-title"><h3>Needs attention</h3><span className="subtle">Lease and rent alerts</span></div><div className="attention-row"><span className="attention-icon red">!</span><div><b>{rows.filter(r => r.overdue).length} overdue rent account(s)</b><small>Review outstanding collections</small></div></div><div className="attention-row"><span className="attention-icon amber">↗</span><div><b>{expiring} lease(s) expiring soon</b><small>Within the next 30 days</small></div></div><div className="attention-row"><span className="attention-icon blue">◷</span><div><b>{upcoming} upcoming lease(s)</b><small>Scheduled to begin later</small></div></div></div>
    </div>}
    <div className="panel"><div className="panel-title"><div><h3>{reports ? 'Rent ledger' : 'Monthly rent status'}</h3><p>Collection progress by lease for {month}</p></div>{!reports && <button className="button-quiet" onClick={() => goTo('payments')}>View payments →</button>}</div>
      {rows.length === 0 ? <div className="empty-state">No rent is due for this month.</div> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Tenant / property</th><th>Due date</th><th>Expected</th><th>Collected</th><th>Balance</th><th>Status</th></tr></thead><tbody>{rows.map(r => <tr key={r.lease_id}><td><b>{r.tenant}</b><small>{r.property} / {r.unit}</small></td><td>{r.due_date}</td><td>{money(r.monthly_rent)}</td><td>{money(r.amount_paid)}</td><td>{money(r.outstanding)}</td><td><Label status={r.partial && r.overdue ? 'Overdue (partial)' : r.status} /></td></tr>)}</tbody></table></div>}
    </div>
    {reports && <p className="report-note">This report shows scheduled rent and recorded collections for a selected month. It does not include operating expenses or calculate net profit.</p>}
  </div>
}
export default function App() {
  const [page, setPage] = useState('dashboard')
  const [revision, setRevision] = useState(0)
  const [menuOpen, setMenuOpen] = useState(false)
  const selectPage = id => { setPage(id); setMenuOpen(false); window.scrollTo(0, 0) }
  return <div className="app-shell">
    <aside className={`sidebar ${menuOpen ? 'show' : ''}`}>
      <div className="brand"><div className="brand-mark">R<span>↗</span></div><div><strong>RentWise</strong><small>PROPERTY MANAGER</small></div></div>
      <div className="sidebar-label">WORKSPACE</div>
      <nav className="nav-list" aria-label="Main navigation">{nav.map(([id, label, symbol]) => <button key={id} className={`nav-link ${page === id ? 'active' : ''}`} onClick={() => selectPage(id)}><span className="nav-symbol">{symbol}</span>{label}</button>)}</nav>
      <div className="sidebar-bottom"><div className="help-card"><b>Built for better rentals.</b><p>One workspace for leases, tenants, and income.</p></div><div className="workspace-profile"><div className="avatar">RW</div><div><b>My workspace</b><small>Local portfolio</small></div><span className="profile-dots">···</span></div></div>
    </aside>
    {menuOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
    <div className="main-area"><header className="topbar"><button className="mobile-menu" onClick={() => setMenuOpen(v => !v)} aria-label="Open navigation">☰</button><div className="breadcrumb">Workspace <span>/</span> <b>{titles[page][0]}</b></div><div className="topbar-right"><span className="online-dot" /> Local workspace</div></header>
      <main className="page-content"><div className="page-heading"><div><p className="eyebrow">PROPERTY MANAGEMENT</p><h1>{titles[page][0]}</h1><p>{titles[page][1]}</p></div>{page === 'dashboard' && <button className="button-primary" onClick={() => selectPage('payments')}>+ Record payment</button>}</div>
      {page === 'dashboard' && <Dashboard apiUrl={API_URL} revision={revision} goTo={selectPage} />}
      {(page === 'properties' || page === 'tenants') && <div className="panel page-panel"><Records apiUrl={API_URL} mode={page} onChanged={() => setRevision(v => v+1)} /></div>}
      {page === 'leases' && <div className="panel page-panel"><Leases key={revision} apiUrl={API_URL} /></div>}
      {page === 'payments' && <div className="panel page-panel"><Payments apiUrl={API_URL} /></div>}
      {page === 'reports' && <Dashboard apiUrl={API_URL} reports revision={revision} goTo={selectPage} />}
      <footer className="app-footer">© {new Date().getFullYear()} RentWise · Rental property management, made simpler.</footer></main></div>
  </div>
}
