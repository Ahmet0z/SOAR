import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import EntityList from './EntityList'
import ContextEditor from './ContextEditor'
import ContextSchemaManager from './ContextSchemaManager'
import { apiClient } from '../api/client'

const defaultIndicator = {
  name: '',
  indicator_type: '',
  confidence: 50
}

function IndicatorsPanel() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState(null)
  const [form, setForm] = useState({ ...defaultIndicator })

  const indicatorsQuery = useQuery({
    queryKey: ['indicators'],
    queryFn: () => apiClient.getIndicators()
  })

  const schemaQuery = useQuery({
    queryKey: ['context-schema', 'indicators'],
    queryFn: () => apiClient.getContextSchema('indicators')
  })

  const selectedIndicator = useMemo(
    () => indicatorsQuery.data?.find((item) => item.id === selectedId),
    [indicatorsQuery.data, selectedId]
  )

  useEffect(() => {
    if (selectedIndicator) {
      setForm({
        name: selectedIndicator.name,
        indicator_type: selectedIndicator.indicator_type,
        confidence: selectedIndicator.confidence
      })
    } else {
      setForm({ ...defaultIndicator })
    }
  }, [selectedIndicator])

  const createMutation = useMutation({
    mutationFn: (payload) => apiClient.createIndicator(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['indicators'] })
      setForm({ ...defaultIndicator })
    }
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }) => apiClient.updateIndicator(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['indicators'] })
  })

  const deleteMutation = useMutation({
    mutationFn: (id) => apiClient.deleteIndicator(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['indicators'] })
      setSelectedId(null)
    }
  })

  const contextAddMutation = useMutation({
    mutationFn: ({ id, key, value }) => apiClient.addIndicatorContext(id, { key, value }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['indicators'] })
  })

  const contextRemoveMutation = useMutation({
    mutationFn: ({ id, key }) => apiClient.removeIndicatorContext(id, key),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['indicators'] })
  })

  const schemaCreateMutation = useMutation({
    mutationFn: (payload) => apiClient.upsertContextSchema('indicators', payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['context-schema', 'indicators'] })
  })

  const schemaDeleteMutation = useMutation({
    mutationFn: (fieldKey) => apiClient.deleteContextSchemaField('indicators', fieldKey),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['context-schema', 'indicators'] })
  })

  const handleSubmit = (event) => {
    event.preventDefault()
    const payload = { ...form, context: selectedIndicator?.context ?? {} }
    if (selectedIndicator) {
      updateMutation.mutate({ id: selectedIndicator.id, payload })
    } else {
      createMutation.mutate({ ...payload, context: {} })
    }
  }

  const handleDelete = () => {
    if (selectedIndicator) {
      deleteMutation.mutate(selectedIndicator.id)
    }
  }

  const indicators = indicatorsQuery.data ?? []
  const schema = schemaQuery.data ?? []

  return (
    <div className="panel-grid">
      <div className="panel-column">
        <div className="panel-header">
          <h2>Indicator Listesi</h2>
          <button type="button" className="ghost" onClick={() => setSelectedId(null)}>
            Yeni Indicator
          </button>
        </div>
        {indicatorsQuery.isLoading ? (
          <p>Yükleniyor...</p>
        ) : (
          <EntityList
            items={indicators}
            selectedId={selectedId}
            onSelect={setSelectedId}
            getPrimary={(item) => item.name}
            getSecondary={(item) => `${item.indicator_type} • Güven: ${item.confidence}`}
          />
        )}
      </div>

      <div className="panel-column">
        <form onSubmit={handleSubmit} className="form-card">
          <h2>{selectedIndicator ? 'Indicator Güncelle' : 'Indicator Oluştur'}</h2>
          <label>
            Ad
            <input
              value={form.name}
              onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
              required
            />
          </label>
          <label>
            Tip
            <input
              value={form.indicator_type}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, indicator_type: event.target.value }))
              }
              required
            />
          </label>
          <label>
            Güven Skoru
            <input
              type="number"
              min="0"
              max="100"
              value={form.confidence}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, confidence: Number(event.target.value) }))
              }
            />
          </label>
          <div className="form-actions">
            {selectedIndicator && (
              <button type="button" className="ghost" onClick={handleDelete}>
                Sil
              </button>
            )}
            <button type="submit">{selectedIndicator ? 'Güncelle' : 'Oluştur'}</button>
          </div>
        </form>

        {selectedIndicator && (
          <ContextEditor
            context={selectedIndicator.context}
            schema={schema}
            onAdd={(key, value) => contextAddMutation.mutate({ id: selectedIndicator.id, key, value })}
            onRemove={(key) => contextRemoveMutation.mutate({ id: selectedIndicator.id, key })}
          />
        )}
      </div>

      <div className="panel-column full">
        <ContextSchemaManager
          entityLabel="Indicator"
          schema={schema}
          onCreate={(payload) => schemaCreateMutation.mutateAsync(payload)}
          onDelete={(fieldKey) => schemaDeleteMutation.mutate(fieldKey)}
          onHistory={(fieldKey) => apiClient.getContextFieldHistory('indicators', fieldKey)}
        />
      </div>
    </div>
  )
}

export default IndicatorsPanel
