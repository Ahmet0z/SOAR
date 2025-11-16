import { useEffect, useMemo, useState } from 'react'
import ReactFlow, {
  useEdgesState,
  useNodesState,
  addEdge,
  Background,
  Controls,
  MiniMap
} from 'reactflow'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import EntityList from './EntityList'
import 'reactflow/dist/style.css'

const createId = () =>
  (typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2, 10))

function PlaybooksPanel() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState(null)
  const [form, setForm] = useState({ name: '', description: '' })
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [activeNodeId, setActiveNodeId] = useState(null)
  const [newNodeAutomation, setNewNodeAutomation] = useState('')
  const [runInput, setRunInput] = useState('{"initial_context": {}}')
  const [runResult, setRunResult] = useState(null)

  const playbooksQuery = useQuery({
    queryKey: ['playbooks'],
    queryFn: () => apiClient.getPlaybooks()
  })

  const automationsQuery = useQuery({
    queryKey: ['automations'],
    queryFn: () => apiClient.getAutomations()
  })

  const selectedPlaybook = useMemo(
    () => playbooksQuery.data?.find((item) => item.id === selectedId),
    [playbooksQuery.data, selectedId]
  )

  useEffect(() => {
    if (selectedPlaybook) {
      setForm({ name: selectedPlaybook.name, description: selectedPlaybook.description ?? '' })
      setNodes(
        (selectedPlaybook.nodes ?? []).map((node) => ({
          id: node.id,
          position: { x: node.x ?? 0, y: node.y ?? 0 },
          data: { label: node.label, automationId: node.automation_id }
        }))
      )
      setEdges(
        (selectedPlaybook.edges ?? []).map((edge) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          data: { condition: edge.condition ?? '' },
          label: edge.condition ?? ''
        }))
      )
    } else {
      setForm({ name: '', description: '' })
      setNodes([])
      setEdges([])
    }
    setActiveNodeId(null)
    setRunResult(null)
  }, [selectedPlaybook, setEdges, setNodes])

  const createMutation = useMutation({
    mutationFn: (payload) => apiClient.createPlaybook(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] })
      setForm({ name: '', description: '' })
      setNodes([])
      setEdges([])
    }
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }) => apiClient.updatePlaybook(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['playbooks'] })
  })

  const deleteMutation = useMutation({
    mutationFn: (id) => apiClient.deletePlaybook(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] })
      setSelectedId(null)
    }
  })

  const validateMutation = useMutation({
    mutationFn: (id) => apiClient.validatePlaybook(id),
    onSuccess: (result) => setRunResult(result)
  })

  const runMutation = useMutation({
    mutationFn: ({ id, payload }) => apiClient.runPlaybook(id, payload),
    onSuccess: (result) => setRunResult(result)
  })

  const handleSubmit = (event) => {
    event.preventDefault()
    const payload = {
      name: form.name,
      description: form.description,
      nodes: nodes.map((node) => ({
        id: node.id,
        label: node.data.label,
        automation_id: node.data.automationId,
        x: node.position.x,
        y: node.position.y
      })),
      edges: edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        condition: edge.data?.condition ?? ''
      }))
    }
    if (selectedPlaybook) {
      updateMutation.mutate({ id: selectedPlaybook.id, payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const handleDelete = () => {
    if (selectedPlaybook) {
      deleteMutation.mutate(selectedPlaybook.id)
    }
  }

  const handleConnect = (connection) => {
    setEdges((eds) => addEdge({ ...connection, id: createId(), label: '' }, eds))
  }

  const handleAddNode = () => {
    if (!newNodeAutomation) return
    const automation = automationsQuery.data?.find((item) => item.id === newNodeAutomation)
    setNodes((current) => [
      ...current,
      {
        id: createId(),
        position: { x: Math.random() * 400, y: Math.random() * 200 },
        data: { label: automation?.name ?? 'Adım', automationId: newNodeAutomation }
      }
    ])
    setNewNodeAutomation('')
  }

  const updateNode = (changes) => {
    setNodes((current) =>
      current.map((node) =>
        node.id === activeNodeId ? { ...node, data: { ...node.data, ...changes } } : node
      )
    )
  }

  const updateEdgeCondition = (edgeId, condition) => {
    setEdges((current) =>
      current.map((edge) =>
        edge.id === edgeId
          ? { ...edge, data: { ...edge.data, condition }, label: condition }
          : edge
      )
    )
  }

  const triggerValidation = () => {
    if (selectedPlaybook) {
      validateMutation.mutate(selectedPlaybook.id)
    }
  }

  const triggerRun = () => {
    if (!selectedPlaybook) return
    try {
      const payload = JSON.parse(runInput)
      runMutation.mutate({ id: selectedPlaybook.id, payload })
    } catch (err) {
      setRunResult({ execution_log: ['Geçersiz JSON: ' + err.message], final_context: {} })
    }
  }

  const playbooks = playbooksQuery.data ?? []
  const automations = automationsQuery.data ?? []
  const activeNode = nodes.find((node) => node.id === activeNodeId)

  return (
    <div className="panel-grid">
      <div className="panel-column">
        <div className="panel-header">
          <h2>Playbooklar</h2>
          <button type="button" className="ghost" onClick={() => setSelectedId(null)}>
            Yeni Playbook
          </button>
        </div>
        {playbooksQuery.isLoading ? (
          <p>Yükleniyor...</p>
        ) : (
          <EntityList
            items={playbooks}
            selectedId={selectedId}
            onSelect={setSelectedId}
            getPrimary={(item) => item.name}
            getSecondary={(item) => `${item.nodes.length} adım • ${item.edges.length} bağlantı`}
          />
        )}
      </div>

      <div className="panel-column full">
        <form onSubmit={handleSubmit} className="form-card">
          <h2>Playbook Tasarımı</h2>
          <label>
            Ad
            <input
              value={form.name}
              onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
              required
            />
          </label>
          <label>
            Açıklama
            <input
              value={form.description}
              onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
            />
          </label>
          <div className="flow-wrapper">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={handleConnect}
              onNodeClick={(_, node) => setActiveNodeId(node.id)}
              fitView
            >
              <MiniMap />
              <Controls />
              <Background gap={16} />
            </ReactFlow>
          </div>
          <div className="flow-actions">
            <select value={newNodeAutomation} onChange={(event) => setNewNodeAutomation(event.target.value)}>
              <option value="">Otomasyon seçin</option>
              {automations.map((automation) => (
                <option key={automation.id} value={automation.id}>
                  {automation.name}
                </option>
              ))}
            </select>
            <button type="button" onClick={handleAddNode}>
              Düğüm Ekle
            </button>
          </div>
          {activeNode && (
            <div className="node-editor">
              <h3>Seçili Düğüm</h3>
              <label>
                Etiket
                <input
                  value={activeNode.data.label}
                  onChange={(event) => updateNode({ label: event.target.value })}
                />
              </label>
              <label>
                Otomasyon
                <select
                  value={activeNode.data.automationId ?? ''}
                  onChange={(event) => updateNode({ automationId: event.target.value })}
                >
                  <option value="">Bağlı otomasyon yok</option>
                  {automations.map((automation) => (
                    <option key={automation.id} value={automation.id}>
                      {automation.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )}

          <div className="edge-list">
            <h3>Bağlantılar</h3>
            {!edges.length && <p className="empty-state">Bağlantı yok</p>}
            {edges.map((edge) => (
              <label key={edge.id}>
                {edge.source} → {edge.target}
                <input
                  value={edge.data?.condition ?? ''}
                  onChange={(event) => updateEdgeCondition(edge.id, event.target.value)}
                  placeholder="Koşul"
                />
              </label>
            ))}
          </div>

          <div className="form-actions">
            {selectedPlaybook && (
              <button type="button" className="ghost" onClick={handleDelete}>
                Sil
              </button>
            )}
            <button type="submit">{selectedPlaybook ? 'Güncelle' : 'Oluştur'}</button>
          </div>
        </form>

        {selectedPlaybook && (
          <div className="runner-card">
            <h3>Playbook Doğrulama / Çalıştırma</h3>
            <div className="runner-actions">
              <button type="button" onClick={triggerValidation} disabled={validateMutation.isLoading}>
                Doğrula
              </button>
              <button type="button" onClick={triggerRun} disabled={runMutation.isLoading}>
                Çalıştır
              </button>
            </div>
            <textarea value={runInput} onChange={(event) => setRunInput(event.target.value)} />
            {runResult && (
              <pre>{JSON.stringify(runResult, null, 2)}</pre>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default PlaybooksPanel
