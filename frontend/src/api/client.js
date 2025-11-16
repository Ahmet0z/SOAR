const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

class ApiClient {
  constructor(baseUrl = API_BASE_URL) {
    this.baseUrl = baseUrl
    this.token = this.getStoredToken()
    this.requestTimeout = 15000
    this.errorReporter = null
    this.unauthorizedHandler = null
  }

  setToken(token) {
    this.token = token
    if (typeof window !== 'undefined') {
      if (token) {
        window.localStorage.setItem('soar_token', token)
      } else {
        window.localStorage.removeItem('soar_token')
      }
    }
  }

  getStoredToken() {
    if (typeof window === 'undefined') return null
    return window.localStorage.getItem('soar_token')
  }

  setUnauthorizedHandler(handler) {
    this.unauthorizedHandler = handler
  }

  setErrorReporter(reporter) {
    this.errorReporter = reporter
  }

  setRequestTimeout(timeoutMs) {
    this.requestTimeout = timeoutMs
  }

  buildWebSocketUrl(path) {
    if (typeof window === 'undefined') {
      throw new Error('WebSocket bağlantıları yalnızca tarayıcıda kullanılabilir')
    }
    const normalizedPath = path.startsWith('/') ? path : `/${path}`
    const base = new URL(this.baseUrl, window.location.origin)
    const wsProtocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
    const trimmedPath = base.pathname.endsWith('/') ? base.pathname.slice(0, -1) : base.pathname
    let url = `${wsProtocol}//${base.host}${trimmedPath}${normalizedPath}`
    if (this.token) {
      const connector = url.includes('?') ? '&' : '?'
      url = `${url}${connector}token=${encodeURIComponent(this.token)}`
    }
    return url
  }

  openAutomationEventsSocket() {
    const url = this.buildWebSocketUrl('/ws/automation-events')
    return new WebSocket(url)
  }

  async request(path, options = {}) {
    const { responseType = 'json', timeout, ...fetchOptions } = options
    const controller = new AbortController()
    const timeoutId = setTimeout(
      () => controller.abort(),
      timeout ?? this.requestTimeout
    )
    const headers = { ...(fetchOptions.headers ?? {}) }
    if (!('Content-Type' in headers) && fetchOptions.body && !(fetchOptions.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json'
    }

    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`
    }

    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...fetchOptions,
        headers,
        signal: controller.signal
      })

      if (response.status === 401) {
        if (this.unauthorizedHandler) {
          this.unauthorizedHandler()
        }
        throw new Error('Oturumunuzun süresi doldu, lütfen tekrar giriş yapın')
      }

      if (!response.ok) {
        const message = await response.text()
        const error = new Error(message || 'API isteği başarısız oldu')
        this.reportError(error)
        throw error
      }

      if (response.status === 204) {
        return null
      }

      if (responseType === 'text') {
        return response.text()
      }

      return response.json()
    } catch (error) {
      if (error.name === 'AbortError') {
        const timeoutError = new Error('API isteği zaman aşımına uğradı')
        this.reportError(timeoutError)
        throw timeoutError
      }
      this.reportError(error)
      throw error
    } finally {
      clearTimeout(timeoutId)
    }
  }

  reportError(error) {
    if (this.errorReporter) {
      this.errorReporter(error)
    }
  }

  buildQuery(params = {}) {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return
      query.append(key, value)
    })
    const queryString = query.toString()
    return queryString ? `?${queryString}` : ''
  }

  async login(username, password) {
    const body = new URLSearchParams({
      username,
      password
    })
    const response = await fetch(`${this.baseUrl}/auth/token`, {
      method: 'POST',
      body
    })

    if (!response.ok) {
      const message = await response.text()
      throw new Error(message || 'Giriş başarısız')
    }

    const token = await response.json()
    this.setToken(token.access_token)
    return token
  }

  getIncidents() {
    return this.request('/incidents')
  }

  createIncident(data) {
    return this.request('/incidents', { method: 'POST', body: JSON.stringify(data) })
  }

  updateIncident(id, data) {
    return this.request(`/incidents/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    })
  }

  deleteIncident(id) {
    return this.request(`/incidents/${id}`, { method: 'DELETE' })
  }

  addIncidentContext(id, mutation) {
    return this.request(`/incidents/${id}/context/fields`, {
      method: 'POST',
      body: JSON.stringify(mutation)
    })
  }

  removeIncidentContext(id, fieldKey) {
    return this.request(`/incidents/${id}/context/fields/${fieldKey}`, {
      method: 'DELETE'
    })
  }

  getIndicators() {
    return this.request('/indicators')
  }

  createIndicator(data) {
    return this.request('/indicators', { method: 'POST', body: JSON.stringify(data) })
  }

  updateIndicator(id, data) {
    return this.request(`/indicators/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    })
  }

  deleteIndicator(id) {
    return this.request(`/indicators/${id}`, { method: 'DELETE' })
  }

  addIndicatorContext(id, mutation) {
    return this.request(`/indicators/${id}/context/fields`, {
      method: 'POST',
      body: JSON.stringify(mutation)
    })
  }

  removeIndicatorContext(id, fieldKey) {
    return this.request(`/indicators/${id}/context/fields/${fieldKey}`, {
      method: 'DELETE'
    })
  }

  getAutomations() {
    return this.request('/automations')
  }

  createAutomation(data) {
    return this.request('/automations', { method: 'POST', body: JSON.stringify(data) })
  }

  updateAutomation(id, data) {
    return this.request(`/automations/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    })
  }

  deleteAutomation(id) {
    return this.request(`/automations/${id}`, { method: 'DELETE' })
  }

  queueAutomationRun(id, payload) {
    return this.request(`/automations/${id}/runs`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  getAutomationRuns(id) {
    return this.request(`/automations/${id}/runs`)
  }

  getAutomationRun(runId) {
    return this.request(`/automation-runs/${runId}`)
  }

  getAutomationRunEvents(runId) {
    return this.request(`/automation-runs/${runId}/events`)
  }

  getAutomationRunMetrics(params = {}) {
    return this.request(`/automation-runs/metrics${this.buildQuery(params)}`)
  }

  getAutomationRunnerStatus() {
    return this.request('/automation-runner/status')
  }

  requeueAutomationRun(runId) {
    return this.request(`/automation-runs/${runId}/requeue`, { method: 'POST' })
  }

  getPlaybooks() {
    return this.request('/playbooks')
  }

  createPlaybook(data) {
    return this.request('/playbooks', { method: 'POST', body: JSON.stringify(data) })
  }

  updatePlaybook(id, data) {
    return this.request(`/playbooks/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    })
  }

  deletePlaybook(id) {
    return this.request(`/playbooks/${id}`, { method: 'DELETE' })
  }

  validatePlaybook(id) {
    return this.request(`/playbooks/${id}/validate`, { method: 'POST' })
  }

  runPlaybook(id, payload) {
    return this.request(`/playbooks/${id}/run`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  getContextSchema(entityType) {
    return this.request(`/context-schemas/${entityType}`)
  }

  upsertContextSchema(entityType, payload) {
    return this.request(`/context-schemas/${entityType}`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  deleteContextSchemaField(entityType, fieldKey) {
    return this.request(`/context-schemas/${entityType}/${fieldKey}`, {
      method: 'DELETE'
    })
  }

  getContextFieldHistory(entityType, fieldKey) {
    return this.request(`/context-schemas/${entityType}/${fieldKey}/history`)
  }

  getAuditLogs(params = {}) {
    return this.request(`/audit-logs${this.buildQuery(params)}`)
  }

  exportAuditLogs(params = {}) {
    return this.request(`/audit-logs/export${this.buildQuery(params)}`, {
      responseType: 'text'
    })
  }

  getOrganizations() {
    return this.request('/organizations')
  }

  createOrganization(payload) {
    return this.request('/organizations', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  getOrganizationMembers(slug) {
    return this.request(`/organizations/${slug}/members`)
  }

  addOrganizationMember(slug, payload) {
    return this.request(`/organizations/${slug}/members`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  inviteOrganizationMember(slug, payload) {
    return this.request(`/organizations/${slug}/invites`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  acceptInvite(token) {
    return this.request(`/organization-invites/${token}/accept`, { method: 'POST' })
  }

  getPublicInvite(token) {
    return this.request(`/public/invites/${token}`)
  }

  acceptPublicInvite(token, payload) {
    return this.request(`/public/invites/${token}/accept`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  getMemberships() {
    return this.request('/me/memberships')
  }

  switchTenant(tenantId) {
    return this.request('/me/tenant', {
      method: 'POST',
      body: JSON.stringify({ tenant_id: tenantId })
    })
  }
}

export const apiClient = new ApiClient()
