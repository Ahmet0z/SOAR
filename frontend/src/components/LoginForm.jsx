import { useState } from 'react'
import PropTypes from 'prop-types'
import { apiClient } from '../api/client'

function LoginForm({ onSuccess }) {
  const [credentials, setCredentials] = useState({ username: 'admin', password: 'admin123' })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handleChange = (event) => {
    const { name, value } = event.target
    setCredentials((prev) => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const token = await apiClient.login(credentials.username, credentials.password)
      onSuccess(token.access_token)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="login-form" onSubmit={handleSubmit}>
      <h1>SOAR Platformu</h1>
      <p className="subtitle">Devam etmek için hesabınıza giriş yapın.</p>
      {error && <p className="error-text">{error}</p>}
      <label>
        Kullanıcı Adı
        <input
          name="username"
          value={credentials.username}
          onChange={handleChange}
          autoComplete="username"
        />
      </label>
      <label>
        Parola
        <input
          type="password"
          name="password"
          value={credentials.password}
          onChange={handleChange}
          autoComplete="current-password"
        />
      </label>
      <button type="submit" disabled={submitting}>
        {submitting ? 'Giriş yapılıyor...' : 'Giriş Yap'}
      </button>
      <p className="helper">Demo hesabı: admin / admin123</p>
    </form>
  )
}

LoginForm.propTypes = {
  onSuccess: PropTypes.func.isRequired
}

export default LoginForm
