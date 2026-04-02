const KNOWN_MESSAGES: { test: RegExp | string; message: string }[] = [
  { test: /incorrect password/i, message: 'Incorrect password.' },
  { test: /no account found for this email/i, message: 'No account for this email. Check the address or sign up.' },
  { test: /invalid (email|username) or password/i, message: 'Invalid email or password.' },
  { test: /invalid credentials/i, message: 'Invalid email or password.' },
  { test: /email already registered/i, message: 'Email already registered. Please use a different email or try signing in.' },
  { test: /user not found/i, message: 'No account for this email. Check the address or sign up.' },
]

function normalizeRaw(raw: string): string {
  let m = raw.trim()
  for (const { test, message } of KNOWN_MESSAGES) {
    if (typeof test === 'string') {
      if (m.includes(test)) return message
    } else if (test.test(m)) {
      return message
    }
  }
  return m
}

export function getErrorMessage(error: unknown): string {
  if (error == null) return 'Something went wrong.'

  if (typeof error === 'string') {
    return normalizeRaw(error) || 'Something went wrong.'
  }

  if (error instanceof Error) {
    const msg = error.message || ''
    if (!msg && (error as Error & { cause?: unknown }).cause) {
      return getErrorMessage((error as Error & { cause?: unknown }).cause)
    }
    return normalizeRaw(msg) || 'Something went wrong.'
  }

  if (typeof error === 'object') {
    const o = error as Record<string, unknown>
    if (typeof o.message === 'string') return normalizeRaw(o.message)
    if (typeof o.detail === 'string') return normalizeRaw(o.detail)
    if (Array.isArray(o.detail) && o.detail.length > 0) {
      const first = o.detail[0] as { msg?: string }
      if (typeof first?.msg === 'string') return normalizeRaw(first.msg)
    }
    if (typeof o.error === 'string') return normalizeRaw(o.error)
  }

  return 'Something went wrong.'
}
