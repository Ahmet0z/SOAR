import { useState } from 'react'
import PropTypes from 'prop-types'

function ContextSchemaManager({ entityLabel, onCreate, onDelete, onHistory, schema = [] }) {
  const [form, setForm] = useState({ field_key: '', field_type: 'string', required: false })
  const [error, setError] = useState('')
  const [history, setHistory] = useState([])
  const [historyField, setHistoryField] = useState('')
  const [historyError, setHistoryError] = useState('')

  const handleChange = (event) => {
    const { name, value, type, checked } = event.target
    setForm((prev) => ({ ...prev, [name]: type === 'checkbox' ? checked : value }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!form.field_key) return
    try {
      setError('')
      await onCreate(form)
      setForm({ field_key: '', field_type: 'string', required: false })
    } catch (err) {
      setError(err.message)
    }
  }

  const loadHistory = async (fieldKey) => {
    if (!onHistory) return
    try {
      setHistoryError('')
      const response = await onHistory(fieldKey)
      setHistory(response)
      setHistoryField(fieldKey)
    } catch (err) {
      setHistoryField('')
      setHistory([])
      setHistoryError(err.message)
    }
  }

  return (
    <section className="schema-manager">
      <h3>{entityLabel} Context Şeması</h3>
      <div className="schema-grid">
        {error && <p className="error-text">{error}</p>}
        <form onSubmit={handleSubmit}>
          <label>
            Alan adı
            <input name="field_key" value={form.field_key} onChange={handleChange} />
          </label>
          <label>
            Tip
            <select name="field_type" value={form.field_type} onChange={handleChange}>
              <option value="string">Metin</option>
              <option value="integer">Sayı</option>
              <option value="boolean">Boolean</option>
            </select>
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              name="required"
              checked={form.required}
              onChange={handleChange}
            />
            Zorunlu alan
          </label>
          <button type="submit">Alan Kaydet</button>
        </form>
        <ul>
          {schema.map((definition) => (
            <li key={definition.id}>
              <div>
                <strong>{definition.field_key}</strong>
                <span>{definition.field_type}</span>
                {definition.required && <span className="tag">Zorunlu</span>}
                <span className="tag neutral">v{definition.version}</span>
              </div>
              <div className="schema-actions">
                <button type="button" onClick={() => loadHistory(definition.field_key)}>
                  Geçmişi Gör
                </button>
                <button type="button" onClick={() => onDelete(definition.field_key)}>
                  Sil
                </button>
              </div>
            </li>
          ))}
          {!schema.length && <li className="empty-state">Henüz alan yok.</li>}
        </ul>
        {(historyField || historyError) && (
          <div className="history-panel">
            <h4>
              {historyField ? `${historyField} alan geçmişi` : 'Şema Geçmişi'}
            </h4>
            {historyError && <p className="error-text">{historyError}</p>}
            {!!history.length && (
              <ul>
                {history.map((entry) => (
                  <li key={`${entry.field_key}-${entry.version}`}>
                    <span>v{entry.version}</span>
                    <span>{new Date(entry.created_at).toLocaleString()}</span>
                    <span>{entry.field_type}</span>
                    {entry.required && <span className="tag">Zorunlu</span>}
                  </li>
                ))}
              </ul>
            )}
            {!history.length && !historyError && <p>Henüz geçmiş bulunamadı.</p>}
          </div>
        )}
      </div>
    </section>
  )
}

ContextSchemaManager.propTypes = {
  entityLabel: PropTypes.string.isRequired,
  onCreate: PropTypes.func.isRequired,
  onDelete: PropTypes.func.isRequired,
  onHistory: PropTypes.func,
  schema: PropTypes.array
}

export default ContextSchemaManager
