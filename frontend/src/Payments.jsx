import { useEffect, useState } from 'react'

const today = () => new Date().toLocaleDateString('en-CA')
const currentMonth = () => today().slice(0, 7)
const money = value => new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD' }).format(value || 0)

export default function Payments({ apiUrl }) {
  const [month, setMonth] = useState(currentMonth())
  const [overview, setOverview] = useState(null)
  const [history, setHistory] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ lease_id: '', amount_paid: '', payment_date: today() })

  async function api(url, opts) {
    const response = await fetch(`${apiUrl}${url}`, opts)
    const result = await response.json()
    if (!response.ok) throw new Error(result.error || 'Request failed')
    return result
  }
  async function reload() {
    try {
      const [summary, payments] = await Promise.all([
        api(`/rent-overview?month=${month}`),
        api(`/payments?month=${month}&include_voided=true`),
      ])
      setOverview(summary)
      setHistory(payments)
      setError('')
    } catch (err) { setError(err.message) }
  }
  useEffect(() => { reload() }, [month])
  async function submit(e) {
    e.preventDefault()
    setSaving(true); setError(''); setNotice('')
    try {
      await api('/payments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...form, lease_id: Number(form.lease_id), payment_month: month, amount_paid: form.amount_paid }) })
      setForm({ ...form, lease_id: '', amount_paid: '' })
      setNotice('Payment recorded successfully.')
      await reload()
    } catch (err) { setError(err.message) }
    finally { setSaving(false) }
  }
  async function voidEntry(id) {
    if (!window.confirm('Void this payment? It will remain visible in the audit history.')) return
    try {
      await api(`/payments/${id}/void`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason: 'Manual correction' }) })
      setNotice('Payment voided. The entry remains in the history.')
      await reload()
    } catch (err) { setError(err.message) }
  }

  return <section>
    <h2>Rent Payments</h2>
    <label>Tracking month <input type="month" value={month} onChange={e => setMonth(e.target.value)} /></label>
    {error && <p role="alert" style={{ color: 'crimson' }}>{error}</p>}
    {notice && <p role="status" style={{ color: 'green' }}>{notice}</p>}
    {overview && <>
      <div style={{ display:'flex', flexWrap:'wrap', gap:12, margin:'18px 0' }}>
        {[['Expected rent', overview.expected_total],['Collected', overview.collected_total],['Outstanding', overview.outstanding_total],['Overdue', overview.overdue_total]].map(([label, amount]) =>
          <div key={label} style={{ border:'1px solid #ccc', padding:16, borderRadius:10, flex:'1 1 150px' }}><small>{label}</small><h3>{money(amount)}</h3></div>
        )}
      </div>
      <h3>Monthly Rent Status</h3>
      {overview.leases.length === 0 ? <p>No leases are due in this month.</p> :
        <div style={{ overflowX:'auto' }}><table style={{ width:'100%', textAlign:'left', borderCollapse:'collapse' }}>
          <thead><tr>{['Tenant / Property','Due','Rent','Paid','Balance','Status'].map(x => <th key={x} style={{ padding:8, borderBottom:'1px solid #aaa' }}>{x}</th>)}</tr></thead>
          <tbody>{overview.leases.map(row => <tr key={row.lease_id}>
            <td style={{ padding:8 }}>{row.tenant}<br/><small>{row.property} / {row.unit}</small></td>
            <td>{row.due_date}</td><td>{money(row.monthly_rent)}</td><td>{money(row.amount_paid)}</td><td>{money(row.outstanding)}</td>
            <td><strong style={{ color: row.overdue ? 'crimson' : row.status === 'Paid' ? 'green' : 'inherit' }}>{row.status}{row.partial && row.overdue ? ' (partial)' : ''}</strong></td>
          </tr>)}</tbody>
        </table></div>}
      <h3>Record a Payment</h3>
      <form onSubmit={submit} style={{ display:'flex', flexWrap:'wrap', gap:10, alignItems:'end' }}>
        <label>Lease<br/><select required value={form.lease_id} onChange={e => setForm({ ...form, lease_id:e.target.value })}>
          <option value="">Select a lease</option>
          {overview.leases.filter(l => l.outstanding > 0).map(l => <option key={l.lease_id} value={l.lease_id}>{l.tenant} — {l.property} ({money(l.outstanding)} due)</option>)}
        </select></label>
        <label>Amount<br/><input required type="number" min="0.01" step="0.01" placeholder="0.00" value={form.amount_paid} onChange={e => setForm({ ...form, amount_paid:e.target.value })}/></label>
        <label>Payment date<br/><input required type="date" value={form.payment_date} onChange={e => setForm({ ...form, payment_date:e.target.value })}/></label>
        <button type="submit" disabled={saving || overview.leases.every(l => l.outstanding === 0)}>{saving ? 'Saving...' : 'Record payment'}</button>
      </form>
      <h3>Payment History — {month}</h3>
      {history.length === 0 ? <p>No recorded payments this month.</p> : <div style={{ overflowX:'auto' }}><table style={{ width:'100%', textAlign:'left' }}>
        <thead><tr><th>Date</th><th>Tenant / Property</th><th>Amount</th><th>Status</th><th>Action</th></tr></thead>
        <tbody>{history.map(p => <tr key={p.id}>
          <td>{p.payment_date}</td><td>{p.tenant} — {p.property} / {p.unit}</td><td>{money(p.amount_paid)}</td>
          <td>{p.voided_at ? 'Voided' : 'Recorded'}</td><td>{!p.voided_at && <button type="button" onClick={() => voidEntry(p.id)}>Void entry</button>}</td>
        </tr>)}</tbody>
      </table></div>}
    </>}
  </section>
}
