import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'

function AuditLogsPanel() {
  const [draftFilters, setDraftFilters] = useState({ action: '', entity_type: '', start: '', end: '' })
  const [appliedFilters, setAppliedFilters] = useState({})
  const [exporting, setExporting] = useState(false)
  const [exportMessage, setExportMessage] = useState('')

  const queryKey = useMemo(() => ['audit-logs', JSON.stringify(appliedFilters)], [appliedFilters])

  const logsQuery = useQuery({
    queryKey,
    queryFn: () => apiClient.getAuditLogs(appliedFilters),
    refetchInterval: 10000
  })

  const logs = logsQuery.data ?? []

  const handleFilterSubmit = (event) => {
    event.preventDefault()
    const sanitized = Object.fromEntries(
      Object.entries(draftFilters).filter(([, value]) => value !== '' && value !== null && value !== undefined)
    )
    setAppliedFilters(sanitized)
  }

  const handleResetFilters = () => {
    setDraftFilters({ action: '', entity_type: '', start: '', end: '' })
    setAppliedFilters({})
  }

  const handleExport = async () => {
    try {
      setExporting(true)
      setExportMessage('')
      const csv = await apiClient.exportAuditLogs(appliedFilters)
      const blob = new Blob([csv], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `audit-logs-${Date.now()}.csv`
      anchor.click()
      URL.revokeObjectURL(url)
      setExportMessage('CSV dışa aktarma hazırlandı')
    } catch (error) {
      setExportMessage(error.message)
    } finally {
      setExporting(false)
    }
  }

  const activeFilters = Object.keys(appliedFilters)

  return (
    <div className="panel-card">
      <div className="panel-header">
        <h2>Son Denetim Kayıtları</h2>
        {logsQuery.isRefetching && <span className="tag neutral">Güncelleniyor</span>}
      </div>
      <form className="filter-grid" onSubmit={handleFilterSubmit}>
        <label>
          Aksiyon
          <input
            value={draftFilters.action}
            onChange={(event) => setDraftFilters((prev) => ({ ...prev, action: event.target.value }))}
            placeholder="ör. automation.run.queued"
          />
        </label>
        <label>
          Varlık Tipi
          <input
            value={draftFilters.entity_type}
            onChange={(event) => setDraftFilters((prev) => ({ ...prev, entity_type: event.target.value }))}
            placeholder="incident / automation"
          />
        </label>
        <label>
          Başlangıç Tarihi
          <input
            type="date"
            value={draftFilters.start}
            onChange={(event) => setDraftFilters((prev) => ({ ...prev, start: event.target.value }))}
          />
        </label>
        <label>
          Bitiş Tarihi
          <input
            type="date"
            value={draftFilters.end}
            onChange={(event) => setDraftFilters((prev) => ({ ...prev, end: event.target.value }))}
          />
        </label>
        <div className="filter-actions">
          <button type="button" className="ghost" onClick={handleResetFilters}>
            Temizle
          </button>
          <button type="submit">Filtrele</button>
        </div>
      </form>
      <div className="filter-meta">
        <span>{logs.length} kayıt</span>
        {activeFilters.length > 0 && <span className="tag">{activeFilters.length} aktif filtre</span>}
        <button type="button" className="ghost" onClick={handleExport} disabled={exporting}>
          {exporting ? 'Hazırlanıyor...' : 'CSV olarak indir'}
        </button>
      </div>
      {exportMessage && <p className="helper">{exportMessage}</p>}
      {logsQuery.isLoading ? (
        <p>Yükleniyor...</p>
      ) : logsQuery.error ? (
        <p className="error-text">{logsQuery.error.message}</p>
      ) : (
        <ul className="log-list">
          {logs.map((entry) => (
            <li key={entry.id}>
              <div>
                <strong>{entry.action}</strong>
                <span>{entry.entity_type}</span>
              </div>
              <div>
                <span>{new Date(entry.created_at).toLocaleString()}</span>
                {entry.entity_id && <span className="tag">{entry.entity_id}</span>}
              </div>
              {!!Object.keys(entry.payload || {}).length && (
                <pre>{JSON.stringify(entry.payload, null, 2)}</pre>
              )}
            </li>
          ))}
          {!logs.length && <li>Henüz log bulunamadı.</li>}
        </ul>
      )}
    </div>
  )
}

export default AuditLogsPanel
