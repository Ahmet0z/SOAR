import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'

function OrganizationsPanel() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({ slug: '', name: '' })
  const [memberForm, setMemberForm] = useState({ username: '', role: 'analyst' })
  const [inviteForm, setInviteForm] = useState({ email: '', role: 'analyst' })
  const [message, setMessage] = useState('')
  const [selectedSlug, setSelectedSlug] = useState('')
  const [switchMessage, setSwitchMessage] = useState('')

  const organizationsQuery = useQuery({
    queryKey: ['organizations'],
    queryFn: () => apiClient.getOrganizations(),
    retry: false
  })

  const membershipsQuery = useQuery({
    queryKey: ['memberships'],
    queryFn: () => apiClient.getMemberships()
  })

  const membersQuery = useQuery({
    queryKey: ['organization-members', selectedSlug],
    queryFn: () => apiClient.getOrganizationMembers(selectedSlug),
    enabled: Boolean(selectedSlug)
  })

  useEffect(() => {
    if (!selectedSlug && organizationsQuery.data?.length) {
      setSelectedSlug(organizationsQuery.data[0].slug)
    }
  }, [organizationsQuery.data, selectedSlug])

  const createMutation = useMutation({
    mutationFn: (payload) => apiClient.createOrganization(payload),
    onSuccess: () => {
      setMessage('Organizasyon oluşturuldu')
      setForm({ slug: '', name: '' })
      queryClient.invalidateQueries({ queryKey: ['organizations'] })
    },
    onError: (error) => setMessage(error.message)
  })

  const addMemberMutation = useMutation({
    mutationFn: (payload) => apiClient.addOrganizationMember(selectedSlug, payload),
    onSuccess: () => {
      setMemberForm({ username: '', role: 'analyst' })
      queryClient.invalidateQueries({ queryKey: ['organization-members', selectedSlug] })
    }
  })

  const inviteMemberMutation = useMutation({
    mutationFn: (payload) => apiClient.inviteOrganizationMember(selectedSlug, payload),
    onSuccess: () => {
      setInviteForm({ email: '', role: 'analyst' })
      queryClient.invalidateQueries({ queryKey: ['organization-members', selectedSlug] })
    }
  })

  const switchTenantMutation = useMutation({
    mutationFn: (tenantId) => apiClient.switchTenant(tenantId),
    onSuccess: (_, tenantId) => {
      setSwitchMessage(`${tenantId} tenant'ına geçildi`)
      queryClient.invalidateQueries()
    },
    onError: (error) => setSwitchMessage(error.message)
  })

  const handleSubmit = (event) => {
    event.preventDefault()
    setMessage('')
    createMutation.mutate(form)
  }

  const organizations = organizationsQuery.data ?? []
  const memberships = membershipsQuery.data ?? []
  const orgMembers = membersQuery.data ?? []

  return (
    <div className="panel-grid">
      <div className="panel-column">
        <div className="panel-card">
          <h2>Organizasyon Oluştur</h2>
          <form onSubmit={handleSubmit}>
            <label>
              Kısa Ad (slug)
              <input value={form.slug} onChange={(e) => setForm((prev) => ({ ...prev, slug: e.target.value }))} />
            </label>
            <label>
              İsim
              <input value={form.name} onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))} />
            </label>
            <button type="submit" disabled={createMutation.isLoading}>
              {createMutation.isLoading ? 'Kaydediliyor...' : 'Kaydet'}
            </button>
            {message && <p className="helper">{message}</p>}
          </form>
        </div>

        <div className="panel-card">
          <h2>Üyeliklerim</h2>
          {membershipsQuery.isLoading ? (
            <p>Yükleniyor...</p>
          ) : membershipsQuery.error ? (
            <p className="error-text">{membershipsQuery.error.message}</p>
          ) : (
            <ul className="org-list">
              {memberships.map((membership) => (
                <li key={membership.id}>
                  <div>
                    <strong>{membership.organization.name}</strong>
                    <span>{membership.role}</span>
                  </div>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => switchTenantMutation.mutate(membership.tenant_slug)}
                  >
                    Bu tenant'a geç
                  </button>
                </li>
              ))}
              {!memberships.length && <li>Henüz üyelik yok.</li>}
            </ul>
          )}
          {switchMessage && <p className="helper">{switchMessage}</p>}
        </div>
      </div>

      <div className="panel-column">
        <div className="panel-card">
          <div className="panel-header">
            <h2>Organizasyon Üyeleri</h2>
            <select
              value={selectedSlug}
              onChange={(event) => setSelectedSlug(event.target.value)}
              disabled={!organizations.length}
            >
              {organizations.map((org) => (
                <option key={org.id} value={org.slug}>
                  {org.name}
                </option>
              ))}
            </select>
          </div>
          {membersQuery.isLoading ? (
            <p>Üyeler yükleniyor...</p>
          ) : membersQuery.error ? (
            <p className="error-text">{membersQuery.error.message}</p>
          ) : (
            <ul className="org-list">
              {orgMembers.map((member) => (
                <li key={member.id}>
                  <div>
                    <strong>{member.user?.username ?? member.email ?? 'Bekleyen davet'}</strong>
                    <span>
                      {member.role} • {member.status}
                    </span>
                    {member.status === 'invited' && member.invite_expires_at && (
                      <span className="tag warning">
                        Bitiş: {new Date(member.invite_expires_at).toLocaleDateString('tr-TR')}
                      </span>
                    )}
                    {member.invite_accepted_at && (
                      <span className="tag neutral">
                        Kabul: {new Date(member.invite_accepted_at).toLocaleDateString('tr-TR')}
                      </span>
                    )}
                  </div>
                  {member.status === 'invited' && member.invite_token && (
                    <span className="tag neutral">Token: {member.invite_token}</span>
                  )}
                </li>
              ))}
              {!orgMembers.length && <li>Henüz üye yok.</li>}
            </ul>
          )}

          <section className="org-actions">
            <h3>Mevcut Kullanıcı Ekle</h3>
            <form
              onSubmit={(event) => {
                event.preventDefault()
                if (!selectedSlug) return
                addMemberMutation.mutate(memberForm)
              }}
            >
              <label>
                Kullanıcı Adı
                <input
                  value={memberForm.username}
                  onChange={(event) => setMemberForm((prev) => ({ ...prev, username: event.target.value }))}
                />
              </label>
              <label>
                Rol
                <select
                  value={memberForm.role}
                  onChange={(event) => setMemberForm((prev) => ({ ...prev, role: event.target.value }))}
                >
                  <option value="analyst">Analyst</option>
                  <option value="admin">Admin</option>
                </select>
              </label>
              <button type="submit" disabled={addMemberMutation.isLoading}>
                {addMemberMutation.isLoading ? 'Ekleniyor...' : 'Üye Ekle'}
              </button>
            </form>
          </section>

          <section className="org-actions">
            <h3>Davetiye Oluştur</h3>
            <form
              onSubmit={(event) => {
                event.preventDefault()
                if (!selectedSlug) return
                inviteMemberMutation.mutate(inviteForm)
              }}
            >
              <label>
                E-posta
                <input
                  type="email"
                  value={inviteForm.email}
                  onChange={(event) => setInviteForm((prev) => ({ ...prev, email: event.target.value }))}
                />
              </label>
              <label>
                Rol
                <select
                  value={inviteForm.role}
                  onChange={(event) => setInviteForm((prev) => ({ ...prev, role: event.target.value }))}
                >
                  <option value="analyst">Analyst</option>
                  <option value="admin">Admin</option>
                </select>
              </label>
              <button type="submit" disabled={inviteMemberMutation.isLoading}>
                {inviteMemberMutation.isLoading ? 'Gönderiliyor...' : 'Davetiye Oluştur'}
              </button>
            </form>
          </section>
        </div>
      </div>
    </div>
  )
}

export default OrganizationsPanel
