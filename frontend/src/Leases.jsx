import { useCallback, useEffect, useMemo, useState } from 'react'

const emptyForm = {
  property_id: '',
  unit_id: '',
  tenant_id: '',
  start_date: '',
  end_date: '',
  monthly_rent: '',
  due_day: 1,
}

const cardStyle = {
  padding: '16px',
  border: '1px solid #ccc',
  borderRadius: '8px',
  marginBottom: '12px',
}

function statusColor(status, expiringSoon) {
  if (expiringSoon) return '#b45309'
  if (status === 'active') return '#15803d'
  if (status === 'upcoming') return '#1d4ed8'
  return '#6b7280'
}

function formatRent(amount) {
  const value = Number(amount)
  if (Number.isNaN(value)) return amount
  return `$${value.toFixed(2)}`
}

function Leases({ apiUrl }) {
  const [leases, setLeases] = useState([])
  const [properties, setProperties] = useState([])
  const [tenants, setTenants] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(emptyForm)

  const selectedProperty = useMemo(
    () => properties.find((property) => String(property.id) === String(form.property_id)),
    [properties, form.property_id],
  )
  const availableUnits = selectedProperty?.unit_list || []

  const loadLeasesData = useCallback(async () => {
    try {
      const [leasesRes, propertiesRes, tenantsRes] = await Promise.all([
        fetch(`${apiUrl}/leases`),
        fetch(`${apiUrl}/properties`),
        fetch(`${apiUrl}/tenants`),
      ])

      if (!leasesRes.ok) throw new Error('Unable to load leases')
      if (!propertiesRes.ok) throw new Error('Unable to load properties')
      if (!tenantsRes.ok) throw new Error('Unable to load tenants')

      const [leasesData, propertiesData, tenantsData] = await Promise.all([
        leasesRes.json(),
        propertiesRes.json(),
        tenantsRes.json(),
      ])

      setLeases(leasesData)
      setProperties(propertiesData)
      setTenants(tenantsData)
      setError('')
    } catch (err) {
      setError(err.message || 'Unable to load lease data')
    } finally {
      setLoading(false)
    }
  }, [apiUrl])

  useEffect(() => {
    loadLeasesData()
  }, [loadLeasesData])

  function startCreate() {
    setEditingId(null)
    setForm(emptyForm)
  }

  function startEdit(lease) {
    setEditingId(lease.id)
    setForm({
      property_id: String(lease.property_id),
      unit_id: String(lease.unit_id),
      tenant_id: String(lease.tenant_id),
      start_date: lease.start_date,
      end_date: lease.end_date,
      monthly_rent: String(lease.monthly_rent),
      due_day: lease.due_day,
    })
  }

  function updateField(name, value) {
    setForm((current) => {
      const next = { ...current, [name]: value }
      if (name === 'property_id') {
        next.unit_id = ''
      }
      return next
    })
  }

  async function saveLease(event) {
    event.preventDefault()
    setSaving(true)
    setError('')

    const payload = {
      property_id: Number(form.property_id),
      unit_id: Number(form.unit_id),
      tenant_id: Number(form.tenant_id),
      start_date: form.start_date,
      end_date: form.end_date,
      monthly_rent: Number(form.monthly_rent),
      due_day: Number(form.due_day),
    }

    try {
      const url = editingId
        ? `${apiUrl}/leases/${editingId}`
        : `${apiUrl}/leases`
      const response = await fetch(url, {
        method: editingId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data.error || 'Could not save lease')
      }

      startCreate()
      await loadLeasesData()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function deleteLease(leaseId) {
    if (!window.confirm('Delete this lease?')) return

    setError('')
    try {
      const response = await fetch(`${apiUrl}/leases/${leaseId}`, {
        method: 'DELETE',
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data.error || 'Could not delete lease')
      }
      if (editingId === leaseId) {
        startCreate()
      }
      await loadLeasesData()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Leases ({leases.length})</h2>
      <p>Connect a tenant to a specific property unit. Overlapping leases on the same unit are not allowed.</p>

      {error && <p style={{ color: 'red' }}>{error}</p>}

      {loading ? (
        <p>Loading leases...</p>
      ) : leases.length === 0 ? (
        <p>No leases added yet.</p>
      ) : (
        <div>
          {leases.map((lease) => (
            <div key={lease.id} style={cardStyle}>
              <h3>{lease.tenant_name}</h3>
              <p>
                Property: {lease.property_address}, {lease.property_city}
              </p>
              <p>Unit: {lease.unit_label}</p>
              <p>
                Lease: {lease.start_date} to {lease.end_date}
              </p>
              <p>Monthly rent: {formatRent(lease.monthly_rent)}</p>
              <p>Rent due day: {lease.due_day}</p>
              <p style={{ color: statusColor(lease.status, lease.expiring_soon), fontWeight: 'bold' }}>
                Status: {lease.status}
                {lease.expiring_soon ? ' — expiring within 30 days' : ''}
              </p>
              <p>
                <button type="button" onClick={() => startEdit(lease)}>
                  Edit
                </button>
                {' '}
                <button type="button" onClick={() => deleteLease(lease.id)}>
                  Delete
                </button>
              </p>
            </div>
          ))}
        </div>
      )}

      <hr />

      <h2>{editingId ? 'Edit Lease' : 'Add New Lease'}</h2>

      {properties.length === 0 || tenants.length === 0 ? (
        <p>Add at least one property and one tenant before creating a lease.</p>
      ) : (
        <form onSubmit={saveLease}>
          <p>
            <label>
              Property:{' '}
              <select
                value={form.property_id}
                onChange={(e) => updateField('property_id', e.target.value)}
                required
              >
                <option value="">Select a property</option>
                {properties.map((property) => (
                  <option key={property.id} value={property.id}>
                    {property.address}, {property.city}
                  </option>
                ))}
              </select>
            </label>
          </p>

          <p>
            <label>
              Unit:{' '}
              <select
                value={form.unit_id}
                onChange={(e) => updateField('unit_id', e.target.value)}
                required
                disabled={!form.property_id}
              >
                <option value="">Select a unit</option>
                {availableUnits.map((unit) => (
                  <option key={unit.id} value={unit.id}>
                    {unit.unit_label}
                  </option>
                ))}
              </select>
            </label>
          </p>

          <p>
            <label>
              Tenant:{' '}
              <select
                value={form.tenant_id}
                onChange={(e) => updateField('tenant_id', e.target.value)}
                required
              >
                <option value="">Select a tenant</option>
                {tenants.map((tenant) => (
                  <option key={tenant.id} value={tenant.id}>
                    {tenant.name}
                  </option>
                ))}
              </select>
            </label>
          </p>

          <p>
            <label>
              Start date:{' '}
              <input
                type="date"
                value={form.start_date}
                onChange={(e) => updateField('start_date', e.target.value)}
                required
              />
            </label>
          </p>

          <p>
            <label>
              End date:{' '}
              <input
                type="date"
                value={form.end_date}
                onChange={(e) => updateField('end_date', e.target.value)}
                required
              />
            </label>
          </p>

          <p>
            <label>
              Monthly rent:{' '}
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={form.monthly_rent}
                onChange={(e) => updateField('monthly_rent', e.target.value)}
                required
              />
            </label>
          </p>

          <p>
            <label>
              Rent due day (1-28):{' '}
              <input
                type="number"
                min="1"
                max="28"
                value={form.due_day}
                onChange={(e) => updateField('due_day', e.target.value)}
                required
              />
            </label>
          </p>

          <button type="submit" disabled={saving}>
            {saving ? 'Saving...' : editingId ? 'Update Lease' : 'Add Lease'}
          </button>
          {editingId && (
            <>
              {' '}
              <button type="button" onClick={startCreate} disabled={saving}>
                Cancel
              </button>
            </>
          )}
        </form>
      )}
    </section>
  )
}

export default Leases
