import { useEffect, useState } from 'react'

const propertyBlank = { address: '', city: '', property_type: 'House', units: 1 }
const tenantBlank = { name: '', email: '', phone: '' }

export default function Records({ apiUrl, refreshKey, onChanged, mode = 'properties' }) {
  const [properties, setProperties] = useState([])
  const [tenants, setTenants] = useState([])
  const [editingProperty, setEditingProperty] = useState(null)
  const [editingTenant, setEditingTenant] = useState(null)
  const [tenantForm, setTenantForm] = useState(tenantBlank)
  const [propertyForm, setPropertyForm] = useState(propertyBlank)
  const [error, setError] = useState('')

  async function api(path, options) {
    const response = await fetch(`${apiUrl}${path}`, options)
    const body = await response.json()
    if (!response.ok) throw new Error(body.error || 'Request failed')
    return body
  }

  async function reload() {
    try {
      if (mode === 'properties') setProperties(await api('/properties'))
      else setTenants(await api('/tenants'))
      setError('')
    } catch (e) { setError(e.message) }
  }
  useEffect(() => { reload() }, [refreshKey, mode])

  async function submit(event, type) {
    event.preventDefault()
    const isProperty = type === 'properties'
    const id = isProperty ? editingProperty : editingTenant
    const form = isProperty ? propertyForm : tenantForm
    try {
      await api(`/${type}${id ? '/' + id : ''}`, { method: id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) })
      if (isProperty) { setEditingProperty(null); setPropertyForm(propertyBlank) }
      else { setEditingTenant(null); setTenantForm(tenantBlank) }
      await reload()
      onChanged?.()
    } catch (e) { setError(e.message) }
  }

  async function remove(type, id) {
    if (!window.confirm(`Delete this ${type === 'properties' ? 'property' : 'tenant'}? This cannot be undone.`)) return
    try { await api(`/${type}/${id}`, { method: 'DELETE' }); await reload(); onChanged?.() }
    catch (e) { setError(e.message) }
  }

  return <section>
    <h2>{mode === 'properties' ? 'Your properties' : 'Your tenants'}</h2>
    {error && <p role="alert" style={{ color: 'crimson' }}>{error}</p>}
    {mode === 'properties' && <>
    <h3>Properties</h3>
    {properties.map(p => <div key={p.id} style={{ padding: 8, borderBottom: '1px solid #ddd' }}>
      {p.address}, {p.city} — {p.units} unit(s) {' '}
      <button onClick={() => { setEditingProperty(p.id); setPropertyForm({ address:p.address, city:p.city, property_type:p.property_type || 'House', units:p.units }) }}>Edit</button>{' '}
      <button onClick={() => remove('properties', p.id)}>Delete</button>
    </div>)}
    <form onSubmit={e => submit(e, 'properties')}>
      <h4>{editingProperty ? 'Edit property' : 'Add property'}</h4>
      <input aria-label="Address" required placeholder="Address" value={propertyForm.address} onChange={e => setPropertyForm({ ...propertyForm, address:e.target.value })} />{' '}
      <input aria-label="City" required placeholder="City" value={propertyForm.city} onChange={e => setPropertyForm({ ...propertyForm, city:e.target.value })} />{' '}
      <select aria-label="Property type" value={propertyForm.property_type} onChange={e => setPropertyForm({ ...propertyForm, property_type:e.target.value })}>{['House','Apartment','Condo','Townhouse','Other'].map(x => <option key={x}>{x}</option>)}</select>{' '}
      <input aria-label="Number of units" type="number" min="1" required value={propertyForm.units} onChange={e => setPropertyForm({ ...propertyForm, units: Number(e.target.value) })} />{' '}
      <button type="submit">{editingProperty ? 'Save property' : 'Add property'}</button>{' '}
      {editingProperty && <button type="button" onClick={() => { setEditingProperty(null); setPropertyForm(propertyBlank) }}>Cancel</button>}
    </form>
    </>}
    {mode === 'tenants' && <>
    <h3>Tenants</h3>
    {tenants.map(t => <div key={t.id} style={{ padding:8, borderBottom:'1px solid #ddd' }}>
      {t.name} — {t.email || 'No email'} — {t.phone || 'No phone'} {' '}
      <button onClick={() => { setEditingTenant(t.id); setTenantForm({ name:t.name, email:t.email || '', phone:t.phone || '' }) }}>Edit</button>{' '}
      <button onClick={() => remove('tenants', t.id)}>Delete</button>
    </div>)}
    <form onSubmit={e => submit(e, 'tenants')}>
      <h4>{editingTenant ? 'Edit tenant' : 'Add tenant'}</h4>
      <input aria-label="Tenant name" required placeholder="Name" value={tenantForm.name} onChange={e => setTenantForm({ ...tenantForm, name:e.target.value })} />{' '}
      <input aria-label="Tenant email" type="email" placeholder="Email" value={tenantForm.email} onChange={e => setTenantForm({ ...tenantForm, email:e.target.value })} />{' '}
      <input aria-label="Tenant phone" placeholder="Phone" value={tenantForm.phone} onChange={e => setTenantForm({ ...tenantForm, phone:e.target.value })} />{' '}
      <button type="submit">{editingTenant ? 'Save tenant' : 'Add tenant'}</button>{' '}
      {editingTenant && <button type="button" onClick={() => { setEditingTenant(null); setTenantForm(tenantBlank) }}>Cancel</button>}
    </form>
    </>}
  </section>
}
