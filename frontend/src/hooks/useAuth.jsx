import { createContext, useContext, useEffect, useState } from 'react'
import { authApi, tokenStore } from '../services/api'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(!!tokenStore.get())

  useEffect(() => {
    if (!tokenStore.get()) return
    authApi.me().then(setUser).catch(() => tokenStore.clear()).finally(() => setLoading(false))
  }, [])

  const accept = (res) => {
    tokenStore.set(res.access_token)
    setUser(res.user)
  }

  const value = {
    user,
    loading,
    login: async (b) => accept(await authApi.login(b)),
    register: async (b) => accept(await authApi.register(b)),
    logout: async () => {
      try { await authApi.logout() } catch { /* session may already be gone */ }
      tokenStore.clear()
      setUser(null)
    },
  }
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}

export const useAuth = () => useContext(AuthCtx)
