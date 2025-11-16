import { useMemo, useState } from 'react'
import PropTypes from 'prop-types'

function ContextEditor({ context, schema, onAdd, onRemove }) {
  const [modalOpen, setModalOpen] = useState(false)
  const [selectedField, setSelectedField] = useState('')
  const [value, setValue] = useState('')
  const [error, setError] = useState('')

  const schemaMap = useMemo(() => {
    const map = {}
    schema.forEach((definition) => {
      map[definition.field_key] = definition
    })
    return map
  }, [schema])

  const openModal = () => {
    setSelectedField(schema[0]?.field_key ?? '')
    setValue('')
    setError('')
    setModalOpen(true)
  }

  const parseValue = (type, raw) => {
    if (type === 'integer') {
      return Number.parseInt(raw, 10)
    }
    if (type === 'boolean') {
      return raw === 'true' || raw === true
    }
    return raw
  }

  const handleAdd = async (event) => {
    event.preventDefault()
    const definition = schemaMap[selectedField]
    if (!definition) {
      setError('Lütfen şema alanı seçin')
      return
    }
    try {
      await onAdd(selectedField, parseValue(definition.field_type, value))
      setModalOpen(false)
    } catch (err) {
      setError(err.message)
    }
  }

  const entries = Object.entries(context ?? {})

  return (
    <div className="context-editor">
      <header>
        <h3>Context Alanları</h3>
        <button type="button" className="ghost" onClick={openModal} disabled={!schema.length}>
          Alan Ekle
        </button>
      </header>
      {!entries.length && <p className="empty-state">Henüz context alanı yok.</p>}
      <ul>
        {entries.map(([key, currentValue]) => (
          <li key={key}>
            <div>
              <strong>{key}</strong>
              <span>{String(currentValue)}</span>
            </div>
            <button type="button" onClick={() => onRemove(key)}>
              Sil
            </button>
          </li>
        ))}
      </ul>

      {modalOpen && (
        <div className="modal-backdrop">
          <form className="modal" onSubmit={handleAdd}>
            <h4>Context Alanı Ekle</h4>
            {error && <p className="error-text">{error}</p>}
            <label>
              Şema Alanı
              <select value={selectedField} onChange={(event) => setSelectedField(event.target.value)}>
                {schema.map((definition) => (
                  <option key={definition.field_key} value={definition.field_key}>
                    {definition.field_key} ({definition.field_type})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Değer
              <input value={value} onChange={(event) => setValue(event.target.value)} />
            </label>
            <div className="modal-actions">
              <button type="button" className="ghost" onClick={() => setModalOpen(false)}>
                Vazgeç
              </button>
              <button type="submit">Kaydet</button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}

ContextEditor.propTypes = {
  context: PropTypes.object,
  schema: PropTypes.array.isRequired,
  onAdd: PropTypes.func.isRequired,
  onRemove: PropTypes.func.isRequired
}

export default ContextEditor
