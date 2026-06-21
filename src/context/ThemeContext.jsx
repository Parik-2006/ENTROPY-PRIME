/**
 * ThemeContext.jsx
 * ----------------
 * Global dark/light theme for Entropy Bank. The active theme is applied as a
 * `data-theme` attribute on <html> so the CSS variables in theme/tokens.css
 * switch instantly, and is persisted to localStorage('ep_theme').
 *
 * Defaults to dark (matches the framework's security-product aesthetic). The
 * attribute is also written synchronously on first import below so there is no
 * flash of the wrong theme before React mounts.
 */

import { createContext, useContext, useEffect, useState, useCallback } from 'react'

const ThemeCtx = createContext(null)
const STORAGE_KEY = 'ep_theme'

export function getInitialTheme() {
  if (typeof window === 'undefined') return 'dark'
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'dark' || stored === 'light') return stored
  return 'dark'
}

// Apply ASAP (before React mounts) to avoid a theme flash.
if (typeof document !== 'undefined') {
  document.documentElement.setAttribute('data-theme', getInitialTheme())
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(getInitialTheme)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try { localStorage.setItem(STORAGE_KEY, theme) } catch { /* ignore */ }
  }, [theme])

  const setTheme = useCallback((t) => {
    setThemeState(t === 'light' ? 'light' : 'dark')
  }, [])

  const toggleTheme = useCallback(() => {
    setThemeState(prev => (prev === 'dark' ? 'light' : 'dark'))
  }, [])

  return (
    <ThemeCtx.Provider value={{ theme, setTheme, toggleTheme, isDark: theme === 'dark' }}>
      {children}
    </ThemeCtx.Provider>
  )
}

export const useTheme = () => {
  const ctx = useContext(ThemeCtx)
  if (!ctx) return { theme: 'dark', toggleTheme: () => {}, setTheme: () => {}, isDark: true }
  return ctx
}
