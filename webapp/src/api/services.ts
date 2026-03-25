// Translate API, OCR, grammar, dictionary, auth helpers

const TRANSLATE_BASE = import.meta.env.VITE_TRANSLATE_API_URL || 'https://t3jb8c44xi.execute-api.us-east-1.amazonaws.com'
// Partner OCR (image → text)
const IMAGE_TO_TEXT_BASE = import.meta.env.VITE_IMAGE_TO_TEXT_API_URL || 'https://xkdvpogqt0.execute-api.us-east-1.amazonaws.com/prod'

const AUTH_TOKEN_KEY = 'auth_token'

export function getStoredToken(): string | null {
  return typeof localStorage !== 'undefined' ? localStorage.getItem(AUTH_TOKEN_KEY) : null
}

function authHeaders(): Record<string, string> {
  const token = getStoredToken()
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) h['Authorization'] = `Bearer ${token}`
  return h
}

export interface TranslateResponse {
  original_text: string
  source_lang: string
  translations: Record<string, string>
  id?: string
  created_at?: string
}

export async function translateText(
  text: string,
  targetLanguages?: string[],
  sourceLang?: string,
  save = false
): Promise<TranslateResponse> {
  const res = await fetch(`${TRANSLATE_BASE}/translate`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      text,
      source_lang: sourceLang ?? 'en',
      target_languages: targetLanguages ?? ['es', 'fr', 'de', 'it', 'pt'],
      save,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error((err as { detail?: string }).detail || 'Translation failed')
  }
  return res.json()
}

export async function getTranslation(id: string): Promise<TranslateResponse> {
  const res = await fetch(`${TRANSLATE_BASE}/translate/${id}`, { headers: authHeaders() })
  if (!res.ok) {
    if (res.status === 404) throw new Error('Translation not found')
    throw new Error('Failed to load translation')
  }
  return res.json()
}

export interface TranslationSummary {
  id: string
  original_text: string
  source_lang: string
  created_at: string
}
export async function listTranslations(): Promise<TranslationSummary[]> {
  const res = await fetch(`${TRANSLATE_BASE}/translations`, { headers: authHeaders() })
  if (!res.ok) throw new Error('Failed to list translations')
  return res.json()
}

export async function saveNote(
  originalText: string,
  sourceLang: string,
  translations: Record<string, string> = {}
): Promise<TranslateResponse> {
  const res = await fetch(`${TRANSLATE_BASE}/translations`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      original_text: originalText,
      source_lang: sourceLang,
      translations,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error((err as { detail?: string }).detail || 'Save failed')
  }
  return res.json()
}

/** Save note body only (no MyMemory call). Omitting translations keeps existing on server. */
export async function patchNote(
  id: string,
  originalText: string,
  sourceLang?: string,
  translations?: Record<string, string> | null
): Promise<TranslateResponse> {
  const body: Record<string, unknown> = {
    original_text: originalText,
    source_lang: sourceLang ?? 'en',
  }
  if (translations != null) {
    body.translations = translations
  }
  const res = await fetch(`${TRANSLATE_BASE}/translate/${id}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error((err as { detail?: string }).detail || 'Save failed')
  }
  return res.json()
}

export async function updateTranslation(
  id: string,
  text: string,
  sourceLang?: string,
  targetLanguages?: string[]
): Promise<TranslateResponse> {
  const res = await fetch(`${TRANSLATE_BASE}/translate/${id}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify({
      text,
      source_lang: sourceLang ?? 'en',
      target_languages: targetLanguages ?? undefined,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error((err as { detail?: string }).detail || 'Update failed')
  }
  return res.json()
}

export async function deleteTranslation(id: string): Promise<void> {
  const res = await fetch(`${TRANSLATE_BASE}/translate/${id}`, { method: 'DELETE', headers: authHeaders() })
  if (!res.ok) throw new Error('Delete failed')
}

export interface ImageToTextResponse {
  success?: boolean
  jobId?: string
  text?: string
  confidence?: number
  filename?: string
  language?: string
}

// POST /ocr; if only jobId comes back, GET /ocr/:jobId
export async function imageToText(file: File, language = 'eng'): Promise<string> {
  if (!IMAGE_TO_TEXT_BASE) throw new Error('Image-to-Text API URL not configured. Set VITE_IMAGE_TO_TEXT_API_URL in .env')
  const form = new FormData()
  form.append('image', file)
  form.append('language', language)
  const res = await fetch(`${IMAGE_TO_TEXT_BASE}/ocr`, {
    method: 'POST',
    body: form,
  })
  const data: ImageToTextResponse & { result?: string; data?: { text?: string; confidence?: number | null } } = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error((data as { error?: string }).error || 'Image-to-text failed')

  let text = data.text ?? data.data?.text ?? ''
  const jobId = data.jobId

  if (!text.trim() && jobId) {
    const getRes = await fetch(`${IMAGE_TO_TEXT_BASE}/ocr/${encodeURIComponent(jobId)}`, { method: 'GET' })
    const fetched = await getRes.json().catch(() => ({})) as ImageToTextResponse & { data?: { text?: string } }
    if (!getRes.ok) throw new Error((fetched as { error?: string }).error || 'Could not fetch OCR result')
    text = fetched.text ?? fetched.data?.text ?? ''
  }

  return text.trim() || '(No text extracted)'
}

export interface LanguageToolMatch {
  message: string
  shortMessage: string
  offset: number
  length: number
  replacements?: Array<{ value: string }>
}

export interface LanguageToolResponse {
  matches: LanguageToolMatch[]
}

export async function checkGrammar(text: string, language = 'en-US'): Promise<LanguageToolResponse> {
  const params = new URLSearchParams({ text, language })
  const res = await fetch('https://api.languagetool.org/v2/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params,
  })
  if (!res.ok) throw new Error('Grammar check failed')
  return res.json()
}

export interface DictionaryMeaning {
  partOfSpeech: string
  definitions: Array<{ definition: string; example?: string }>
}

export interface DictionaryEntry {
  word: string
  phonetic?: string
  meanings: DictionaryMeaning[]
}

export async function lookupWord(word: string, lang = 'en'): Promise<DictionaryEntry[]> {
  const res = await fetch(`https://api.dictionaryapi.dev/api/v2/entries/${lang}/${encodeURIComponent(word.trim())}`)
  if (!res.ok) {
    if (res.status === 404) throw new Error('Word not found')
    throw new Error('Dictionary lookup failed')
  }
  return res.json()
}

export async function getDefaultLanguages(): Promise<{ default_targets: string[]; source_default: string }> {
  const res = await fetch(`${TRANSLATE_BASE}/languages`)
  if (!res.ok) throw new Error('Failed to load languages')
  return res.json()
}

export async function healthCheck(): Promise<{ status: string }> {
  const res = await fetch(`${TRANSLATE_BASE}/health`)
  if (!res.ok) throw new Error('API unhealthy')
  return res.json()
}

export interface AuthUser {
  user_id: string
  email: string
  name?: string
}

// Turn FastAPI errors into one string
function apiErrorMessage(data: unknown, fallback: string): string {
  if (!data || typeof data !== 'object') return fallback
  const d = data as { detail?: unknown }
  const detail = d.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; message?: string }
    const msg = first?.msg ?? first?.message
    if (typeof msg === 'string') return msg
  }
  return fallback
}

export async function login(email: string, password: string): Promise<{ token: string; user: AuthUser }> {
  const res = await fetch(`${TRANSLATE_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(apiErrorMessage(data, 'Login failed'))
  }
  const data = await res.json()
  if (typeof localStorage !== 'undefined' && data.token) localStorage.setItem(AUTH_TOKEN_KEY, data.token)
  return data
}

export async function signup(email: string, name: string, password: string): Promise<{ message: string }> {
  const res = await fetch(`${TRANSLATE_BASE}/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, name, password }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(apiErrorMessage(data, 'Signup failed'))
  }
  return res.json()
}

export async function verifyAuth(): Promise<AuthUser | null> {
  const token = getStoredToken()
  if (!token) return null
  const res = await fetch(`${TRANSLATE_BASE}/auth/verify`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return null
  const data = await res.json()
  return data as AuthUser
}

export function logout(): void {
  if (typeof localStorage !== 'undefined') localStorage.removeItem(AUTH_TOKEN_KEY)
}
