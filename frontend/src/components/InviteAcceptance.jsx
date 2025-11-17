import { useEffect, useState } from 'react'
import PropTypes from 'prop-types'
import { apiClient } from '../api/client'

function InviteAcceptance({ token, onComplete }) {
  const [invite, setInvite] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ username: '', password: '', full_name: '' })
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    apiClient
      .getPublicInvite(token)
      .then((data) => {
        if (!cancelled) {
          setInvite(data)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [token])

  const handleChange = (event) => {
    const { name, value } = event.target
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    try {
      await apiClient.acceptPublicInvite(token, form)
      setSuccess(true)
    } catch (err) {
      setError(err.message)
    }
  }

  const closeInvite = () => {
    if (onComplete) {
      onComplete()
    }
  }

  if (loading) {
    return (
      <div className="invite-card">
        <h1>Davet doğrulanıyor...</h1>
      </div>
    )
  }

  if (error) {
    return (
      <div className="invite-card">
        <h1>Davet bulunamadı</h1>
        <p className="error-text">{error}</p>
        <button type="button" onClick={closeInvite}>
          Giriş ekranına dön
        </button>
      </div>
    )
  }

  if (!invite) {
    return null
  }

  if (success) {
    return (
      <div className="invite-card">
        <h1>Davetiye kabul edildi</h1>
        <p className="subtitle">Yeni hesabınızla giriş yapabilirsiniz.</p>
        <button type="button" onClick={closeInvite}>
          Giriş ekranına dön
        </button>
      </div>
    )
  }

  return (
    <div className="invite-card">
      <p className="eyebrow">{invite.organization.name}</p>
      <h1>Organizasyona katıl</h1>
      <p className="subtitle">
        {invite.email ? `${invite.email} adresi için` : 'Bu davet için'} erişim sağlanmıştır. Davet {invite.expires_at ? new Date(invite.expires_at).toLocaleString('tr-TR') : 'belirtilen'} tarihine kadar geçerlidir.
      </p>
      {invite.expired && <p className="error-text">Davetin süresi dolmuş.</p>}
      {!invite.expired && (
        <form className="invite-form" onSubmit={handleSubmit}>
          <label>
            Kullanıcı Adı
            <input name="username" value={form.username} onChange={handleChange} required />
          </label>
          <label>
            Ad Soyad
            <input name="full_name" value={form.full_name} onChange={handleChange} />
          </label>
          <label>
            Parola
            <input
              name="password"
              type="password"
              value={form.password}
              onChange={handleChange}
              required
              minLength={6}
            />
          </label>
          {error && <p className="error-text">{error}</p>}
          <button type="submit">Daveti kabul et</button>
        </form>
      )}
      <button type="button" className="ghost" onClick={closeInvite}>
        Giriş ekranına dön
      </button>
    </div>
  )
}

InviteAcceptance.propTypes = {
  token: PropTypes.string.isRequired,
  onComplete: PropTypes.func
}

InviteAcceptance.defaultProps = {
  onComplete: null
}

export default InviteAcceptance
