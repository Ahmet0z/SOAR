import { useEffect, useMemo, useState } from 'react'
import IncidentsPanel from './components/IncidentsPanel'
import IndicatorsPanel from './components/IndicatorsPanel'
import AutomationsPanel from './components/AutomationsPanel'
import PlaybooksPanel from './components/PlaybooksPanel'
import LoginForm from './components/LoginForm'
import InviteAcceptance from './components/InviteAcceptance'
import AuditLogsPanel from './components/AuditLogsPanel'
import OrganizationsPanel from './components/OrganizationsPanel'
import ErrorBoundary from './components/ErrorBoundary'
import { apiClient } from './api/client'
import './App.css'

const TABS = [
  { id: 'incidents', label: 'Incidents', component: IncidentsPanel },
  { id: 'indicators', label: 'Indicators', component: IndicatorsPanel },
  { id: 'automations', label: 'Automations', component: AutomationsPanel },
  { id: 'playbooks', label: 'Playbooks', component: PlaybooksPanel },
  { id: 'audit-logs', label: 'Audit Logs', component: AuditLogsPanel },
  { id: 'organizations', label: 'Organizations', component: OrganizationsPanel }
]

function App() {
  const [activeTab, setActiveTab] = useState(TABS[0].id)
  const [token, setToken] = useState(() => apiClient.getStoredToken())
  const readInviteFromLocation = () => {
    if (typeof window === 'undefined') return null
    const params = new URLSearchParams(window.location.search)
    return params.get('invite')
  }
  const [inviteToken, setInviteToken] = useState(readInviteFromLocation)

  useEffect(() => {
    apiClient.setUnauthorizedHandler(() => {
      setToken(null)
    })
    apiClient.setErrorReporter((error) => {
      console.error('[API]', error)
    })
    if (typeof window !== 'undefined') {
      const handler = () => {
        setInviteToken(readInviteFromLocation())
      }
      window.addEventListener('popstate', handler)
      return () => window.removeEventListener('popstate', handler)
    }
    return undefined
  }, [])

  useEffect(() => {
    apiClient.setToken(token)
  }, [token])

  const ActiveComponent = useMemo(
    () => TABS.find((tab) => tab.id === activeTab)?.component ?? IncidentsPanel,
    [activeTab]
  )

  const clearInviteToken = () => {
    setInviteToken(null)
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href)
      url.searchParams.delete('invite')
      window.history.replaceState({}, '', url)
    }
  }

  const handleLogout = () => {
    setToken(null)
  }

  const handleLoginSuccess = (accessToken) => {
    setToken(accessToken)
  }

  if (!token && inviteToken) {
    return (
      <div className="auth-shell">
        <InviteAcceptance token={inviteToken} onComplete={clearInviteToken} />
      </div>
    )
  }

  if (!token) {
    return (
      <div className="auth-shell">
        <LoginForm onSuccess={handleLoginSuccess} />
      </div>
    )
  }

  return (
    <div className="app-shell">
      <header>
        <div>
          <p className="eyebrow">SOAR Platformu</p>
          <h1>Güvenlik Operasyon Kontrol Paneli</h1>
          <p className="subtitle">
            Incidents, indicators, automations ve playbook süreçlerini tek noktadan yönetin.
          </p>
        </div>
        <button type="button" className="ghost" onClick={handleLogout}>
          Çıkış Yap
        </button>
      </header>

      <nav className="tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={tab.id === activeTab ? 'active' : ''}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <main>
        <ErrorBoundary>
          <ActiveComponent />
        </ErrorBoundary>
      </main>
    </div>
  )
}

export default App
