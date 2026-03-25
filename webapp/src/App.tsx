import { useState, useEffect, useCallback } from 'react'
import {
  translateText,
  imageToText,
  getDefaultLanguages,
  healthCheck,
  checkGrammar,
  lookupWord,
  listTranslations,
  getTranslation,
  updateTranslation,
  deleteTranslation,
  saveNote,
  type TranslateResponse,
  type TranslationSummary,
  type LanguageToolResponse,
  type DictionaryEntry,
} from './api/services'
import {
  login as apiLogin,
  signup as apiSignup,
  verifyAuth,
  logout as apiLogout,
  type AuthUser,
} from './api/services'
import './App.css'
import { getErrorMessage } from './utils/errorHandler'

const LANGS: Record<string, string> = {
  es: 'Spanish',
  fr: 'French',
  de: 'German',
  it: 'Italian',
  pt: 'Portuguese',
  ar: 'Arabic',
  zh: 'Chinese',
  hi: 'Hindi',
  ja: 'Japanese',
  ko: 'Korean',
  nl: 'Dutch',
  pl: 'Polish',
  ru: 'Russian',
  tr: 'Turkish',
}

const SAMPLE_TEXTS = [
  'Hello world',
  'Good morning',
  'Thank you very much',
  'How are you today?',
  'Welcome to our application',
]

const DEFAULT_TARGETS = ['es', 'fr', 'de', 'it', 'pt']

// Email shape check
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

// Signup: must include one of these
const PASSWORD_SPECIAL_REGEX = /[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?]/

type PageId = 'translate' | 'dictionary'

export default function App() {
  const [page, setPage] = useState<PageId>('translate')
  const [step, setStep] = useState<'upload' | 'text' | 'translated'>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [extractedText, setExtractedText] = useState('')
  const [translation, setTranslation] = useState<TranslateResponse | null>(null)
  const [targetLangs, setTargetLangs] = useState<string[]>(DEFAULT_TARGETS)
  const [sourceLang, setSourceLang] = useState('en')
  const [translateAllLangs, setTranslateAllLangs] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [apiStatus, setApiStatus] = useState<string>('')
  const [darkMode, setDarkMode] = useState(false)
  const [showRaw, setShowRaw] = useState(false)
  const [copiedLang, setCopiedLang] = useState<string | null>(null)
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches
  )
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches
  )

  const [grammarResult, setGrammarResult] = useState<LanguageToolResponse | null>(null)
  const [grammarLoading, setGrammarLoading] = useState(false)
  const [dictWord, setDictWord] = useState('')
  const [dictResult, setDictResult] = useState<DictionaryEntry[] | null>(null)
  const [dictLoading, setDictLoading] = useState(false)
  const [savedList, setSavedList] = useState<TranslationSummary[]>([])
  const [savedListLoading, setSavedListLoading] = useState(false)
  const [user, setUser] = useState<AuthUser | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [authError, setAuthError] = useState<string | null>(null)
  const [authTab, setAuthTab] = useState<'login' | 'signup'>('login')
  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [signupEmail, setSignupEmail] = useState('')
  const [signupPassword, setSignupPassword] = useState('')
  const [signupName, setSignupName] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [authSubmitting, setAuthSubmitting] = useState(false)
  const [authFieldErrors, setAuthFieldErrors] = useState<{ email?: string; password?: string; name?: string }>({})

  const validateEmail = (email: string): string | null => {
    const trimmed = email.trim()
    if (!trimmed) return 'Email is required'
    if (trimmed.length > 254) return 'Email is too long'
    if (!EMAIL_REGEX.test(trimmed)) return 'Please enter a valid email address'
    return null
  }
  const validatePasswordLogin = (password: string): string | null => {
    if (!password) return 'Password is required'
    return null
  }
  const validatePasswordSignup = (password: string): string | null => {
    if (!password) return 'Password is required'
    if (password.length < 6) return 'Password must be at least 6 characters'
    if (!/[A-Z]/.test(password)) return 'Password must contain at least one capital letter'
    if (!/[0-9]/.test(password)) return 'Password must contain at least one number'
    if (!PASSWORD_SPECIAL_REGEX.test(password)) return 'Password must contain at least one special character'
    return null
  }
  const validateName = (name: string): string | null => {
    if (!name.trim()) return 'Name is required'
    return null
  }

  useEffect(() => {
    verifyAuth().then((u) => {
      setUser(u)
      setAuthLoading(false)
    }).catch(() => setAuthLoading(false))
  }, [])

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)')
    const sync = () => {
      const mobile = mq.matches
      setIsMobile(mobile)
      if (mobile) setSidebarCollapsed(true)
      else setSidebarCollapsed(false)
    }
    sync()
    mq.addEventListener('change', sync)
    return () => mq.removeEventListener('change', sync)
  }, [])

  const closeMobileSidebar = useCallback(() => {
    if (isMobile) setSidebarCollapsed(true)
  }, [isMobile])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setAuthError(null)
    setAuthFieldErrors({})
    const emailErr = validateEmail(loginEmail)
    const passwordErr = validatePasswordLogin(loginPassword)
    if (emailErr || passwordErr) {
      setAuthFieldErrors({
        email: emailErr || undefined,
        password: passwordErr || undefined,
      })
      return
    }
    setAuthSubmitting(true)
    try {
      const { user: u } = await apiLogin(loginEmail.trim().toLowerCase(), loginPassword)
      setUser(u)
      setLoginEmail('')
      setLoginPassword('')
    } catch (err) {
      const raw = err instanceof Error ? err.message : ''
      const msg = getErrorMessage(err)
      const isInvalidCredentials =
        /invalid (email|username) or password/i.test(raw) ||
        /invalid credentials/i.test(raw) ||
        (raw.toLowerCase().includes('invalid') && raw.toLowerCase().includes('password'))
      if (isInvalidCredentials) {
        setAuthTab('signup')
        setSignupEmail(loginEmail.trim().toLowerCase())
        setSignupPassword('')
        setSignupName('')
        setAuthError('No account found with this email. Please sign up to create an account.')
      } else {
        setAuthError(msg)
      }
    } finally {
      setAuthSubmitting(false)
    }
  }

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault()
    setAuthError(null)
    setAuthFieldErrors({})
    const emailErr = validateEmail(signupEmail)
    const passwordErr = validatePasswordSignup(signupPassword)
    const nameErr = validateName(signupName)
    if (emailErr || passwordErr || nameErr) {
      setAuthFieldErrors({
        email: emailErr || undefined,
        password: passwordErr || undefined,
        name: nameErr || undefined,
      })
      return
    }
    setAuthSubmitting(true)
    try {
      await apiSignup(signupEmail.trim().toLowerCase(), signupName.trim(), signupPassword)
      const { user: u } = await apiLogin(signupEmail.trim().toLowerCase(), signupPassword)
      setUser(u)
      setSignupEmail('')
      setSignupPassword('')
      setSignupName('')
      setLoginEmail('')
      setLoginPassword('')
    } catch (err) {
      setAuthError(getErrorMessage(err))
    } finally {
      setAuthSubmitting(false)
    }
  }

  const handleLogout = () => {
    setAuthError(null)
    setAuthFieldErrors({})
    setLoginEmail('')
    setLoginPassword('')
    setSignupEmail('')
    setSignupPassword('')
    setSignupName('')
    apiLogout()
    setUser(null)
  }

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode)
  }, [darkMode])

  useEffect(() => {
    if (!import.meta.env.DEV) return
    Promise.all([healthCheck(), getDefaultLanguages()])
      .then(([, langs]) => {
        setApiStatus(`API OK · ${langs.default_targets.join(', ')}`)
      })
      .catch(() => setApiStatus('Unreachable'))
  }, [])

  const loadSavedList = useCallback(async () => {
    setSavedListLoading(true)
    try {
      const list = await listTranslations()
      setSavedList(list)
    } catch {
      setSavedList([])
    } finally {
      setSavedListLoading(false)
    }
  }, [])
  useEffect(() => { loadSavedList() }, [loadSavedList])

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) setFile(f)
    setError(null)
  }

  const extractText = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const text = await imageToText(file)
      setExtractedText(text)
      setStep('text')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Extraction failed')
    } finally {
      setLoading(false)
    }
  }

  const runTranslate = async () => {
    const text = extractedText.trim() || (translation?.original_text ?? '')
    if (!text) return
    setLoading(true)
    setError(null)
    setGrammarResult(null)
    try {
      const targets = translateAllLangs ? Object.keys(LANGS) : targetLangs.length ? targetLangs : DEFAULT_TARGETS
      const result = await translateText(text, targets, sourceLang, false)
      setTranslation(result)
      setStep('translated')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Translation failed')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveNote = async () => {
    if (!translation) return
    setLoading(true)
    setError(null)
    try {
      const saved = await saveNote(translation.original_text, translation.source_lang, translation.translations)
      setTranslation(saved)
      loadSavedList()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setLoading(false)
    }
  }

  const runGrammarCheck = async () => {
    const text = extractedText.trim()
    if (!text) return
    setGrammarLoading(true)
    setError(null)
    try {
      const result = await checkGrammar(text, 'en-US')
      setGrammarResult(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Grammar check failed')
    } finally {
      setGrammarLoading(false)
    }
  }

  const runDictionaryLookup = async () => {
    if (!dictWord.trim()) return
    setDictLoading(true)
    setError(null)
    setDictResult(null)
    try {
      const result = await lookupWord(dictWord.trim(), 'en')
      setDictResult(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lookup failed')
      setDictResult(null)
    } finally {
      setDictLoading(false)
    }
  }

  const loadSaved = async (id: string) => {
    try {
      const t = await getTranslation(id)
      setTranslation(t)
      setExtractedText(t.original_text)
      setStep('translated')
      setPage('translate')
      closeMobileSidebar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    }
  }

  const handleUpdateSaved = async () => {
    if (!translation?.id) return
    const text = extractedText.trim()
    if (!text) return
    setLoading(true)
    setError(null)
    try {
      const targets = translateAllLangs ? Object.keys(LANGS) : targetLangs.length ? targetLangs : DEFAULT_TARGETS
      const updated = await updateTranslation(translation.id, text, sourceLang, targets)
      setTranslation(updated)
      loadSavedList()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed')
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteSaved = async (id: string) => {
    try {
      await deleteTranslation(id)
      if (translation?.id === id) {
        setTranslation(null)
        setExtractedText('')
        setStep('upload')
      }
      loadSavedList()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  const reset = () => {
    setFile(null)
    setExtractedText('')
    setTranslation(null)
    setStep('upload')
    setError(null)
    setGrammarResult(null)
  }

  const copyToClipboard = (text: string, lang: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedLang(lang)
      setTimeout(() => setCopiedLang(null), 1500)
    })
  }

  const copyAllTranslations = () => {
    if (!translation) return
    const block = Object.entries(translation.translations)
      .map(([lang, text]) => `${LANGS[lang] ?? lang}: ${text}`)
      .join('\n')
    navigator.clipboard.writeText(block).then(() => {
      setCopiedLang('all')
      setTimeout(() => setCopiedLang(null), 1500)
    })
  }

  const selectAllLangs = () => setTargetLangs(Object.keys(LANGS))
  const clearLangs = () => setTargetLangs([])

  const navItems: { id: PageId; label: string; icon: string }[] = [
    { id: 'translate', label: 'Translate', icon: '↔' },
    { id: 'dictionary', label: 'Dictionary', icon: '📖' },
  ]

  // Not logged in → auth screen only
  if (!authLoading && !user) {
    return (
      <div className="auth-page">
        <div className="auth-page-panel auth-page-brand">
          <div className="auth-page-brand-inner">
            <div className="auth-page-logo" aria-hidden>↔</div>
            <h1 className="auth-page-brand-title">Translate</h1>
            <p className="auth-page-brand-tagline">
              Turn text and images into multiple languages. Sign in to save notes and access your workspace.
            </p>
            <div className="auth-page-brand-demo" aria-hidden>
              <div className="auth-page-demo-label">Preview</div>
              <p className="auth-page-demo-original">Hello, welcome to Translate</p>
              <ul className="auth-page-demo-list">
                <li><span className="auth-page-demo-lang">Spanish</span> Hola, bienvenido a Translate</li>
                <li><span className="auth-page-demo-lang">French</span> Bonjour, bienvenue sur Translate</li>
                <li><span className="auth-page-demo-lang">German</span> Hallo, willkommen bei Translate</li>
              </ul>
            </div>
          </div>
        </div>
        <div className="auth-page-panel auth-page-form-panel">
          <button
            type="button"
            className="auth-page-theme-toggle"
            onClick={() => setDarkMode((d) => !d)}
            title={darkMode ? 'Light mode' : 'Dark mode'}
            aria-label={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            <span className="auth-page-theme-icon">{darkMode ? '☀' : '☽'}</span>
            <span className="auth-page-theme-label">{darkMode ? 'Light' : 'Dark'}</span>
          </button>
          <div className="auth-page-card">
            <div className="auth-page-tabs">
              <button
                type="button"
                className={`auth-page-tab ${authTab === 'login' ? 'active' : ''}`}
                onClick={() => { setAuthTab('login'); setAuthError(null); setAuthFieldErrors({}); }}
              >
                Sign in
              </button>
              <button
                type="button"
                className={`auth-page-tab ${authTab === 'signup' ? 'active' : ''}`}
                onClick={() => {
                  setAuthTab('signup')
                  setAuthError(null)
                  setAuthFieldErrors({})
                  setSignupEmail('')
                  setSignupPassword('')
                  setSignupName('')
                }}
              >
                Sign up
              </button>
            </div>
            <form
              className="auth-page-form"
              onSubmit={authTab === 'login' ? handleLogin : handleSignup}
              noValidate
            >
              <div className="auth-page-field">
                <label htmlFor="auth-email">Email</label>
                <input
                  id="auth-email"
                  type="email"
                  autoComplete="email"
                  value={authTab === 'login' ? loginEmail : signupEmail}
                  onChange={(e) => {
                    if (authTab === 'login') setLoginEmail(e.target.value)
                    else setSignupEmail(e.target.value)
                    setAuthFieldErrors((prev) => ({ ...prev, email: undefined }))
                  }}
                  required
                  className={`auth-page-input ${authFieldErrors.email ? 'auth-page-input-error' : ''}`}
                  placeholder="you@example.com"
                  disabled={authSubmitting}
                />
                {authFieldErrors.email && <span className="auth-page-field-error">{authFieldErrors.email}</span>}
              </div>
              {authTab === 'signup' && (
                <div className="auth-page-field">
                  <label htmlFor="auth-name">Name</label>
                  <input
                    id="auth-name"
                    type="text"
                    autoComplete="name"
                    value={signupName}
                    onChange={(e) => { setSignupName(e.target.value); setAuthFieldErrors((prev) => ({ ...prev, name: undefined })); }}
                    className={`auth-page-input ${authFieldErrors.name ? 'auth-page-input-error' : ''}`}
                    placeholder="Your name"
                    disabled={authSubmitting}
                  />
                  {authFieldErrors.name && <span className="auth-page-field-error">{authFieldErrors.name}</span>}
                </div>
              )}
              <div className="auth-page-field">
                <label htmlFor="auth-password">Password</label>
                <div className="auth-page-password-wrap">
                  <input
                    id="auth-password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete={authTab === 'login' ? 'current-password' : 'new-password'}
                    value={authTab === 'login' ? loginPassword : signupPassword}
                    onChange={(e) => {
                      if (authTab === 'login') setLoginPassword(e.target.value)
                      else setSignupPassword(e.target.value)
                      setAuthFieldErrors((prev) => ({ ...prev, password: undefined }))
                    }}
                    required
                    minLength={authTab === 'signup' ? 6 : undefined}
                    className={`auth-page-input ${authFieldErrors.password ? 'auth-page-input-error' : ''}`}
                    placeholder={authTab === 'signup' ? '6+ chars, capital, number, special' : ''}
                    disabled={authSubmitting}
                  />
                  <button
                    type="button"
                    className="auth-page-password-toggle"
                    onClick={() => setShowPassword((s) => !s)}
                    tabIndex={-1}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    title={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? '🙈' : '👁'}
                  </button>
                </div>
                {authTab === 'signup' && !authFieldErrors.password && (
                  <span className="auth-page-hint">Password must be at least 6 characters with 1 capital letter, 1 number, and 1 special character</span>
                )}
                {authFieldErrors.password && <span className="auth-page-field-error">{authFieldErrors.password}</span>}
              </div>
              {authError && (
                <div className="auth-page-error" role="alert">
                  {authError}
                </div>
              )}
              <button
                type="submit"
                className="auth-page-submit"
                disabled={authSubmitting}
              >
                {authSubmitting ? (
                  <>
                    <span className="auth-page-spinner" aria-hidden />
                    <span>{authTab === 'login' ? 'Signing in…' : 'Creating account…'}</span>
                  </>
                ) : (
                  authTab === 'login' ? 'Sign in' : 'Create account'
                )}
              </button>
            </form>
          </div>
        </div>
      </div>
    )
  }

  if (authLoading) {
    return (
      <div className="auth-page auth-page-loading">
        <div className="auth-page-loading-spinner" aria-hidden />
        <p className="auth-page-loading-text">Loading…</p>
      </div>
    )
  }

  return (
    <div className="notion-app">
      {isMobile && !sidebarCollapsed && (
        <button
          type="button"
          className="sidebar-backdrop"
          onClick={() => setSidebarCollapsed(true)}
          aria-label="Close menu"
        />
      )}
      <aside className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <div className="sidebar-brand-icon" aria-hidden>◆</div>
            {!sidebarCollapsed && (
              <div className="sidebar-brand-text">
                <span className="sidebar-logo">Translate</span>
                <span className="sidebar-workspace-label">Workspace</span>
              </div>
            )}
          </div>
          <button
            type="button"
            className="sidebar-toggle"
            onClick={() => setSidebarCollapsed((c) => !c)}
            aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {sidebarCollapsed ? '→' : '←'}
          </button>
        </div>
        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`nav-item ${page === item.id ? 'active' : ''}`}
              onClick={() => {
                setPage(item.id)
                setError(null)
                closeMobileSidebar()
              }}
            >
              <span className="nav-icon">{item.icon}</span>
              {!sidebarCollapsed && <span className="nav-label">{item.label}</span>}
            </button>
          ))}
        </nav>
        {!sidebarCollapsed && (
          <div className="sidebar-saved-section">
            <div className="sidebar-section-title">My notes</div>
            {savedListLoading ? (
              <div className="sidebar-saved-muted">Loading…</div>
            ) : savedList.length === 0 ? (
              <div className="sidebar-saved-muted">No saved notes yet</div>
            ) : (
              <ul className="sidebar-saved-list">
                {savedList.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`sidebar-saved-item ${translation?.id === item.id ? 'active' : ''}`}
                      onClick={() => loadSaved(item.id)}
                    >
                      <span className="sidebar-saved-icon">📄</span>
                      <span className="sidebar-saved-label">
                        {item.original_text.length > 36 ? item.original_text.slice(0, 36) + '…' : item.original_text}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {!sidebarCollapsed && (
          <div className="sidebar-footer">
            {user && (
              <div className="notion-sidebar-account">
                <div className="notion-avatar" title={user.email} aria-hidden>
                  {(user.name?.trim() || user.email)[0].toUpperCase()}
                </div>
                <div className="notion-sidebar-account-meta">
                  <span className="notion-sidebar-name">{user.name?.trim() || user.email.split('@')[0]}</span>
                  <span className="notion-sidebar-email">{user.email}</span>
                </div>
                <button type="button" className="notion-sidebar-logout" onClick={handleLogout}>
                  Log out
                </button>
              </div>
            )}
            {import.meta.env.DEV && apiStatus && (
              <span className="api-status">{apiStatus}</span>
            )}
          </div>
        )}
      </aside>

      <div className="notion-main">
        <header className="topbar">
          <div className="topbar-left">
            {isMobile && (
              <button
                type="button"
                className="topbar-menu-btn"
                onClick={() => setSidebarCollapsed((c) => !c)}
                aria-label={sidebarCollapsed ? 'Open menu' : 'Close menu'}
              >
                {sidebarCollapsed ? '☰' : '✕'}
              </button>
            )}
            <div className="topbar-titles">
              <h1 className="topbar-title">
                {page === 'translate' && 'Translate'}
                {page === 'dictionary' && 'Dictionary'}
              </h1>
              <p className="topbar-sub">Private page · {user?.email ?? ''}</p>
            </div>
          </div>
          <div className="topbar-actions">
            <button
              type="button"
              className="topbar-logout"
              onClick={handleLogout}
              title="Sign out"
            >
              Log out
            </button>
            <button
              type="button"
              className="theme-toggle-btn"
              onClick={() => setDarkMode((d) => !d)}
              title={darkMode ? 'Switch to light' : 'Switch to dark'}
              aria-label="Toggle theme"
            >
              <span className="theme-toggle-icon">{darkMode ? '☀' : '☽'}</span>
              <span className="theme-toggle-label">{darkMode ? 'Light' : 'Dark'}</span>
            </button>
          </div>
        </header>

        <main className="notion-content">
          {error && <div className="error-banner">{error}</div>}

          {page === 'dictionary' && (
            <div className="block">
              <p className="block-caption">Look up definitions (Free Dictionary API)</p>
              <div className="dict-row">
                <input
                  type="text"
                  value={dictWord}
                  onChange={(e) => setDictWord(e.target.value)}
                  placeholder="Enter a word…"
                  onKeyDown={(e) => e.key === 'Enter' && runDictionaryLookup()}
                />
                <button type="button" onClick={runDictionaryLookup} disabled={dictLoading || !dictWord.trim()}>
                  {dictLoading ? '…' : 'Look up'}
                </button>
              </div>
              {dictResult && dictResult.length > 0 && (
                <div className="dict-result">
                  <h2 className="dict-word">{dictResult[0].word} {dictResult[0].phonetic && <span className="phonetic">{dictResult[0].phonetic}</span>}</h2>
                  {dictResult[0].meanings.map((m, i) => (
                    <div key={i} className="meaning">
                      <em>{m.partOfSpeech}</em>
                      <ul>
                        {m.definitions.slice(0, 4).map((d, j) => (
                          <li key={j}>
                            {d.definition}
                            {d.example && <div className="example">{d.example}</div>}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {page === 'translate' && (
            <>
              {step === 'upload' && (
                <div className="block">
                  <h2 className="block-title">New translation</h2>
                  <p className="block-caption">Extract text from an image (classmate API) or type below. Images only (e.g. JPG, PNG) — PDF is not supported.</p>
                  <div className="block-body">
                    <input type="file" accept="image/*" onChange={onFileChange} className="file-input" title="Images only (no PDF)" />
                    {file && <p className="file-name">{file.name}</p>}
                    <button type="button" onClick={extractText} disabled={!file || loading} className="btn-primary">
                      {loading ? 'Extracting…' : 'Extract text'}
                    </button>
                    <p className="or">— or —</p>
                    <button type="button" className="btn-ghost" onClick={() => { setStep('text'); setExtractedText(''); }}>
                      Type or paste text
                    </button>
                  </div>
                </div>
              )}

              {(step === 'text' || step === 'translated') && (
                <>
                  <div className="block">
                    <h2 className="block-title">Text</h2>
                    <div className="textarea-wrap">
                      <textarea
                        value={extractedText}
                        onChange={(e) => setExtractedText(e.target.value)}
                        rows={5}
                        placeholder="Type or paste text to translate…"
                        className="notion-textarea"
                      />
                      <div className="textarea-meta">
                        <span>{extractedText.length} chars</span>
                        <button type="button" className="link-btn" onClick={() => setExtractedText('')}>Clear</button>
                      </div>
                    </div>
                    <div className="block-actions">
                      <button type="button" className="btn-secondary" onClick={runGrammarCheck} disabled={grammarLoading || !extractedText.trim()}>
                        {grammarLoading ? 'Checking…' : 'Check grammar'}
                      </button>
                    </div>
                    {grammarResult && grammarResult.matches.length > 0 && (
                      <div className="grammar-result">
                        <strong>Issues</strong>
                        <ul>
                          {grammarResult.matches.map((m, i) => (
                            <li key={i}>{m.message}{m.replacements?.length ? ` → ${m.replacements.slice(0, 2).map(r => r.value).join(', ')}` : ''}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {grammarResult && grammarResult.matches.length === 0 && <p className="grammar-ok">No issues found.</p>}
                    <div className="chips">
                      {SAMPLE_TEXTS.map((s) => (
                        <button key={s} type="button" className="chip" onClick={() => setExtractedText(s)}>{s}</button>
                      ))}
                    </div>
                    <div className="lang-options">
                      <label className="lang-select-wrap">
                        <span>Source</span>
                        <select value={sourceLang} onChange={(e) => setSourceLang(e.target.value)}>
                          <option value="en">English</option>
                          {Object.entries(LANGS).map(([code, name]) => (
                            <option key={code} value={code}>{name}</option>
                          ))}
                        </select>
                      </label>
                      <label className="checkbox-wrap">
                        <input type="checkbox" checked={translateAllLangs} onChange={(e) => setTranslateAllLangs(e.target.checked)} />
                        All languages
                      </label>
                      {!translateAllLangs && (
                        <div className="lang-checkboxes">
                          {Object.entries(LANGS).map(([code, name]) => (
                            <label key={code}>
                              <input
                                type="checkbox"
                                checked={targetLangs.includes(code)}
                                onChange={(e) => setTargetLangs((prev) => e.target.checked ? [...prev, code] : prev.filter((l) => l !== code))}
                              />
                              {name}
                            </label>
                          ))}
                          <div className="lang-actions">
                            <button type="button" className="link-btn" onClick={selectAllLangs}>All</button>
                            <button type="button" className="link-btn" onClick={clearLangs}>None</button>
                          </div>
                        </div>
                      )}
                    </div>
                    <button type="button" onClick={runTranslate} disabled={loading} className="btn-primary">
                      {loading ? 'Translating…' : 'Translate'}
                    </button>
                  </div>

                  {translation && (
                    <div className="block">
                <div className="block-head">
                  <h2 className="block-title">Translations</h2>
                  <div className="block-buttons">
                    {!translation.id ? (
                      <button type="button" className="btn-save-note-primary" onClick={handleSaveNote} disabled={loading}>
                        {loading ? 'Saving…' : 'Save this note'}
                      </button>
                    ) : (
                      <>
                        <button type="button" className="btn-secondary-sm" onClick={handleUpdateSaved} disabled={loading}>Update</button>
                        <button type="button" className="btn-danger-sm" onClick={() => translation.id && handleDeleteSaved(translation.id)}>Delete</button>
                      </>
                    )}
                    <button type="button" className="btn-secondary-sm" onClick={copyAllTranslations}>{copiedLang === 'all' ? 'Copied' : 'Copy all'}</button>
                  </div>
                </div>
                      {translation.id && <p className="saved-id">Saved · {translation.id.slice(0, 8)}…</p>}
                      <p className="original">Original: {translation.original_text}</p>
                      <ul className="trans-list">
                        {Object.entries(translation.translations).map(([lang, text]) => (
                          <li key={lang}>
                            <strong>{LANGS[lang] ?? lang}</strong>
                            <span>{text}</span>
                            <button type="button" className="copy-btn" onClick={() => copyToClipboard(text, lang)} title="Copy">{copiedLang === lang ? '✓' : '📋'}</button>
                          </li>
                        ))}
                      </ul>
                      <button type="button" className="link-btn" onClick={() => setShowRaw((r) => !r)}>{showRaw ? 'Hide' : 'Show'} JSON</button>
                      {showRaw && <pre className="raw-json">{JSON.stringify(translation, null, 2)}</pre>}
                    </div>
                  )}

                  <button type="button" className="btn-ghost" onClick={reset}>Start over</button>
                </>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  )
}
