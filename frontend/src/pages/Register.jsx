import { Lock, Mail, User } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AuthShell from '../components/AuthShell'
import { Alert, Button, field } from '../components/ui'
import { useAuth } from '../hooks/useAuth'
import { errorMessage } from '../services/api'

const strength = (p) => [p.length >= 8, /[A-Za-z]/.test(p) && /\d/.test(p), p.length >= 12].filter(Boolean).length

export default function Register() {
  const { register } = useAuth()
  const nav = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const score = strength(form.password)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try { await register(form); nav('/app/new') } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  const input = (Icon, props) => (
    <span className="relative block"><Icon className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><input className={`${field} pl-10`} required {...props} /></span>
  )

  return (
    <AuthShell title="Create your account" subtitle="It takes less than a minute."
      footer={<>Already have an account? <Link className="font-semibold text-brand-600 hover:underline" to="/login">Log in</Link></>}>
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert tone="error">{error}</Alert>}
        <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">Name</span>{input(User, { placeholder: 'Your name', autoComplete: 'name', value: form.name, onChange: set('name') })}</label>
        <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">Email</span>{input(Mail, { type: 'email', placeholder: 'you@example.com', autoComplete: 'email', value: form.email, onChange: set('email') })}</label>
        <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">Password</span>
          {input(Lock, { type: 'password', placeholder: 'At least 8 characters', minLength: 8, autoComplete: 'new-password', value: form.password, onChange: set('password') })}
          {form.password && (
            <span className="mt-2 flex items-center gap-1.5" aria-hidden="true">
              {[1, 2, 3].map((i) => <span key={i} className={`h-1.5 flex-1 rounded-full transition-colors ${i <= score ? ['', 'bg-rose-400', 'bg-amber-400', 'bg-emerald-500'][score] : 'bg-slate-200'}`} />)}
              <span className="ml-1 text-xs text-slate-500">{['', 'Weak', 'Okay', 'Strong'][score]}</span>
            </span>)}
        </label>
        <Button className="w-full" size="lg" loading={busy}>{busy ? 'Creating account…' : 'Create account'}</Button>
      </form>
    </AuthShell>
  )
}
