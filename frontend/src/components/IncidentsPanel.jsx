import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import EntityList from './EntityList'
import ContextEditor from './ContextEditor'
import ContextSchemaManager from './ContextSchemaManager'
import { apiClient } from '../api/client'

const defaultIncident = {
  title: '',
  description: '',
  severity: 'medium',
  context: {}
}

function IncidentsPanel() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState(null)
  const [form, setForm] = useState({ ...defaultIncident })

  const incidentsQuery = useQuery({
    queryKey: ['incidents'],
    queryFn: () => apiClient.getIncidents()
  })

  const schemaQuery = useQuery({
    queryKey: ['context-schema', 'incidents'],
    queryFn: () => apiClient.getContextSchema('incidents')
  })

  const selectedIncident = useMemo(
    () => incidentsQuery.data?.find((item) => item.id === selectedId),
    [incidentsQuery.data, selectedId]
  )

  useEffect(() => {
    if (selectedIncident) {
      setForm({
        title: selectedIncident.title,
        description: selectedIncident.description ?? '',
        severity: selectedIncident.severity,
        context: selectedIncident.context
      })
    } else {
      setForm({ ...defaultIncident })
    }
  }, [selectedIncident])

  const createMutation = useMutation({
    mutationFn: (payload) => apiClient.createIncident(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
      setForm({ ...defaultIncident })
    }
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }) => apiClient.updateIncident(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
    }
  })

  const deleteMutation = useMutation({
    mutationFn: (id) => apiClient.deleteIncident(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
      setSelectedId(null)
    }
  })

  const contextAddMutation = useMutation({
    mutationFn: ({ id, key, value }) => apiClient.addIncidentContext(id, { key, value }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['incidents'] })
  })

  const contextRemoveMutation = useMutation({
    mutationFn: ({ id, key }) => apiClient.removeIncidentContext(id, key),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['incidents'] })
  })

  const schemaCreateMutation = useMutation({
    mutationFn: (payload) => apiClient.upsertContextSchema('incidents', payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['context-schema', 'incidents'] })
  })

  const schemaDeleteMutation = useMutation({
    mutationFn: (fieldKey) => apiClient.deleteContextSchemaField('incidents', fieldKey),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['context-schema', 'incidents'] })
  })

  const handleSubmit = (event) => {
    event.preventDefault()
    if (selectedIncident) {
      updateMutation.mutate({ id: selectedIncident.id, payload: form })
    } else {
      createMutation.mutate(form)
    }
  }

  const handleDelete = () => {
    if (selectedIncident) {
      deleteMutation.mutate(selectedIncident.id)
    }
  }

  const incidents = incidentsQuery.data ?? []
  const schema = schemaQuery.data ?? []

  return (
    <div className="panel-grid">
      <div className="panel-column">
        <div className="panel-header">
          <h2>Incident Listesi</h2>
          <button type="button" className="ghost" onClick={() => setSelectedId(null)}>
            Yeni Incident
          </button>
        </div>
        {incidentsQuery.isLoading ? (
          <p>Yükleniyor...</p>
        ) : (
          <EntityList
            items={incidents}
            selectedId={selectedId}
            onSelect={setSelectedId}
            getPrimary={(item) => item.title}
            getSecondary={(item) => `${item.severity.toUpperCase()} • ${item.description ?? 'Açıklama yok'}`}
          />
        )}
      </div>

      <div className="panel-column">
        <form onSubmit={handleSubmit} className="form-card">
          <h2>{selectedIncident ? 'Incident Güncelle' : 'Incident Oluştur'}</h2>
          <label>
            Başlık
            <input
              value={form.title}
              onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
              required
            />
          </label>
          <label>
            Açıklama
            <textarea
              value={form.description}
              onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
            />
          </label>
          <label>
            Seviye
            <select
              value={form.severity}
              onChange={(event) => setForm((prev) => ({ ...prev, severity: event.target.value }))}
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </label>
          <div className="form-actions">
            {selectedIncident && (
              <button type="button" className="ghost" onClick={handleDelete}>
                Sil
              </button>
            )}
            <button type="submit">
              {selectedIncident ? 'Güncelle' : 'Oluştur'}
            </button>
          </div>
        </form>

        {selectedIncident && (
          <ContextEditor
            context={selectedIncident.context}
            schema={schema}
            onAdd={(key, value) => contextAddMutation.mutate({ id: selectedIncident.id, key, value })}
            onRemove={(key) => contextRemoveMutation.mutate({ id: selectedIncident.id, key })}
          />
        )}
      </div>

      <div className="panel-column full">
        <ContextSchemaManager
          entityLabel="Incident"
          schema={schema}
          onCreate={(payload) => schemaCreateMutation.mutateAsync(payload)}
          onDelete={(fieldKey) => schemaDeleteMutation.mutate(fieldKey)}
          onHistory={(fieldKey) => apiClient.getContextFieldHistory('incidents', fieldKey)}
        />
      </div>
    </div>
  )
}

export default IncidentsPanel
