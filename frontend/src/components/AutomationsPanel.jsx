import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import CodeMirror from '@uiw/react-codemirror'
import { python } from '@codemirror/lang-python'
import EntityList from './EntityList'
import { apiClient } from '../api/client'

const defaultCode = `def run(payload):
    context = payload.get("context", {})
    return {"message": f"Merhaba {context.get('user', 'analyst')}"}
`

function AutomationsPanel() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState(null)
  const [form, setForm] = useState({ name: '', description: '', python_code: defaultCode })
  const [testInput, setTestInput] = useState('{"context": {}}')
  const [runnerSettings, setRunnerSettings] = useState({ max_retries: 0, timeout_seconds: 60 })
  const [runnerError, setRunnerError] = useState('')
  const [activeRunId, setActiveRunId] = useState(null)
  const [metricsWindow, setMetricsWindow] = useState('24')
  const [metricsAutomationFilter, setMetricsAutomationFilter] = useState('all')
  const [liveRunnerStatus, setLiveRunnerStatus] = useState(null)
  const [eventStreamError, setEventStreamError] = useState('')
  const [eventConnected, setEventConnected] = useState(false)

  const automationsQuery = useQuery({
    queryKey: ['automations'],
    queryFn: () => apiClient.getAutomations()
  })

  const runsQuery = useQuery({
    queryKey: ['automation-runs', selectedId],
    queryFn: () => apiClient.getAutomationRuns(selectedId),
    enabled: Boolean(selectedId)
  })

  const runDetailsQuery = useQuery({
    queryKey: ['automation-run', activeRunId],
    queryFn: () => apiClient.getAutomationRun(activeRunId),
    enabled: Boolean(activeRunId)
  })

  const metricsQuery = useQuery({
    queryKey: ['automation-run-metrics', metricsWindow, metricsAutomationFilter],
    queryFn: () =>
      apiClient.getAutomationRunMetrics({
        window_hours: Number(metricsWindow),
        automation_id: metricsAutomationFilter !== 'all' ? metricsAutomationFilter : undefined
      }),
    keepPreviousData: true
  })

  const runnerStatusQuery = useQuery({
    queryKey: ['automation-runner-status'],
    queryFn: () => apiClient.getAutomationRunnerStatus(),
    retry: false
  })

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    if (!apiClient.token) return undefined
    let socket
    let reconnectTimer
    let active = true

    const handleRunUpdate = (run) => {
      if (!run || !run.id) return
      queryClient.setQueryData(['automation-run', run.id], run)
      queryClient.setQueryData(['automation-runs', run.automation_id], (existing = []) => {
        const filtered = existing.filter((item) => item.id !== run.id)
        const updated = [run, ...filtered]
        return updated.sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        )
      })
    }

    const handleMessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (!data?.type) return
        if (data.type === 'run_update') {
          handleRunUpdate(data.payload?.run)
        } else if (data.type === 'runner_status') {
          setLiveRunnerStatus(data.payload)
          queryClient.setQueryData(['automation-runner-status'], data.payload)
        } else if (data.type === 'metrics_refresh') {
          queryClient.invalidateQueries({ queryKey: ['automation-run-metrics'] })
        }
      } catch (err) {
        // ignore malformed events
      }
    }

    const connect = () => {
      socket = apiClient.openAutomationEventsSocket()
      socket.onopen = () => {
        if (!active) return
        setEventConnected(true)
        setEventStreamError('')
      }
      socket.onmessage = handleMessage
      socket.onerror = () => {
        setEventStreamError('Gerçek zamanlı bağlantı kesildi, tekrar bağlanılıyor...')
      }
      socket.onclose = () => {
        setEventConnected(false)
        if (active) {
          reconnectTimer = window.setTimeout(connect, 3000)
        }
      }
    }

    connect()

    return () => {
      active = false
      if (socket) {
        socket.close()
      }
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer)
      }
    }
  }, [queryClient, apiClient.token])

  const selectedAutomation = useMemo(
    () => automationsQuery.data?.find((item) => item.id === selectedId),
    [automationsQuery.data, selectedId]
  )

  useEffect(() => {
    if (selectedAutomation) {
      setForm({
        name: selectedAutomation.name,
        description: selectedAutomation.description ?? '',
        python_code: selectedAutomation.python_code
      })
    } else {
      setForm({ name: '', description: '', python_code: defaultCode })
    }
    setRunnerError('')
    setActiveRunId(null)
  }, [selectedAutomation])

  const createMutation = useMutation({
    mutationFn: (payload) => apiClient.createAutomation(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['automations'] })
      setForm({ name: '', description: '', python_code: defaultCode })
    }
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }) => apiClient.updateAutomation(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['automations'] })
  })

  const deleteMutation = useMutation({
    mutationFn: (id) => apiClient.deleteAutomation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['automations'] })
      setSelectedId(null)
    }
  })

  const queueRunMutation = useMutation({
    mutationFn: ({ id, payload }) => apiClient.queueAutomationRun(id, payload),
    onSuccess: (run, variables) => {
      setActiveRunId(run.id)
      setRunnerError('')
      queryClient.invalidateQueries({ queryKey: ['automation-runs', variables.id] })
    },
    onError: (error) => {
      setRunnerError(error.message)
    }
  })

  const requeueMutation = useMutation({
    mutationFn: (runId) => apiClient.requeueAutomationRun(runId),
    onSuccess: (_, runId) => {
      queryClient.invalidateQueries({ queryKey: ['automation-runs', selectedId] })
      if (activeRunId === runId) {
        setActiveRunId(null)
      }
    }
  })

  const handleSubmit = (event) => {
    event.preventDefault()
    if (selectedAutomation) {
      updateMutation.mutate({ id: selectedAutomation.id, payload: form })
    } else {
      createMutation.mutate(form)
    }
  }

  const handleDelete = () => {
    if (selectedAutomation) {
      deleteMutation.mutate(selectedAutomation.id)
    }
  }

  const runAutomation = () => {
    if (!selectedAutomation) return
    try {
      const parsed = JSON.parse(testInput)
      queueRunMutation.mutate({
        id: selectedAutomation.id,
        payload: {
          inputs: parsed,
          max_retries: Number(runnerSettings.max_retries) || 0,
          timeout_seconds: Number(runnerSettings.timeout_seconds) || 60
        }
      })
    } catch (err) {
      setRunnerError(`Geçersiz JSON girdisi: ${err.message}`)
    }
  }

  const handleRequeue = (runId) => {
    requeueMutation.mutate(runId)
  }

  const automations = automationsQuery.data ?? []
  const automationFilterOptions = useMemo(
    () => [
      { value: 'all', label: 'Tüm Otomasyonlar' },
      ...automations.map((automation) => ({ value: automation.id, label: automation.name }))
    ],
    [automations]
  )

  const metricsData = metricsQuery.data
  const chartData = metricsData?.per_hour ?? []
  const maxBucketValue = chartData.reduce((max, bucket) => {
    const total = bucket.success + bucket.failed + bucket.running + bucket.pending
    return total > max ? total : max
  }, 1)
  const workerStatus = liveRunnerStatus ?? runnerStatusQuery.data

  return (
    <div className="panel-grid">
      <div className="panel-column">
        <div className="panel-header">
          <h2>Otomasyonlar</h2>
          <button type="button" className="ghost" onClick={() => setSelectedId(null)}>
            Yeni Otomasyon
          </button>
        </div>
        {automationsQuery.isLoading ? (
          <p>Yükleniyor...</p>
        ) : (
          <EntityList
            items={automations}
            selectedId={selectedId}
            onSelect={setSelectedId}
            getPrimary={(item) => item.name}
            getSecondary={(item) => item.description ?? 'Açıklama yok'}
          />
        )}
      </div>

      <div className="panel-column code-editor">
        <form onSubmit={handleSubmit} className="form-card">
          <h2>{selectedAutomation ? 'Otomasyonu Güncelle' : 'Yeni Otomasyon'}</h2>
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
          <label>
            Python Kodu
            <CodeMirror
              value={form.python_code}
              extensions={[python()]}
              height="200px"
              onChange={(value) => setForm((prev) => ({ ...prev, python_code: value }))}
            />
          </label>
          <div className="form-actions">
            {selectedAutomation && (
              <button type="button" className="ghost" onClick={handleDelete}>
                Sil
              </button>
            )}
            <button type="submit">{selectedAutomation ? 'Güncelle' : 'Oluştur'}</button>
          </div>
        </form>

        {selectedAutomation && (
          <div className="runner-card">
            <h3>Otomasyonu Test Et</h3>
            <textarea value={testInput} onChange={(event) => setTestInput(event.target.value)} />
            <div className="runner-settings">
              <label>
                Maksimum Tekrar
                <input
                  type="number"
                  min="0"
                  max="5"
                  value={runnerSettings.max_retries}
                  onChange={(event) =>
                    setRunnerSettings((prev) => ({ ...prev, max_retries: event.target.value }))
                  }
                />
              </label>
              <label>
                Zaman Aşımı (sn)
                <input
                  type="number"
                  min="5"
                  max="600"
                  value={runnerSettings.timeout_seconds}
                  onChange={(event) =>
                    setRunnerSettings((prev) => ({ ...prev, timeout_seconds: event.target.value }))
                  }
                />
              </label>
            </div>
            <button type="button" onClick={runAutomation} disabled={queueRunMutation.isLoading}>
              {queueRunMutation.isLoading ? 'Kuyruğa Alınıyor...' : 'Çalıştır'}
            </button>
            {runnerError && <p className="error-text">{runnerError}</p>}
            {runDetailsQuery.error && <p className="error-text">{runDetailsQuery.error.message}</p>}
            {runDetailsQuery.data && (
              <div className="runner-result">
                <p>Çalışma Durumu: {runDetailsQuery.data.status}</p>
                <p>Deneme Sayısı: {runDetailsQuery.data.attempts}</p>
                <p>Bekleme Süresi: {runDetailsQuery.data.queue_latency_ms ?? 0} ms</p>
                <p>Süre: {runDetailsQuery.data.duration_ms ?? 0} ms</p>
                <p>Son Hata: {runDetailsQuery.data.last_error ?? '—'}</p>
                {runDetailsQuery.data.timed_out && <p className="tag warning">Zaman aşımı</p>}
                <pre>{JSON.stringify(runDetailsQuery.data.logs, null, 2)}</pre>
                {runDetailsQuery.data.output && (
                  <pre>{JSON.stringify(runDetailsQuery.data.output, null, 2)}</pre>
                )}
              </div>
            )}
            <div className="run-history">
              <h4>Son Çalışmalar</h4>
              {runsQuery.isLoading && <p>Yükleniyor...</p>}
              {!runsQuery.isLoading && (
                <ul>
                  {(runsQuery.data ?? []).map((run) => (
                    <li key={run.id}>
                      <div className="run-row">
                        <button type="button" onClick={() => setActiveRunId(run.id)}>
                          {run.status.toUpperCase()} • {new Date(run.created_at).toLocaleTimeString()} •
                          {` ${run.attempts}/${run.max_retries + 1}`} deneme
                          {run.timed_out && <span className="tag warning">Timeout</span>}
                        </button>
                        {run.status === 'failed' && (
                          <button
                            type="button"
                            className="ghost small"
                            disabled={requeueMutation.isLoading}
                            onClick={() => handleRequeue(run.id)}
                          >
                            {requeueMutation.isLoading ? 'Yeniden kuyruğa alınıyor...' : 'Yeniden kuyruğa al'}
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                  {!runsQuery.data?.length && <li>Henüz çalışma yok.</li>}
                </ul>
              )}
            </div>
          </div>
        )}
    </div>

      <div className="panel-column full">
        <div className="metrics-card">
          <div className="panel-header">
            <h2>Koşum geçmişi & kuyruk sağlığı</h2>
            <div className="metrics-controls">
              <label>
                Zaman aralığı
                <select value={metricsWindow} onChange={(event) => setMetricsWindow(event.target.value)}>
                  <option value="6">Son 6 saat</option>
                  <option value="12">Son 12 saat</option>
                  <option value="24">Son 24 saat</option>
                  <option value="72">Son 72 saat</option>
                </select>
              </label>
              <label>
                Otomasyon filtresi
                <select
                  value={metricsAutomationFilter}
                  onChange={(event) => setMetricsAutomationFilter(event.target.value)}
                >
                  {automationFilterOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          {metricsQuery.isLoading && <p>Metrikler yükleniyor...</p>}
          {metricsQuery.error && <p className="error-text">{metricsQuery.error.message}</p>}
          {!metricsQuery.isLoading && !metricsQuery.error && metricsData && (
            <>
              <div className="metrics-summary">
                <div className="metric-pill">
                  <span>Toplam</span>
                  <strong>{metricsData.total_runs}</strong>
                </div>
                <div className="metric-pill">
                  <span>Başarılı</span>
                  <strong>{metricsData.success_count}</strong>
                </div>
                <div className="metric-pill">
                  <span>Başarısız</span>
                  <strong>{metricsData.failed_count}</strong>
                </div>
                <div className="metric-pill">
                  <span>Timeout</span>
                  <strong>{metricsData.timeout_count}</strong>
                </div>
                <div className="metric-pill">
                  <span>Ort. süre (ms)</span>
                  <strong>{Math.round(metricsData.avg_duration_ms ?? 0)}</strong>
                </div>
                <div className="metric-pill">
                  <span>Ort. bekleme (ms)</span>
                  <strong>{Math.round(metricsData.avg_queue_latency_ms ?? 0)}</strong>
                </div>
              </div>
              <div className="metrics-chart">
                {chartData.map((bucket) => {
                  const total = bucket.success + bucket.failed + bucket.running + bucket.pending
                  const height = `${Math.max((total / maxBucketValue) * 100, 4)}%`
                  return (
                    <div className="metrics-bar" key={bucket.bucket_start}>
                      <div className="bar-stack" style={{ height }}>
                        <span className="bar-segment success" style={{ flex: bucket.success }} />
                        <span className="bar-segment running" style={{ flex: bucket.running }} />
                        <span className="bar-segment pending" style={{ flex: bucket.pending }} />
                        <span className="bar-segment failed" style={{ flex: bucket.failed }} />
                      </div>
                      <span className="bar-label">
                        {new Date(bucket.bucket_start).toLocaleTimeString('tr-TR', { hour: '2-digit' })}
                      </span>
                      {bucket.timeouts > 0 && (
                        <span className="bar-timeout">{bucket.timeouts} timeout</span>
                      )}
                    </div>
                  )
                })}
              </div>
            </>
          )}

          <div className="worker-status">
            <div>
              <p>Kuyruk boyutu</p>
              <strong>{workerStatus?.queue_size ?? 0}</strong>
            </div>
            <div>
              <p>İşlenen çalışma</p>
              <strong>{workerStatus?.processed_runs ?? 0}</strong>
            </div>
            <p>Durum: {runnerStatusQuery.error ? 'Yalnızca adminler görüntüleyebilir' : workerStatus?.status ?? 'bilinmiyor'}</p>
            <p>
              Son heartbeat: {workerStatus?.last_heartbeat
                ? new Date(workerStatus.last_heartbeat).toLocaleTimeString('tr-TR')
                : '—'}
            </p>
            <p className={`stream-indicator ${eventConnected ? 'connected' : 'disconnected'}`}>
              {eventConnected ? 'Gerçek zamanlı güncelleniyor' : 'Bağlantı yeniden kuruluyor...'}
            </p>
            {eventStreamError && <p className="error-text">{eventStreamError}</p>}
            <button type="button" className="ghost small" onClick={() => runnerStatusQuery.refetch()}>
              Yenile
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default AutomationsPanel
