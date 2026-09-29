import { Lock, Mail } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import AuthShell from '../components/AuthShell'
import { Alert, Button, field } from '../components/ui'
import { useAuth } from '../hooks/useAuth'
import { errorMessage } from '../services/api'

export default function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [params] = useSearchParams()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try { await login(form); nav('/app') } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  return (
    <AuthShell title="Welcome back" subtitle="Log in to continue learning."
      footer={<>New here? <Link className="font-semibold text-brand-600 hover:underline" to="/register">Create an account</Link></>}>
      <form onSubmit={submit} className="space-y-4">
        {params.get('expired') && <Alert tone="info">Your session ended. Please log in again.</Alert>}
        {error && <Alert tone="error">{error}</Alert>}
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-slate-700">Email</span>
          <span className="relative block"><Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className={`${field} pl-10`} type="email" autoComplete="email" placeholder="you@example.com" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></span>
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-slate-700">Password</span>
          <span className="relative block"><Lock className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className={`${field} pl-10`} type="password" autoComplete="current-password" placeholder="Your password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></span>
        </label>
        <Button className="w-full" size="lg" loading={busy}>{busy ? 'Signing in…' : 'Log in'}</Button>
      </form>
    </AuthShell>
  )
}
