import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'

function formatNumber(value) {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 }).format(value)
}

function AutomationAnalyticsPanel() {
  const [windowHours, setWindowHours] = useState('168')
  const [limit, setLimit] = useState('10')

  const analyticsQuery = useQuery({
    queryKey: ['automation-run-analytics', windowHours, limit],
    queryFn: () =>
      apiClient.getAutomationRunAnalytics({
        window_hours: Number(windowHours),
        limit: Number(limit)
      })
  })

  const analytics = analyticsQuery.data

  const failureRate = useMemo(() => {
    if (!analytics || analytics.total_runs === 0) return 0
    return (analytics.total_failures / analytics.total_runs) * 100
  }, [analytics])

  return (
    <section className="panel analytics-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Automation Analytics</p>
          <h2>Çapraz Koşum Trendleri</h2>
          <p className="subtitle">
            Kuyruklanan otomasyonlar arasında hangi akışların başarısız olduğunu, ortalama süreleri ve
            yeniden deneme davranışlarını inceleyin.
          </p>
        </div>
        <div className="filters">
          <label>
            Zaman Aralığı (saat)
            <input
              type="number"
              min={1}
              max={720}
              value={windowHours}
              onChange={(event) => setWindowHours(event.target.value)}
            />
          </label>
          <label>
            Gösterilecek Otomasyon
            <input
              type="number"
              min={1}
              max={50}
              value={limit}
              onChange={(event) => setLimit(event.target.value)}
            />
          </label>
        </div>
      </div>

      {analyticsQuery.isLoading ? (
        <div className="empty-state">Analitikler yükleniyor...</div>
      ) : analyticsQuery.isError ? (
        <div className="empty-state error">Analitik verileri çekilirken hata oluştu.</div>
      ) : (
        <>
          <div className="stat-grid">
            <article className="stat-card">
              <p className="label">Toplam Çalışma</p>
              <p className="value">{formatNumber(analytics.total_runs)}</p>
            </article>
            <article className="stat-card">
              <p className="label">Başarısızlık Oranı</p>
              <p className="value">{formatNumber(failureRate)}%</p>
            </article>
            <article className="stat-card">
              <p className="label">Zaman Aşımı</p>
              <p className="value">{formatNumber(analytics.total_timeouts)}</p>
            </article>
          </div>

          <div className="timeline">
            <div>
              <p className="eyebrow">Kapsam</p>
              <p>
                {new Date(analytics.from_ts).toLocaleString('tr-TR')} -{' '}
                {new Date(analytics.to_ts).toLocaleString('tr-TR')}
              </p>
            </div>
            <p className="muted">
              Otomasyonlar başarısız koşu sayısına göre sıralandı. Yeniden deneme süreleri ortalama milisaniye
              olarak hesaplanır.
            </p>
          </div>

          <div className="table-wrapper">
            <table className="analytics-table">
              <thead>
                <tr>
                  <th>Automation</th>
                  <th>Çalışma</th>
                  <th>Başarısız</th>
                  <th>Zaman Aşımı</th>
                  <th>Yeniden Deneme</th>
                  <th>Ort. Süre (ms)</th>
                  <th>Yeniden Deneme Aralığı (ms)</th>
                  <th>Son Çalışma</th>
                </tr>
              </thead>
              <tbody>
                {analytics.automations.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="empty-row">
                      Bu aralıkta koşu bulunamadı.
                    </td>
                  </tr>
                ) : (
                  analytics.automations.map((automation) => (
                    <tr key={automation.automation_id}>
                      <td>
                        <strong>{automation.automation_name}</strong>
                        <span className="muted">#{automation.automation_id.slice(0, 8)}</span>
                      </td>
                      <td>{formatNumber(automation.run_count)}</td>
                      <td>{formatNumber(automation.failure_count)}</td>
                      <td>{formatNumber(automation.timeout_count)}</td>
                      <td>{formatNumber(automation.retry_count)}</td>
                      <td>{formatNumber(automation.avg_duration_ms)}</td>
                      <td>{formatNumber(automation.mean_time_between_retries_ms)}</td>
                      <td>
                        {automation.last_run_at
                          ? new Date(automation.last_run_at).toLocaleString('tr-TR')
                          : '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}

export default AutomationAnalyticsPanel
